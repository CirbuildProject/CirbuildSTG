"""BM25-based short-term memory store for the Cirbuild agent.

Provides keyword-based retrieval over pipeline artifacts (spec text,
pseudocode plans, and RTL code). Uses BM25 scoring for ranking —
no external embedding models required.

This store is ephemeral (session-scoped) and optimized for the
syntax-heavy, semantics-light nature of hardware descriptions
where exact signal names and keywords matter more than semantic similarity.
"""

import math
import re
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("cirbuild.memory.rag_store")

# Valid namespace names
NAMESPACES = ("spec", "pseudocode", "rtl", "metrics")


@dataclass
class Chunk:
    """A single indexed text chunk."""

    text: str
    namespace: str
    metadata: Dict[str, str] = field(default_factory=dict)
    tokens: List[str] = field(default_factory=list)


class RAGStore:
    """BM25-based in-memory retrieval store.

    Stores text chunks across four namespaces (spec, pseudocode, rtl, metrics)
    and retrieves the most relevant chunks for a given query using
    BM25 scoring.

    Args:
        k1: BM25 term frequency saturation parameter. Default 1.5.
        b: BM25 document length normalization parameter. Default 0.75.
        chunk_size: Maximum characters per chunk when splitting. Default 500.
        chunk_overlap: Character overlap between chunks. Default 100.
    """

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
    ) -> None:
        self._k1 = k1
        self._b = b
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._chunks: List[Chunk] = []
        self._idf_cache: Dict[str, float] = {}
        self._avg_dl: float = 0.0
        self._dirty = True  # IDF needs recomputation

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenize text into lowercase words, preserving signal names.

        Handles hardware-specific tokens like signal_name, bit widths,
        and Verilog keywords.
        """
        # Split on whitespace and punctuation, but keep underscores and brackets
        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*|\d+", text.lower())
        return tokens

    def _split_into_chunks(
        self,
        text: str,
        namespace: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> List[Chunk]:
        """Split text into overlapping chunks."""
        meta = metadata or {}
        chunks: List[Chunk] = []

        if len(text) <= self._chunk_size:
            tokens = self._tokenize(text)
            chunks.append(
                Chunk(text=text, namespace=namespace, metadata=meta, tokens=tokens)
            )
            return chunks

        start = 0
        while start < len(text):
            end = start + self._chunk_size
            chunk_text = text[start:end]

            # Try to break at a newline or space
            if end < len(text):
                last_newline = chunk_text.rfind("\n")
                if last_newline > self._chunk_size // 2:
                    chunk_text = chunk_text[:last_newline]
                    end = start + last_newline

            tokens = self._tokenize(chunk_text)
            chunks.append(
                Chunk(
                    text=chunk_text.strip(),
                    namespace=namespace,
                    metadata=meta,
                    tokens=tokens,
                )
            )

            start = end - self._chunk_overlap
            if start >= len(text):
                break

        return chunks

    def add(
        self,
        text: str,
        namespace: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> int:
        """Add a text document to the store.

        The text is split into chunks and indexed for BM25 retrieval.

        Args:
            text: The text content to store.
            namespace: One of 'spec', 'pseudocode', 'rtl', 'metrics'.
            metadata: Optional metadata dict (e.g., module_name, source).

        Returns:
            Number of chunks created.

        Raises:
            ValueError: If namespace is invalid.
        """
        if namespace not in NAMESPACES:
            raise ValueError(
                f"Invalid namespace '{namespace}'. Must be one of {NAMESPACES}"
            )

        if not text.strip():
            return 0

        new_chunks = self._split_into_chunks(text, namespace, metadata)
        self._chunks.extend(new_chunks)
        self._dirty = True

        logger.debug("Added %d chunks to '%s' namespace", len(new_chunks), namespace)
        return len(new_chunks)

    def store_pipeline_artifacts(self, artifacts: "PipelineArtifacts") -> None:
        """Convenience method to store all pipeline artifacts.

        Args:
            artifacts: A PipelineArtifacts instance from the pipeline bridge.
        """
        meta = {"module_name": artifacts.module_name}

        if artifacts.spec_text:
            self.add(artifacts.spec_text, "spec", meta)

        if artifacts.pseudocode:
            self.add(artifacts.pseudocode, "pseudocode", meta)

        if artifacts.rtl_code:
            self.add(artifacts.rtl_code, "rtl", meta)

        logger.info(
            "Stored pipeline artifacts for '%s': %d total chunks",
            artifacts.module_name,
            len(self._chunks),
        )

    def store_librelane_results(self, metrics_text: str, module_name: str, run_tag: str = "") -> int:
        """Store librelane metrics in the metrics namespace.

        Args:
            metrics_text: Formatted metrics/results text to store (can include DRC, LVS, PPA, timing, area, power).
            module_name: The module/design name.
            run_tag: Optional run identifier for reference.

        Returns:
            Number of chunks created.
        """
        if not metrics_text.strip():
            return 0

        meta = {"module_name": module_name, "run_tag": run_tag}
        chunk_count = self.add(metrics_text, "metrics", meta)
        logger.info(
            "Stored librelane metrics for '%s': %d chunks",
            module_name,
            chunk_count,
        )
        return chunk_count

    def query(
        self,
        query: str,
        namespace: str = "all",
        top_k: int = 5,
    ) -> List[Tuple[float, Chunk]]:
        """Query the store and return the most relevant chunks.

        Args:
            query: The search query string.
            namespace: Namespace to search ('spec', 'pseudocode', 'rtl', 'metrics', or 'all').
            top_k: Maximum number of results to return.

        Returns:
            List of (score, Chunk) tuples, sorted by descending score.
        """
        if not self._chunks:
            return []

        if self._dirty:
            self._recompute_idf()

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Filter by namespace
        if namespace == "all":
            candidates = self._chunks
        else:
            candidates = [c for c in self._chunks if c.namespace == namespace]

        if not candidates:
            return []

        # Score each candidate with BM25
        scored: List[Tuple[float, Chunk]] = []
        for chunk in candidates:
            score = self._bm25_score(query_tokens, chunk)
            if score > 0:
                scored.append((score, chunk))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    def _recompute_idf(self) -> None:
        """Recompute IDF values and average document length."""
        n = len(self._chunks)
        if n == 0:
            self._avg_dl = 0.0
            self._idf_cache = {}
            self._dirty = False
            return

        # Document frequency for each term
        df: Counter = Counter()
        total_length = 0

        for chunk in self._chunks:
            unique_tokens = set(chunk.tokens)
            for token in unique_tokens:
                df[token] += 1
            total_length += len(chunk.tokens)

        self._avg_dl = total_length / n

        # IDF with smoothing: log((N - df + 0.5) / (df + 0.5) + 1)
        self._idf_cache = {}
        for term, freq in df.items():
            self._idf_cache[term] = math.log(
                (n - freq + 0.5) / (freq + 0.5) + 1.0
            )

        self._dirty = False

    def _bm25_score(self, query_tokens: List[str], chunk: Chunk) -> float:
        """Compute BM25 score for a chunk against query tokens."""
        if not chunk.tokens:
            return 0.0

        dl = len(chunk.tokens)
        tf_map = Counter(chunk.tokens)
        score = 0.0

        for qt in query_tokens:
            if qt not in self._idf_cache:
                continue

            idf = self._idf_cache[qt]
            tf = tf_map.get(qt, 0)

            # BM25 formula
            numerator = tf * (self._k1 + 1)
            denominator = tf + self._k1 * (
                1 - self._b + self._b * dl / max(self._avg_dl, 1)
            )
            score += idf * (numerator / denominator)

        return score

    def clear(self, namespace: Optional[str] = None) -> None:
        """Clear stored chunks.

        Args:
            namespace: If provided, clear only that namespace.
                If None, clear everything.
        """
        if namespace is None:
            self._chunks.clear()
        else:
            self._chunks = [c for c in self._chunks if c.namespace != namespace]
        self._dirty = True
        logger.info(
            "Cleared memory%s",
            f" (namespace: {namespace})" if namespace else "",
        )

    def stats(self) -> Dict[str, int]:
        """Return chunk counts per namespace."""
        counts: Dict[str, int] = {ns: 0 for ns in NAMESPACES}
        for chunk in self._chunks:
            counts[chunk.namespace] = counts.get(chunk.namespace, 0) + 1
        counts["total"] = len(self._chunks)
        return counts

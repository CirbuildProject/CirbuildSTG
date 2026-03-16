"""Bridge between the Cirbuild agent and the spec2rtl pipeline backend.

Validates inputs, invokes the pipeline, and captures intermediate
artifacts (spec text, pseudocode, RTL) for the RAG memory store.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from cirbuild.config.settings import CirbuildSettings
from cirbuild.pipeline.json_spec import JsonHardwareSpec

logger = logging.getLogger("cirbuild.pipeline.bridge")


def _json_to_spec_text(spec_json: dict) -> str:
    """Convert a JSON spec dict into a natural-language spec string.

    Local copy to avoid depending on Spec2RTLPipeline's private API.
    """
    parts = []
    parts.append(f"Module Name: {spec_json.get('module_name', 'Unknown')}")
    parts.append(f"\nDescription:\n{spec_json.get('description', '')}")

    if inputs := spec_json.get("inputs"):
        parts.append("\nInputs:")
        for name, desc in inputs.items():
            parts.append(f"  - {name}: {desc}")

    if outputs := spec_json.get("outputs"):
        parts.append("\nOutputs:")
        for name, desc in outputs.items():
            parts.append(f"  - {name}: {desc}")

    if behavior := spec_json.get("behavior"):
        parts.append(f"\nBehavior:\n{behavior}")

    if constraints := spec_json.get("constraints"):
        parts.append("\nConstraints:")
        for c in constraints:
            parts.append(f"  - {c}")

    if classification := spec_json.get("classification"):
        parts.append(f"\nHardware Classification: {classification}")

    return "\n".join(parts)


class PipelineArtifacts:
    """Container for intermediate pipeline artifacts captured for RAG."""

    def __init__(self) -> None:
        self.spec_text: str = ""
        self.module_name: str = ""
        self.classification: str = ""
        self.pseudocode: str = ""
        self.final_cpp: str = ""
        self.rtl_code: str = ""
        self.rtl_path: Optional[str] = None
        self.success: bool = False
        self.error_log: Optional[str] = None


class Spec2RTLBridge:
    """Bridge for invoking the spec2rtl pipeline from the Cirbuild agent.

    Handles input validation, pipeline execution, and artifact capture.
    The spec2rtl pipeline uses its own LLM configuration internally —
    this bridge does NOT share the agent's LLM channel.

    Args:
        settings: CirbuildSTG settings.
    """

    def __init__(self, settings: CirbuildSettings | None = None) -> None:
        self._settings = settings or CirbuildSettings.from_yaml()
        self._pipeline = None  # Lazy init

    def _get_pipeline(self):
        """Lazily initialize the spec2rtl pipeline."""
        if self._pipeline is None:
            from spec2rtl.pipeline import Spec2RTLPipeline
            self._pipeline = Spec2RTLPipeline(
                config_path=self._settings.spec2rtl_config_path
            )
        return self._pipeline

    def run_from_json(
        self,
        spec_json: dict,
        target_compiler: str | None = None,
    ) -> PipelineArtifacts:
        """Validate and run the pipeline from a JSON spec.

        Args:
            spec_json: Raw JSON dict from the agent.
            target_compiler: Override compiler setting.

        Returns:
            PipelineArtifacts with captured intermediate data.
        """
        # Validate with Pydantic schema
        validated = JsonHardwareSpec.model_validate(spec_json)
        logger.info("✅ JSON spec validated: %s", validated.module_name)

        artifacts = PipelineArtifacts()
        artifacts.module_name = validated.module_name
        artifacts.classification = validated.classification

        # Convert to text for artifact storage
        artifacts.spec_text = _json_to_spec_text(spec_json)

        # Run the pipeline
        pipeline = self._get_pipeline()
        result = pipeline.run_from_json(spec_json, target_compiler)

        artifacts.success = result.success
        artifacts.module_name = result.module_name
        artifacts.rtl_path = result.rtl_output_path
        artifacts.error_log = result.error_log

        # Capture RTL output if successful
        if result.success and result.rtl_output_path:
            rtl_path = Path(result.rtl_output_path)
            if rtl_path.exists():
                artifacts.rtl_code = rtl_path.read_text(encoding="utf-8")

        return artifacts

    def run_from_file(
        self,
        file_path: Path,
        target_compiler: str | None = None,
    ) -> PipelineArtifacts:
        """Run the pipeline from a file (PDF, TXT, or JSON).

        Args:
            file_path: Path to the specification file.
            target_compiler: Override compiler setting.

        Returns:
            PipelineArtifacts with captured intermediate data.
        """
        artifacts = PipelineArtifacts()
        pipeline = self._get_pipeline()

        suffix = file_path.suffix.lower()

        if suffix == ".json":
            spec_json = json.loads(file_path.read_text(encoding="utf-8"))
            return self.run_from_json(spec_json, target_compiler)

        elif suffix == ".txt":
            spec_text = file_path.read_text(encoding="utf-8")
            artifacts.spec_text = spec_text
            result = pipeline.run_from_text(spec_text, target_compiler)

        elif suffix == ".pdf":
            artifacts.spec_text = f"[PDF file: {file_path.name}]"
            result = pipeline.run(file_path, target_compiler)

        else:
            raise ValueError(
                f"Unsupported file format: {suffix}. "
                "Supported: .json, .txt, .pdf"
            )

        artifacts.success = result.success
        artifacts.rtl_path = result.rtl_output_path
        artifacts.error_log = result.error_log

        if result.success and result.rtl_output_path:
            rtl_path = Path(result.rtl_output_path)
            if rtl_path.exists():
                artifacts.rtl_code = rtl_path.read_text(encoding="utf-8")

        return artifacts

    def run_from_text(
        self,
        spec_text: str,
        target_compiler: str | None = None,
    ) -> PipelineArtifacts:
        """Run the pipeline from raw text (e.g., from chat input).

        Args:
            spec_text: Raw specification text.
            target_compiler: Override compiler setting.

        Returns:
            PipelineArtifacts with captured intermediate data.
        """
        artifacts = PipelineArtifacts()
        artifacts.spec_text = spec_text

        pipeline = self._get_pipeline()
        result = pipeline.run_from_text(spec_text, target_compiler)

        artifacts.success = result.success
        artifacts.rtl_path = result.rtl_output_path
        artifacts.error_log = result.error_log

        if result.success and result.rtl_output_path:
            rtl_path = Path(result.rtl_output_path)
            if rtl_path.exists():
                artifacts.rtl_code = rtl_path.read_text(encoding="utf-8")

        return artifacts

"""Tool definitions and handlers for the Cirbuild agent.

Each tool is defined in OpenAI function-calling format and has
a corresponding handler function. Memory (RAG), workspace, and
librelane tools are wired to real implementations.
"""

from __future__ import annotations
import os
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from cirbuild.config.settings import CirbuildSettings

if TYPE_CHECKING:
    from cirbuild.librelane.runner import LibrelaneRunner
    from cirbuild.memory.rag_store import RAGStore
    from cirbuild.workspace.manager import WorkspaceManager

logger = logging.getLogger("cirbuild.agent.tools")


def _resolve_api_key(model: str) -> str | None:
    """Resolve the correct API key for a given model string.

    Inspects the model prefix to select the appropriate provider key
    from the environment. Mirrors the logic in CirbuildAgent._resolve_api_key
    so that tool handlers use the same provider-specific key routing.

    Key environment variables (set in .env):
        CIRBUILD_OPENROUTER_KEY  — for ``openrouter/`` models
        CIRBUILD_GEMINI_KEY      — for ``gemini/`` models
        CIRBUILD_ANTHROPIC_KEY   — for ``anthropic/`` models

    Args:
        model: LiteLLM model string (e.g. ``openrouter/minimax/minimax-m2.5``).

    Returns:
        The resolved API key string, or None if no matching key is set.
    """
    if model.startswith("gemini/"):
        return os.environ.get("CIRBUILD_GEMINI_KEY")
    if model.startswith("anthropic/"):
        return os.environ.get("CIRBUILD_ANTHROPIC_KEY")
    if model.startswith("openrouter/"):
        return os.environ.get("CIRBUILD_OPENROUTER_KEY")
    # Unknown provider prefix — let LiteLLM fall back to its own env detection
    return None


def get_tool_definitions() -> List[dict]:
    """Return all tool definitions in OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": "parse_spec_to_json",
                "description": (
                    "Parse a natural-language hardware specification into a structured "
                    "JSON object compatible with the Spec2RTL pipeline. Use this when "
                    "the user describes a hardware module in conversation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "spec_description": {
                            "type": "string",
                            "description": "The user's natural-language hardware specification.",
                        }
                    },
                    "required": ["spec_description"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_spec2rtl_pipeline",
                "description": (
                    "Execute the Spec2RTL pipeline with a JSON specification to generate "
                    "RTL (Verilog) code. The JSON must conform to the JsonHardwareSpec schema."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "spec_json": {
                            "type": "object",
                            "description": (
                                "Structured hardware spec with module_name, description, "
                                "inputs, outputs, behavior, constraints, classification."
                            ),
                        },
                        "target_compiler": {
                            "type": "string",
                            "description": "Target HLS compiler. Defaults to 'Google XLS'.",
                        },
                    },
                    "required": ["spec_json"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_spec2rtl_from_file",
                "description": (
                    "Execute the Spec2RTL pipeline from a specification file. "
                    "Supports PDF, TXT, and JSON file formats."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the specification file.",
                        },
                        "target_compiler": {
                            "type": "string",
                            "description": "Target HLS compiler. Defaults to 'Google XLS'.",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_memory",
                "description": (
                    "Query the short-term memory store for information about the current "
                    "design session. Can retrieve spec details, pseudocode plans, or RTL code."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query.",
                        },
                        "namespace": {
                            "type": "string",
                            "enum": ["spec", "pseudocode", "rtl", "all"],
                            "description": "Which memory namespace to search.",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_workspace_file",
                "description": "Read the contents of a file from the Verilog workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Name of the file to read.",
                        },
                    },
                    "required": ["filename"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_workspace_file",
                "description": (
                    "Write or update a Verilog/SystemVerilog file in the workspace. "
                    "A history snapshot is saved automatically."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Name of the file to write.",
                        },
                        "content": {
                            "type": "string",
                            "description": "The full file content to write.",
                        },
                    },
                    "required": ["filename", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_workspace_files",
                "description": "List all files in the current Verilog workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "package_for_librelane",
                "description": (
                    "Package the workspace Verilog files into a librelane-compatible "
                    "design directory with generated configuration."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module_name": {
                            "type": "string",
                            "description": "Top-level module name for librelane config.",
                        },
                        "clock_port": {
                            "type": "string",
                            "description": "Clock port name. Defaults to 'clk'.",
                        },
                        "clock_period": {
                            "type": "number",
                            "description": "Target clock period in ns. Defaults to 10.",
                        },
                    },
                    "required": ["module_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_librelane_flow",
                "description": (
                    "Execute the Librelane RTL-to-GDSII physical design flow on the "
                    "packaged design. Returns PPA (Power, Performance, Area) metrics."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module_name": {
                            "type": "string",
                            "description": "Module name (must match a packaged design).",
                        },
                    },
                    "required": ["module_name"],
                },
            },
        },
    ]


def get_tool_handlers(
    settings: CirbuildSettings,
    rag_store: RAGStore | None = None,
    workspace_manager: WorkspaceManager | None = None,
    librelane_runner: LibrelaneRunner | None = None,
) -> Dict[str, Callable]:
    """Return a mapping of tool names to their handler functions.

    Args:
        settings: CirbuildSTG settings for configuring handlers.
        rag_store: Optional RAGStore instance. Creates a default if None.
        workspace_manager: Optional WorkspaceManager instance. Creates a
            default if None.
        librelane_runner: Optional LibrelaneRunner instance. Creates a
            default if None.

    Returns:
        Dict mapping tool name strings to callable handlers.
    """
    from cirbuild.librelane.runner import LibrelaneRunner as _LibrelaneRunner
    from cirbuild.memory.rag_store import RAGStore as _RAGStore
    from cirbuild.pipeline.bridge import Spec2RTLBridge
    from cirbuild.workspace.manager import WorkspaceManager as _WorkspaceManager

    bridge = Spec2RTLBridge(settings)
    store = rag_store or _RAGStore()
    workspace = workspace_manager or _WorkspaceManager(settings.workspace_dir)
    runner = librelane_runner or _LibrelaneRunner(settings)

    # ------------------------------------------------------------------
    # Spec parsing
    # ------------------------------------------------------------------

    def handle_parse_spec_to_json(spec_description: str) -> dict:
        """Use the agent's LLM to parse natural language into JSON spec."""
        from litellm import completion as llm_completion

        from cirbuild.pipeline.json_spec import JsonHardwareSpec

        parse_prompt = (
            "Convert the following hardware specification description into a JSON object "
            "with exactly these fields:\n"
            "- module_name (string): The hardware module name\n"
            "- description (string): Brief description of the module\n"
            "- inputs (object): Input signal names mapped to type/width descriptions\n"
            "- outputs (object): Output signal names mapped to type/width descriptions\n"
            "- behavior (string): Detailed behavioral specification\n"
            "- constraints (array of strings): Design constraints\n"
            "- classification (string): One of COMBINATIONAL, SEQUENTIAL_PIPELINE, STATE_MACHINE\n\n"
            "Output ONLY valid JSON, no markdown fences or extra text.\n\n"
            f"Specification:\n{spec_description}"
        )

        try:
            response = llm_completion(
                model=settings.agent_model,
                api_key=_resolve_api_key(settings.agent_model),
                messages=[
                    {
                        "role": "system",
                        "content": "You are a hardware specification parser. Output only valid JSON.",
                    },
                    {"role": "user", "content": parse_prompt},
                ],
                temperature=0.0,
                max_tokens=2048,
                # Do NOT pass response_format — not all providers support it
            )
            content = response.choices[0].message.content
            # Strip markdown fences if present
            if content.strip().startswith("```"):
                content = content.strip()
                content = content.split("\n", 1)[1] if "\n" in content else content
                if content.endswith("```"):
                    content = content[:-3]
            spec_json = json.loads(content)
            # Validate with Pydantic
            validated = JsonHardwareSpec.model_validate(spec_json)
            return {"success": True, "spec_json": validated.model_dump()}
        except Exception as exc:
            logger.error("Failed to parse spec: %s", exc)
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Pipeline execution (with auto-store to RAG + auto-init workspace)
    # ------------------------------------------------------------------

    def handle_run_spec2rtl_pipeline(
        spec_json: dict,
        target_compiler: str | None = None,
    ) -> dict:
        """Run the spec2rtl pipeline with a JSON spec.

        On success, automatically stores artifacts in the RAG memory
        store and initializes the workspace from the synthesis result.
        """
        try:
            artifacts = bridge.run_from_json(spec_json, target_compiler)
            # Auto-store in RAG and auto-init workspace on success
            if artifacts.success:
                store.store_pipeline_artifacts(artifacts)
                if artifacts.rtl_path:
                    workspace.init_from_synthesis(
                        artifacts.rtl_path, artifacts.module_name
                    )
            return {
                "success": artifacts.success,
                "module_name": artifacts.module_name,
                "rtl_path": artifacts.rtl_path,
                "error": artifacts.error_log,
                "rtl_preview": (
                    artifacts.rtl_code[:500] if artifacts.rtl_code else None
                ),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def handle_run_spec2rtl_from_file(
        file_path: str,
        target_compiler: str | None = None,
    ) -> dict:
        """Run the spec2rtl pipeline from a file.

        On success, automatically stores artifacts in the RAG memory
        store and initializes the workspace from the synthesis result.
        """
        try:
            artifacts = bridge.run_from_file(Path(file_path), target_compiler)
            # Auto-store in RAG and auto-init workspace on success
            if artifacts.success:
                store.store_pipeline_artifacts(artifacts)
                if artifacts.rtl_path:
                    workspace.init_from_synthesis(
                        artifacts.rtl_path, artifacts.module_name
                    )
            return {
                "success": artifacts.success,
                "module_name": artifacts.module_name,
                "rtl_path": artifacts.rtl_path,
                "error": artifacts.error_log,
                "rtl_preview": (
                    artifacts.rtl_code[:500] if artifacts.rtl_code else None
                ),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # RAG memory query
    # ------------------------------------------------------------------

    def handle_query_memory(query: str, namespace: str = "all") -> dict:
        """Query the BM25 RAG memory store for relevant chunks."""
        results = store.query(query, namespace=namespace, top_k=5)
        if not results:
            return {"results": [], "message": "No relevant results found."}
        return {
            "results": [
                {
                    "score": round(score, 3),
                    "namespace": chunk.namespace,
                    "text": chunk.text[:300],
                    "metadata": chunk.metadata,
                }
                for score, chunk in results
            ]
        }

    # ------------------------------------------------------------------
    # Workspace file operations
    # ------------------------------------------------------------------

    def handle_read_workspace_file(filename: str) -> dict:
        """Read a file from the active Verilog workspace."""
        try:
            content = workspace.read_file(filename)
            return {"filename": filename, "content": content}
        except (FileNotFoundError, RuntimeError) as exc:
            return {"error": str(exc)}

    def handle_write_workspace_file(filename: str, content: str) -> dict:
        """Write a file to the active Verilog workspace with history."""
        try:
            path = workspace.write_file(filename, content)
            return {"success": True, "path": str(path)}
        except RuntimeError as exc:
            return {"error": str(exc)}

    def handle_list_workspace_files() -> dict:
        """List all files in the active Verilog workspace."""
        try:
            files = workspace.list_files()
            return {"files": files, "active_module": workspace.active_module}
        except RuntimeError as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Librelane integration
    # ------------------------------------------------------------------

    def handle_package_for_librelane(
        module_name: str,
        clock_port: str = "clk",
        clock_period: float = 10.0,
    ) -> dict:
        """Package workspace files for librelane and generate config."""
        try:
            # Create design directory in workspace
            design_dir = settings.workspace_dir / module_name / "librelane_design"

            # Use workspace manager to copy files
            copied = workspace.package_for_librelane(design_dir, module_name)
            if not copied:
                return {"error": f"No .v/.sv files found in workspace for module '{module_name}'."}

            # Generate librelane config
            config_path = runner.generate_config(
                design_dir=design_dir,
                module_name=module_name,
                clock_port=clock_port,
                clock_period=clock_period,
            )

            # Check for existing runs
            existing_runs = runner.check_existing_runs(design_dir)

            result: Dict[str, Any] = {
                "success": True,
                "design_dir": str(design_dir),
                "config_path": str(config_path),
                "files_packaged": [str(f) for f in copied],
            }

            if existing_runs:
                result["existing_runs"] = existing_runs
                result["message"] = (
                    f"Found {len(existing_runs)} existing run(s). "
                    "Use run_librelane_flow to start a new run, or inspect existing results."
                )

            return result
        except Exception as exc:
            return {"error": str(exc)}

    def handle_run_librelane_flow(module_name: str) -> dict:
        """Execute the librelane flow on a packaged design."""
        try:
            design_dir = settings.workspace_dir / module_name / "librelane_design"

            if not design_dir.exists():
                return {
                    "error": f"Design directory not found: {design_dir}. Run package_for_librelane first."
                }

            # Check for existing runs first
            existing_runs = runner.check_existing_runs(design_dir)

            # Run the flow
            result = runner.run_flow(design_dir)

            if result.get("success"):
                # Parse results from the latest run
                runs = runner.check_existing_runs(design_dir)
                if runs:
                    latest = runs[-1]
                    parsed = runner.parse_run_results(Path(latest["path"]))
                    result["parsed_results"] = parsed

            return result
        except Exception as exc:
            return {"error": str(exc)}

    return {
        "parse_spec_to_json": handle_parse_spec_to_json,
        "run_spec2rtl_pipeline": handle_run_spec2rtl_pipeline,
        "run_spec2rtl_from_file": handle_run_spec2rtl_from_file,
        "query_memory": handle_query_memory,
        "read_workspace_file": handle_read_workspace_file,
        "write_workspace_file": handle_write_workspace_file,
        "list_workspace_files": handle_list_workspace_files,
        "package_for_librelane": handle_package_for_librelane,
        "run_librelane_flow": handle_run_librelane_flow,
    }

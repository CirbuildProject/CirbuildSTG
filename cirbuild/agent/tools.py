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
                "name": "scan_workspace",
                "description": (
                    "Scan the cirbuild_workspace directory for existing module directories "
                    "that contain Verilog or SystemVerilog files. "
                    "Use this when the user has manually placed files in the workspace "
                    "and wants the agent to find and work with them without running the pipeline."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "activate_workspace_module",
                "description": (
                    "Activate an existing workspace module by name so the agent can "
                    "read, edit, package, and run librelane on it. "
                    "Use after scan_workspace to select which module to work with."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module_name": {
                            "type": "string",
                            "description": "The module directory name to activate (as returned by scan_workspace).",
                        },
                    },
                    "required": ["module_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "load_verilog_file",
                "description": (
                    "Load an existing Verilog or SystemVerilog file from the local filesystem "
                    "directly into the workspace, bypassing the Spec2RTL pipeline. "
                    "Use this to quickly test or edit an existing RTL file without running the pipeline first."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute or relative path to the .v or .sv file to load.",
                        },
                        "module_name": {
                            "type": "string",
                            "description": (
                                "Optional module name override. "
                                "If not provided, the filename stem is used as the module name."
                            ),
                        },
                    },
                    "required": ["file_path"],
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
            
            module_name = artifacts.module_name or (Path(artifacts.rtl_path).stem if artifacts.rtl_path else "unknown_module")
            # Clean module_name for matching workspace directory and filename
            safe_module_name = (
                str(module_name).strip().lower().replace(" ", "_").replace("-", "_")
            )
            # RTL file will be named {module_name}.v or .sv in the workspace
            rtl_ext = Path(artifacts.rtl_path).suffix if artifacts.rtl_path else ".v"
            clean_filename = f"{safe_module_name}{rtl_ext}"
            # Auto-store in RAG and auto-init workspace on success
            if artifacts.success:
                store.store_pipeline_artifacts(artifacts)
                if artifacts.rtl_path:
                    # Use the calculated module_name (with fallback) to ensure consistency
                    workspace.init_from_synthesis(
                        artifacts.rtl_path, module_name)

            response_dict = {
                "success": artifacts.success,
                "module_name": module_name,
                "rtl_path": artifacts.rtl_path,
                "rtl_filename": clean_filename,
            }

            if artifacts.success:
                response_dict["agent_instruction"] = (
                    f"SUCCESS: The Verilog file '{clean_filename}' is now in the workspace. "
                    f"You MUST use the read_workspace_file tool on '{clean_filename}' to review it before proceeding."
                )
                if artifacts.rtl_code:
                    response_dict["rtl_preview"] = artifacts.rtl_code[:500]
            else:
                response_dict["error"] = artifacts.error_log

            return response_dict
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
            
            module_name = artifacts.module_name or (Path(artifacts.rtl_path).stem if artifacts.rtl_path else "unknown_module")
            # Clean module_name for matching workspace directory and filename
            safe_module_name = (
                str(module_name).strip().lower().replace(" ", "_").replace("-", "_")
            )
            # RTL file will be named {module_name}.v or .sv in the workspace
            rtl_ext = Path(artifacts.rtl_path).suffix if artifacts.rtl_path else ".v"
            clean_filename = f"{safe_module_name}{rtl_ext}"
            # Auto-store in RAG and auto-init workspace on success
            if artifacts.success:
                store.store_pipeline_artifacts(artifacts)
                if artifacts.rtl_path:
                    # Use the calculated module_name (with fallback) to ensure consistency
                    workspace.init_from_synthesis(
                        artifacts.rtl_path, module_name)

            response_dict = {
                "success": artifacts.success,
                "module_name": module_name,
                "rtl_path": artifacts.rtl_path,
                "rtl_filename": clean_filename,
            }

            if artifacts.success:
                response_dict["agent_instruction"] = (
                    f"SUCCESS: The Verilog file '{clean_filename}' is now in the workspace. "
                    f"You MUST use the read_workspace_file tool on '{clean_filename}' to review it before proceeding."
                )
                if artifacts.rtl_code:
                    response_dict["rtl_preview"] = artifacts.rtl_code[:500]
            else:
                response_dict["error"] = artifacts.error_log

            return response_dict

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
        """Read a file from the active Verilog workspace.
        
        Returns file content with the filename and line count for context.
        """
        try:
            content = workspace.read_file(filename)
            lines = content.split('\n')
            
            logger.info("📖 Reading '%s': %d lines", filename, len(lines))
            
            return {
                "filename": filename,
                "content": content,
                "lines": len(lines),
                "preview": content[:500],  # First 500 chars for quick review
            }
        except (FileNotFoundError, RuntimeError) as exc:
            logger.error("Failed to read '%s': %s", filename, exc)
            return {"error": str(exc)}

    def handle_write_workspace_file(filename: str, content: str) -> dict:
        """Write a file to the active Verilog workspace with history.
        
        Saves previous version and logs the edit with detailed change information.
        """
        try:
            # Get previous version if it exists for comparison
            prev_content = None
            prev_lines = 0
            try:
                prev_content = workspace.read_file(filename)
                prev_lines = len(prev_content.split('\n'))
            except FileNotFoundError:
                pass
            
            # Write the new file
            path = workspace.write_file(filename, content)
            new_lines = len(content.split('\n'))
            
            # Calculate change metrics
            change_info = {
                "success": True,
                "path": str(path),
                "new_lines": new_lines,
                "status": "EDITING",  # Clear indicator that file is being modified
            }
            
            if prev_content:
                change_info["previous_lines"] = prev_lines
                change_info["lines_added"] = max(0, new_lines - prev_lines)
                change_info["lines_removed"] = max(0, prev_lines - new_lines)
            else:
                change_info["created"] = True
            
            # Log the edit
            logger.info(
                "✏️ [EDITING] File '%s' modified: %d lines (was %d lines). Status: PENDING REVIEW",
                filename,
                new_lines,
                prev_lines if prev_content else 0
            )
            
            return change_info
        except RuntimeError as exc:
            logger.error("Failed to write '%s': %s", filename, exc)
            return {"error": str(exc)}

    def handle_list_workspace_files() -> dict:
        """List all files in the active Verilog workspace."""
        try:
            files = workspace.list_files()
            return {"files": files, "active_module": workspace.active_module}
        except RuntimeError as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Workspace scanning and activation (for manually placed files)
    # ------------------------------------------------------------------

    def handle_scan_workspace() -> dict:
        """Scan cirbuild_workspace for existing module directories with Verilog files."""
        try:
            modules = workspace.scan_for_modules()
            if not modules:
                return {
                    "modules": [],
                    "message": (
                        f"No Verilog files found in workspace root '{workspace._root}'. "
                        "Place a .v or .sv file inside a subdirectory of the workspace, "
                        "or use load_verilog_file to import one."
                    ),
                }
            return {
                "modules": modules,
                "count": len(modules),
                "agent_instruction": (
                    f"Found {len(modules)} module(s) in the workspace. "
                    "Use activate_workspace_module('<module_name>') to select one and start working with it."
                ),
            }
        except Exception as exc:
            logger.error("Error scanning workspace: %s", exc)
            return {"error": str(exc)}

    def handle_activate_workspace_module(module_name: str) -> dict:
        """Activate an existing workspace module so the agent can work with it."""
        try:
            module_dir = workspace.activate_module(module_name)
            files = workspace.list_files()
            logger.info(
                "🔓 [ACTIVATE] Workspace module '%s' activated. Files: %s",
                module_name,
                files,
            )
            return {
                "success": True,
                "active_module": module_name,
                "workspace_dir": str(module_dir),
                "files": files,
                "agent_instruction": (
                    f"✅ Workspace module '{module_name}' is now active. "
                    f"Files available: {', '.join(files)}. "
                    f"Use read_workspace_file to review the RTL, then package_for_librelane('{module_name}') to prepare for synthesis."
                ),
            }
        except FileNotFoundError as exc:
            return {"error": str(exc)}
        except Exception as exc:
            logger.error("Error activating workspace module: %s", exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Direct Verilog file loader (bypasses pipeline)
    # ------------------------------------------------------------------

    def handle_load_verilog_file(
        file_path: str,
        module_name: str | None = None,
    ) -> dict:
        """Load an existing Verilog/SystemVerilog file into the workspace.

        Copies the file into the workspace and sets it as the active module,
        bypassing the Spec2RTL pipeline entirely. Useful for testing existing
        RTL files directly with librelane.
        """
        try:
            src = Path(file_path)
            if not src.exists():
                return {"error": f"File not found: {file_path}"}

            if src.suffix.lower() not in (".v", ".sv"):
                return {
                    "error": (
                        f"Unsupported file extension '{src.suffix}'. "
                        "Only .v and .sv files are supported."
                    )
                }

            # Use provided module_name or fall back to filename stem
            mod_name = module_name or src.stem

            # Reuse init_from_synthesis — it copies the file and sets active module
            workspace_dir = workspace.init_from_synthesis(str(src), mod_name)

            # Read the file content for display
            content = src.read_text(encoding="utf-8")
            lines = content.split("\n")

            logger.info(
                "📂 [LOAD] Loaded '%s' (%d lines) into workspace as module '%s'",
                src.name,
                len(lines),
                mod_name,
            )

            return {
                "success": True,
                "module_name": mod_name,
                "workspace_dir": str(workspace_dir),
                "filename": f"{mod_name}{src.suffix}",
                "lines": len(lines),
                "rtl_preview": content[:500],
                "agent_instruction": (
                    f"✅ Loaded '{src.name}' into workspace as module '{mod_name}'. "
                    f"The file has {len(lines)} lines. "
                    f"Use read_workspace_file('{mod_name}{src.suffix}') to review the full RTL, "
                    f"then package_for_librelane('{mod_name}') to prepare for synthesis."
                ),
            }
        except Exception as exc:
            logger.error("Failed to load Verilog file: %s", exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Librelane integration
    # ------------------------------------------------------------------

    def handle_package_for_librelane(
        module_name: str,
        clock_port: str = "clk",
        clock_period: float = 10.0,
    ) -> dict:
        """Package workspace files for librelane and generate config.
        
        Displays final RTL code for user review before packaging for synthesis.
        """
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

            # Read and display final RTL code before packaging
            final_rtl_display = ""
            for rtl_file in copied:
                try:
                    rtl_content = rtl_file.read_text(encoding="utf-8")
                    lines = len(rtl_content.split('\n'))
                    logger.info(
                        "🎯 [FINAL RTL] %s: %d lines | Ready for synthesis",
                        rtl_file.name,
                        lines
                    )
                    final_rtl_display += f"\n--- {rtl_file.name} ({lines} lines) ---\n"
                    # Show first and last portions with middle summary
                    rtl_lines = rtl_content.split('\n')
                    if len(rtl_lines) > 20:
                        final_rtl_display += '\n'.join(rtl_lines[:8])
                        final_rtl_display += f"\n... ({len(rtl_lines)-16} lines middle content) ...\n"
                        final_rtl_display += '\n'.join(rtl_lines[-8:])
                    else:
                        final_rtl_display += rtl_content
                except Exception as e:
                    logger.warning("Could not read RTL from %s: %s", rtl_file, e)

            logger.info(
                "📦 [PACKAGING] Module '%s' ready for librelane. Design dir: %s",
                module_name,
                design_dir
            )

            result: Dict[str, Any] = {
                "success": True,
                "design_dir": str(design_dir),
                "config_path": str(config_path),
                "files_packaged": [str(f) for f in copied],
                "files_count": len(copied),
                "status": "PACKAGED",
            }
            
            if final_rtl_display:
                result["final_rtl"] = final_rtl_display
                result["agent_instruction"] = (
                    f"✅ RTL packaging complete for '{module_name}'. Final RTL shown above for review. "
                    f"Configuration saved to: {config_path}. "
                    f"Ready to run librelane flow with: run_librelane_flow('{module_name}')"
                )

            if existing_runs:
                result["existing_runs"] = existing_runs
                result["message"] = (
                    f"Found {len(existing_runs)} existing run(s). "
                    "Use run_librelane_flow to start a new run, or inspect existing results."
                )

            return result
        except Exception as exc:
            logger.error("Error packaging for librelane: %s", exc)
            return {"error": str(exc)}

    def handle_run_librelane_flow(module_name: str) -> dict:
        """Execute the librelane flow on a packaged design.
        
        Captures metrics from the flow execution (via programmatic API or subprocess)
        and routes them to the RAG memory store for agent optimization recommendations.
        """
        try:
            design_dir = settings.workspace_dir / module_name / "librelane_design"

            if not design_dir.exists():
                return {
                    "error": f"Design directory not found: {design_dir}. Run package_for_librelane first."
                }

            # Check for existing runs first
            existing_runs = runner.check_existing_runs(design_dir)

            # Run the flow (hybrid: tries programmatic first, falls back to subprocess)
            logger.info("Executing librelane flow for module '%s'", module_name)
            result = runner.run_flow(design_dir, use_programmatic=True)

            response: Dict[str, Any] = {
                "success": result.get("success", False),
                "method": result.get("method", "unknown"),
                "design_dir": str(design_dir),
            }

            if result.get("success"):
                # Parse results from the latest run
                runs = runner.check_existing_runs(design_dir)
                if runs:
                    latest = runs[-1]
                    parsed = runner.parse_run_results(Path(latest["path"]))
                    response["parsed_results"] = parsed

                # ============================================================
                # NEW: Capture and store metrics in RAG
                # ============================================================
                
                # Collect metrics from different sources
                metrics_text_parts = []
                
                # 1. From programmatic State object (if available)
                if result.get("state_available") and result.get("metrics"):
                    state_metrics = result.get("metrics", {})
                    metrics_text = runner._format_metrics_for_storage(state_metrics, module_name)
                    metrics_text_parts.append(metrics_text)
                
                # 2. From parsed run results
                if response.get("parsed_results"):
                    parsed = response["parsed_results"]
                    if parsed.get("outputs") or parsed.get("metrics"):
                        parts = [f"\n=== Librelane Run Results ==="]
                        
                        if parsed.get("outputs"):
                            parts.append("\nGenerated Outputs:")
                            for output_type, files in parsed["outputs"].items():
                                parts.append(f"  {output_type}: {len(files)} file(s)")
                                if files:
                                    parts.append(f"    → {files[0]}")
                        
                        if parsed.get("metrics"):
                            parts.append("\nExtracted Metrics/Reports:")
                            for report_name, content in parsed["metrics"].items():
                                parts.append(f"  {report_name}: {len(content)} chars")
                                # Add first 500 chars of metric content for analysis
                                if content:
                                    parts.append(f"    {content[:500]}")
                        
                        metrics_text_parts.append("\n".join(parts))
                
                # 3. From subprocess output if available
                if result.get("method") == "subprocess" and result.get("stdout_tail"):
                    parts = [f"\n=== Librelane Subprocess Output ==="]
                    parts.append(result["stdout_tail"][:1000])
                    metrics_text_parts.append("\n".join(parts))
                
                # Store combined metrics in RAG
                if metrics_text_parts:
                    metrics_text = "\n".join(metrics_text_parts)
                    run_tag = (runs[-1]["tag"] if runs else "latest")
                    
                    try:
                        chunks_stored = store.store_librelane_results(
                            metrics_text=metrics_text,
                            module_name=module_name,
                            run_tag=run_tag,
                        )
                        logger.info("Stored %d metric chunks in RAG for module '%s'", chunks_stored, module_name)
                        response["metrics_stored"] = {
                            "chunks": chunks_stored,
                            "run_tag": run_tag,
                            "status": "success",
                        }
                    except Exception as e:
                        logger.error("Failed to store metrics in RAG: %s", e)
                        response["metrics_stored"] = {
                            "status": "failed",
                            "error": str(e),
                        }
                
                # Add agent instruction for optimization
                response["agent_instruction"] = (
                    f"✅ Librelane flow completed successfully for '{module_name}'. "
                    f"Synthesis metrics have been stored in memory. "
                    f"You can now query the metrics using query_memory to optimize the design, "
                    f"or analyze DRC/LVS violations, area, timing, and power. "
                    f"Generated outputs: {', '.join(response.get('parsed_results', {}).get('outputs', {}).keys())}"
                )
            else:
                response["error"] = result.get("error", "Unknown error")
                response["agent_instruction"] = f"❌ Librelane flow failed for '{module_name}'. Please check the error message above."
            
            # Include additional info
            if result.get("return_code"):
                response["return_code"] = result["return_code"]
            if result.get("stderr_tail"):
                response["stderr_tail"] = result["stderr_tail"]
            if result.get("latest_run"):
                response["latest_run"] = result["latest_run"]

            return response
        except Exception as exc:
            logger.error("Error in librelane flow handler: %s", exc)
            return {"error": str(exc), "details": f"Exception: {type(exc).__name__}"}

    return {
        "parse_spec_to_json": handle_parse_spec_to_json,
        "run_spec2rtl_pipeline": handle_run_spec2rtl_pipeline,
        "run_spec2rtl_from_file": handle_run_spec2rtl_from_file,
        "query_memory": handle_query_memory,
        "scan_workspace": handle_scan_workspace,
        "activate_workspace_module": handle_activate_workspace_module,
        "load_verilog_file": handle_load_verilog_file,
        "read_workspace_file": handle_read_workspace_file,
        "write_workspace_file": handle_write_workspace_file,
        "list_workspace_files": handle_list_workspace_files,
        "package_for_librelane": handle_package_for_librelane,
        "run_librelane_flow": handle_run_librelane_flow,
    }

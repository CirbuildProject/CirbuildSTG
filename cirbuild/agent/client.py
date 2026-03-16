"""Cirbuild Agent — dedicated LLM-powered assistant for IC design.

Uses its own LLM API channel (separate from spec2rtl backend) to
provide interactive assistance with hardware specification, RTL
generation, debugging, and physical design flow.
"""

from __future__ import annotations
import os
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

import litellm
from litellm import completion

from cirbuild.config.settings import CirbuildSettings

if TYPE_CHECKING:
    from cirbuild.librelane.runner import LibrelaneRunner
    from cirbuild.memory.rag_store import RAGStore
    from cirbuild.workspace.manager import WorkspaceManager

logger = logging.getLogger("cirbuild.agent")


class CirbuildAgent:
    """Interactive LLM agent for the Cirbuild EDA workflow.

    Maintains conversation history and executes tool calls for
    pipeline invocation, workspace editing, and librelane execution.

    Args:
        settings: CirbuildSTG settings. Loaded from defaults if None.
    """

    @staticmethod
    def _render_system_prompt(user_role: str | None = None) -> str:
        """Render the system prompt from the Jinja2 template.

        Falls back to a hardcoded prompt if the template is unavailable.
        """
        try:
            from jinja2 import Environment, FileSystemLoader

            template_dir = Path(__file__).parent / "prompts"
            env = Environment(loader=FileSystemLoader(str(template_dir)))
            template = env.get_template("system.jinja2")
            return template.render(user_role=user_role)
        except Exception:
            # Fallback if template loading fails
            return (
                "You are Cirbuild, an expert AI assistant for Integrated Circuit design. "
                "You help users design hardware modules by:\n"
                "1. Understanding their hardware specifications\n"
                "2. Running the Spec2RTL pipeline to generate RTL code\n"
                "3. Helping debug and edit the generated Verilog/SystemVerilog\n"
                "4. Running the Librelane physical design flow for GDSII generation\n\n"
                "You have access to tools for pipeline execution, workspace management, "
                "and memory retrieval. Use them when appropriate.\n\n"
                "When a user describes a hardware module, use the parse_spec_to_json tool "
                "to structure their description, then run_spec2rtl_pipeline to generate RTL.\n\n"
                "Be concise, technical, and helpful. When showing code, use proper formatting."
            )

    def __init__(self, settings: CirbuildSettings | None = None) -> None:
        self._settings = settings or CirbuildSettings.from_yaml()
        self._system_prompt = self._render_system_prompt()
        self._history: List[dict] = [
            {"role": "system", "content": self._system_prompt}
        ]
        self._tools: List[dict] = []
        self._tool_handlers: Dict[str, Callable] = {}

        # Phase 3: RAG memory store and workspace manager
        from cirbuild.memory.rag_store import RAGStore as _RAGStore
        from cirbuild.workspace.manager import WorkspaceManager as _WorkspaceManager

        self._rag_store: RAGStore = _RAGStore()
        self._workspace: WorkspaceManager = _WorkspaceManager(
            self._settings.workspace_dir
        )

        # Phase 4: Librelane runner
        from cirbuild.librelane.runner import LibrelaneRunner as _LibrelaneRunner

        self._librelane: LibrelaneRunner = _LibrelaneRunner(self._settings)

        self._setup_default_tools()

    @property
    def rag_store(self) -> RAGStore:
        """The agent's BM25 RAG memory store."""
        return self._rag_store

    @property
    def workspace(self) -> WorkspaceManager:
        """The agent's Verilog workspace manager."""
        return self._workspace

    @property
    def librelane(self) -> LibrelaneRunner:
        """The agent's Librelane flow runner."""
        return self._librelane

    def _setup_default_tools(self) -> None:
        """Register the default tool definitions and handlers.

        Passes the RAG store, workspace manager, and librelane runner
        to the tool handlers so that all tools use real implementations.
        """
        from cirbuild.agent.tools import get_tool_definitions, get_tool_handlers

        self._tools = get_tool_definitions()
        self._tool_handlers = get_tool_handlers(
            self._settings,
            rag_store=self._rag_store,
            workspace_manager=self._workspace,
            librelane_runner=self._librelane,
        )

    def register_tool(
        self,
        definition: dict,
        handler: Callable,
    ) -> None:
        """Register an additional tool for the agent.

        Args:
            definition: OpenAI-format tool definition dict.
            handler: Callable that executes the tool.
        """
        self._tools.append(definition)
        name = definition["function"]["name"]
        self._tool_handlers[name] = handler

    def chat(self, user_message: str) -> str:
        """Send a message and get the agent's response.

        Handles the tool-calling loop: if the LLM returns tool calls,
        executes them and feeds results back until a text response is produced.

        Args:
            user_message: The user's input message.

        Returns:
            The agent's text response.
        """
        self._history.append({"role": "user", "content": user_message})

        max_tool_rounds = 5  # Prevent infinite tool-calling loops

        for round_num in range(max_tool_rounds):
            logger.info("🔄 Tool-calling round %d/%d", round_num + 1, max_tool_rounds)
            response = self._call_llm()

            message = response.choices[0].message

            # If no tool calls, return the text response
            if not message.tool_calls:
                assistant_content = message.content or ""
                self._history.append(
                    {"role": "assistant", "content": assistant_content}
                )
                logger.info("✅ Agent returned text response in round %d", round_num + 1)
                return assistant_content

            logger.info("📞 Agent made %d tool call(s) in round %d", len(message.tool_calls), round_num + 1)

            # Process tool calls
            # Build a clean assistant message with only standard fields
            tool_calls_data = None
            if message.tool_calls:
                tool_calls_data = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]

            assistant_msg = {"role": "assistant", "content": message.content or ""}
            if tool_calls_data:
                assistant_msg["tool_calls"] = tool_calls_data
            self._history.append(assistant_msg)

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                logger.info("🔧 Tool call: %s(%s)", tool_name, tool_args)

                # Execute the tool
                result = self._execute_tool(tool_name, tool_args)

                # Log tool execution result
                if isinstance(result, dict) and "error" in result:
                    logger.error("❌ Tool %s returned error: %s", tool_name, result["error"])
                else:
                    logger.info("✅ Tool %s executed successfully", tool_name)

                # Add tool result to history
                self._history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": (
                            json.dumps(result)
                            if isinstance(result, dict)
                            else str(result)
                        ),
                    }
                )

        # If we exhausted tool rounds, return what we have
        return "[Agent reached maximum tool-calling rounds. Please try again.]"

    @staticmethod
    def _resolve_api_key(model: str) -> str | None:
        """Resolve the correct API key for a given model string.

        Inspects the model prefix to select the appropriate provider key
        from the environment. This allows the agent to use different
        providers for primary and fallback models without coupling to a
        single API key.

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

    def _call_llm(self) -> Any:
        """Make an LLM API call with the current history and tools.

        Uses the agent's dedicated LLM configuration, NOT the spec2rtl backend's.
        Dynamically swaps the API key based on the active model's provider prefix
        so that fallback models can use a different provider without extra config.

        Returns:
            The litellm completion response.
        """
        kwargs: dict[str, Any] = {
            "model": self._settings.agent_model,
            "api_key": self._resolve_api_key(self._settings.agent_model),
            "messages": self._history,
            "temperature": self._settings.agent_temperature,
            "max_tokens": self._settings.agent_max_tokens,
        }

        if self._tools:
            kwargs["tools"] = self._tools
            kwargs["tool_choice"] = "auto"

        try:
            return completion(**kwargs)
        except Exception as exc:
            # Try fallback models — swap the API key for each provider
            for fallback in self._settings.agent_fallback_models:
                try:
                    kwargs["model"] = fallback
                    kwargs["api_key"] = self._resolve_api_key(fallback)
                    logger.warning("Falling back to model: %s", fallback)
                    return completion(**kwargs)
                except Exception:
                    continue
            raise RuntimeError(
                f"All agent LLM models failed. Last error: {exc}"
            ) from exc

    def _execute_tool(self, name: str, args: dict) -> Any:
        """Execute a registered tool by name.

        Args:
            name: Tool function name.
            args: Tool arguments dict.

        Returns:
            Tool execution result.
        """
        handler = self._tool_handlers.get(name)
        if handler is None:
            return {"error": f"Unknown tool: {name}"}

        try:
            return handler(**args)
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc)
            return {"error": f"Tool execution failed: {str(exc)}"}

    def get_history(self) -> List[dict]:
        """Return the conversation history."""
        return list(self._history)

    def clear_history(self) -> None:
        """Clear conversation history, keeping only the system prompt."""
        self._history = [{"role": "system", "content": self._system_prompt}]

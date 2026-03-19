"""CLI chat loop for the Cirbuild agent.

Provides an interactive terminal interface with /command dispatch
and natural language routing to the LLM agent.
"""

import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from cirbuild.agent.client import CirbuildAgent
from cirbuild.config.settings import CirbuildSettings

logger = logging.getLogger("cirbuild.cli")
console = Console()


def print_welcome() -> None:
    """Display the welcome banner."""
    console.print(
        Panel(
            "[bold cyan]Cirbuild[/bold cyan] — AI-Powered IC Design Assistant\n"
            "[dim]Spec-to-GDSII Electronic Design Automation[/dim]\n\n"
            "Type your hardware specification or use /help for commands.\n"
            "Type /quit to exit.",
            title="🔧 CirbuildSTG v0.1",
            border_style="cyan",
        )
    )


def print_help() -> None:
    """Display available commands."""
    help_text = """
**Available Commands:**

| Command | Description |
|---------|-------------|
| `/spec <file>` | Load a spec file (PDF, TXT, JSON) and run pipeline |
| `/load <file> [module_name]` | Load an existing .v/.sv file directly into workspace (no pipeline) |
| `/workspace` | List files in the Verilog workspace |
| `/edit <file>` | Show a workspace file for discussion |
| `/package <module>` | Package workspace for Librelane |
| `/run-librelane <module>` | Execute the Librelane flow |
| `/status` | Show current session status |
| `/clear` | Clear conversation history |
| `/help` | Show this help message |
| `/quit` | Exit Cirbuild |

Or just type naturally to chat with the agent!
"""
    console.print(Markdown(help_text))


def handle_command(command: str, agent: CirbuildAgent) -> bool:
    """Handle a /command input.

    Args:
        command: The command string (without the leading /).
        agent: The active CirbuildAgent instance.

    Returns:
        True if the CLI should continue, False to exit.
    """
    parts = command.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in ("quit", "exit"):
        console.print("[dim]Goodbye![/dim]")
        return False

    elif cmd == "help":
        print_help()

    elif cmd == "clear":
        agent.clear_history()
        console.print("[dim]Conversation history cleared.[/dim]")

    elif cmd == "status":
        history_len = len(agent.get_history()) - 1  # Exclude system prompt
        console.print(f"[dim]Session messages: {history_len}[/dim]")

    elif cmd == "spec":
        if not arg:
            console.print("[red]Usage: /spec <file_path>[/red]")
        else:
            file_path = Path(arg)
            if not file_path.exists():
                console.print(f"[red]File not found: {file_path}[/red]")
            else:
                console.print(f"[dim]Loading spec from {file_path}...[/dim]")
                # Route through agent for proper tool handling
                response = agent.chat(
                    f"Run the Spec2RTL pipeline on this file: {file_path}"
                )
                console.print(Markdown(response))

    elif cmd == "load":
        if not arg:
            console.print("[red]Usage: /load <file_path> [module_name][/red]")
        else:
            load_parts = arg.split(maxsplit=1)
            verilog_path = Path(load_parts[0])
            module_override = load_parts[1] if len(load_parts) > 1 else ""
            if not verilog_path.exists():
                console.print(f"[red]File not found: {verilog_path}[/red]")
            else:
                console.print(
                    f"[dim]Loading Verilog file '{verilog_path}' directly into workspace...[/dim]"
                )
                msg = f"Load this Verilog file directly into the workspace: {verilog_path.resolve()}"
                if module_override:
                    msg += f" Use module name: {module_override}"
                response = agent.chat(msg)
                console.print(Markdown(response))

    elif cmd == "workspace":
        response = agent.chat("List all files in the workspace.")
        console.print(Markdown(response))

    elif cmd == "edit":
        if not arg:
            console.print("[red]Usage: /edit <filename>[/red]")
        else:
            response = agent.chat(
                f"Show me the contents of workspace file: {arg}"
            )
            console.print(Markdown(response))

    elif cmd == "package":
        if not arg:
            console.print("[red]Usage: /package <module_name>[/red]")
        else:
            response = agent.chat(
                f"Package the workspace files for Librelane with module name: {arg}"
            )
            console.print(Markdown(response))

    elif cmd == "run-librelane":
        if not arg:
            console.print("[red]Usage: /run-librelane <module_name>[/red]")
        else:
            response = agent.chat(
                f"Run the Librelane physical design flow for module: {arg}"
            )
            console.print(Markdown(response))

    else:
        console.print(
            f"[red]Unknown command: /{cmd}. Type /help for available commands.[/red]"
        )

    return True


def run_cli(config_path: Path | None = None) -> None:
    """Run the interactive CLI chat loop.

    Args:
        config_path: Optional path to a CirbuildSTG config YAML.
    """
    settings = CirbuildSettings.from_yaml(config_path)
    agent = CirbuildAgent(settings)

    print_welcome()

    while True:
        try:
            user_input = console.input("[bold green]You>[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        # Command dispatch
        if user_input.startswith("/"):
            should_continue = handle_command(user_input[1:], agent)
            if not should_continue:
                break
            continue

        # Regular message — route to agent
        console.print("\n[dim italic] Cirbuild is processing...[/dim italic]")
        try:
            response = agent.chat(user_input)
        except Exception as exc:
            console.print(f"[red]Agent error: {exc}[/red]")
            continue

        console.print()
        console.print(
            Panel(
                Markdown(response),
                title="[bold cyan]Cirbuild[/bold cyan]",
                border_style="cyan",
            )
        )
        console.print()

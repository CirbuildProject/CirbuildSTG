"""CLI entry point for CirbuildSTG.

Usage:
    python -m cirbuild              # Start interactive chat
    python -m cirbuild --config custom.yaml
"""

import argparse
import sys
import logging
import litellm
from pathlib import Path


def main() -> int:
    """Parse CLI arguments and launch the Cirbuild agent."""
    logging.basicConfig(level=logging.INFO, format="[dim]%(message)s[/dim]")
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    litellm.suppress_debug_info = True
    parser = argparse.ArgumentParser(
        prog="cirbuild",
        description="CirbuildSTG — AI-Powered Spec-to-GDSII IC Design Assistant",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a CirbuildSTG configuration YAML file.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit.",
    )

    args = parser.parse_args()

    if args.version:
        from cirbuild import __version__

        print(f"CirbuildSTG v{__version__}")
        return 0

    from cirbuild.cli import run_cli

    run_cli(config_path=args.config)
    return 0


if __name__ == "__main__":
    sys.exit(main())

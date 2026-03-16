"""CirbuildSTG configuration management.

Manages settings for the Cirbuild agent client, completely separate
from the spec2rtl backend configuration. The agent has its own LLM
API channel, workspace paths, and librelane integration settings.
"""

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


_DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.yaml"


def _load_yaml_config(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class CirbuildSettings(BaseSettings):
    """Application-wide settings for the Cirbuild agent client.

    Values are resolved in this priority order (highest wins):
    1. Environment variables (prefixed with CIRBUILD_)
    2. Values passed directly to the constructor
    3. YAML config file values
    4. Defaults defined below
    """

    # --- Agent LLM Configuration (SEPARATE from spec2rtl backend) ---
    agent_model: str = Field(
        default="openrouter/minimax/minimax-m2.5",
        description="LLM model for the Cirbuild agent (LiteLLM format).",
    )
    agent_fallback_models: List[str] = Field(
        default_factory=lambda: [
            "openrouter/google/gemini-2.5-flash",
        ],
        description="Fallback models for the agent.",
    )
    agent_temperature: float = Field(
        default=0.3,
        description="Temperature for agent LLM completions.",
    )
    agent_max_tokens: int = Field(
        default=4096,
        description="Maximum output tokens for agent completions.",
    )

    # --- Workspace ---
    workspace_dir: Path = Field(
        default=Path("cirbuild_workspace"),
        description="Root directory for the Verilog editing workspace.",
    )

    # --- Librelane ---
    librelane_repo_path: Path = Field(
        default=Path("../librelane"),
        description="Path to the librelane repository.",
    )
    librelane_pdk_root: str = Field(
        default="~/.ciel",
        description="PDK root directory for librelane.",
    )
    librelane_pdk: str = Field(
        default="sky130A",
        description="Target PDK for librelane flow.",
    )

    # --- Spec2RTL Backend ---
    spec2rtl_config_path: Optional[Path] = Field(
        default=None,
        description="Path to spec2rtl config YAML. Uses spec2rtl defaults if None.",
    )

    model_config = {
        "env_prefix": "CIRBUILD_",
        "env_nested_delimiter": "__",
    }

    @classmethod
    def from_yaml(cls, config_path: Path | None = None) -> "CirbuildSettings":
        import os
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        path = config_path or _DEFAULT_CONFIG_PATH
        yaml_values = _load_yaml_config(path)

        env_prefix = cls.model_config.get("env_prefix", "CIRBUILD_")
        filtered: dict = {}
        for key, value in yaml_values.items():
            env_key = f"{env_prefix}{key.upper()}"
            if env_key not in os.environ:
                filtered[key] = value

        return cls(**filtered)

# CirbuildSTG — Tech Stack Documentation

> Accurate as of v0.1.0. Cross-referenced against `pyproject.toml`, `requirements.txt`, and source code.

---

## Overview

CirbuildSTG is an agentic AI EDA assistant that orchestrates two external subsystems — an RTL generation backend (Cirbuild-Spec2RTL) and a physical design flow (Librelane/OpenLane) — through a single conversational CLI interface. The architecture is deliberately split into:

1. **Frontend agent** — conversational LLM loop with tool-calling, workspace management, and session memory
2. **RTL backend** — delegated to the `Cirbuild-Spec2RTL` package (separate process, separate API keys, separate config)
3. **Physical design** — delegated to Librelane via a Nix-shell subprocess bridge

---

## Core Dependencies

### From `pyproject.toml`

```toml
litellm>=1.0.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
pyyaml>=6.0
python-dotenv>=1.0.0
jinja2>=3.0.0
rich>=13.0.0
```

### From `requirements.txt` (additionally installs)

```
git+https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git@main
```

The Spec2RTL backend is an installable git dependency — not a local submodule. The launch scripts use `--force-reinstall --no-cache-dir` to always pull the latest commit.

---

## Component Deep-Dives

### 1. LiteLLM — Agent LLM Interface

**File:** `cirbuild/agent/client.py`

LiteLLM provides a unified completion API across 100+ LLM providers. CirbuildSTG uses it for the **conversational agent only** — the RTL backend has its own separate LiteLLM instance with different keys.

**Configuration** (`cirbuild/config/default_config.yaml`):
```yaml
agent_model: "openrouter/minimax/minimax-m2.5"
agent_fallback_models:
  - "openrouter/google/gemini-2.5-flash"
  - "openrouter/deepseek/deepseek-v3.2"
agent_temperature: 0.3
agent_max_tokens: 8192
```

**API key routing** — the agent selects the correct key based on the model prefix:

| Model prefix | Key used |
|---|---|
| `openrouter/*` | `CIRBUILD_OPENROUTER_KEY` |
| `gemini/*` | `CIRBUILD_GEMINI_KEY` |
| `anthropic/*` | `CIRBUILD_ANTHROPIC_KEY` |

**Tool-calling loop** (`cirbuild/agent/client.py`):

The agent runs a ReAct-style loop — completion → parse tool calls → execute tools → append results → repeat — up to `max_rounds` (default: 15):

```python
for round in range(max_rounds):
    response = litellm.completion(model, messages, tools=tools)
    if not response.tool_calls:
        return response.content          # Final answer
    for call in response.tool_calls:
        result = execute_tool(call.name, call.args)
        messages.append(tool_result(result))
```

**Dual LLM isolation:** The agent uses `CIRBUILD_*` keys. The Spec2RTL backend uses `SPEC2RTL_*` keys. This prevents frontend chat from depleting the backend's rate-limit quota.

---

### 2. Pydantic — Data Validation

**Files:** `cirbuild/pipeline/json_spec.py`, `cirbuild/config/settings.py`

#### `JsonHardwareSpec` — Spec2RTL input validation

All hardware specifications produced by the agent are validated against this schema before being passed to the backend:

```python
class JsonHardwareSpec(BaseModel):
    module_name: str
    description: str
    inputs: Dict[str, str]        # signal_name → type/width
    outputs: Dict[str, str]       # signal_name → type/width
    behavior: str
    constraints: List[str]
    classification: Literal[
        "COMBINATIONAL",
        "SEQUENTIAL_PIPELINE",
        "STATE_MACHINE"
    ]
```

This prevents malformed specs from reaching the expensive multi-stage LLM pipeline.

#### `CirbuildSettings` — Application configuration

```python
class CirbuildSettings(BaseSettings):
    agent_model: str = "openrouter/minimax/minimax-m2.5"
    agent_fallback_models: List[str] = [...]
    agent_temperature: float = 0.3
    agent_max_tokens: int = 8192
    workspace_dir: Path = Path("cirbuild_workspace")
    librelane_repo_path: str = "../librelane"
    librelane_pdk_root: str = "~/.ciel"
    librelane_pdk: str = "sky130A"
    spec2rtl_config_path: Optional[Path] = None

    model_config = {"env_prefix": "CIRBUILD_"}
```

**Priority:** env vars (`CIRBUILD_*`) → YAML config → field defaults.

---

### 3. BM25 RAG Store — Session Memory

**File:** `cirbuild/memory/rag_store.py`

CirbuildSTG uses a **custom in-memory BM25 implementation** for session-scoped retrieval of pipeline artifacts. There are no external embedding models, no vector databases, and no network calls.

**Why BM25 over embeddings?**
- Hardware keywords (signal names, pragma strings, module names) match better with exact keyword retrieval than semantic similarity
- Zero setup — works out of the box, no API keys or services needed
- Session-scoped: rebuilt fresh each run, so memory is always relevant to the current design

**BM25 parameters:**
- `k1 = 1.5` — Term frequency saturation
- `b = 0.75` — Document length normalization
- Chunk size: 500 characters, 100 character overlap

**Namespaces:**

| Namespace | Content |
|---|---|
| `spec` | Hardware specifications (natural language + structured JSON) |
| `pseudocode` | Module 1/2 design plans from the RTL pipeline |
| `rtl` | Generated Verilog/SystemVerilog code |
| `metrics` | Physical design results (area, timing, power) |

**Usage in agent tools:**
```python
# Store artifacts after pipeline runs
store.store_pipeline_artifacts(artifacts)

# Query from any tool
results = store.query("ALU XOR operation", namespace="rtl", top_k=5)
```

---

### 4. WorkspaceManager — File Editing with History

**File:** `cirbuild/workspace/manager.py`

Manages Verilog/RTL files in the `cirbuild_workspace/` directory. Every write creates an automatic version snapshot.

**Directory structure:**
```
cirbuild_workspace/
└── <module_name>/
    ├── <module_name>.v          # Active RTL file
    ├── <module_name>_tb.v       # Testbench (if generated)
    └── .history/
        ├── 001_<module_name>.v  # Snapshot before edit 1
        ├── 002_<module_name>.v  # Snapshot before edit 2
        └── ...
```

**Security:** Path traversal protection is enforced on every file operation:
```python
def _safe_path(self, filename: str) -> Path:
    resolved = (module_dir / filename).resolve()
    if not resolved.is_relative_to(module_dir):
        raise ValueError(f"Path traversal detected: {filename!r}")
    return resolved
```

---

### 5. Spec2RTL Bridge

**File:** `cirbuild/pipeline/bridge.py`

The bridge validates input, invokes the Spec2RTL pipeline, and captures its artifacts for RAG storage.

```python
class Spec2RTLBridge:
    def run_from_json(self, spec: JsonHardwareSpec) -> dict:
        # 1. Validate spec (already done by Pydantic)
        # 2. Convert to dict and pass to pipeline.run_from_json()
        result = pipeline.run_from_json(spec.model_dump())
        # 3. Capture RTL path, logs, and summary for workspace + RAG
        return artifacts
```

The Spec2RTL pipeline itself is a separate package with its own 4+1 module architecture. See the [Cirbuild-Spec2RTL README](https://github.com/CirbuildProject/Cirbuild-Spec2RTL) for its internal details.

---

### 6. Librelane — Physical Design Flow

**Files:** `cirbuild/librelane/runner.py`, `cirbuild/librelane/nix_bridge.py`

#### Runner (`runner.py`)

`LibrelaneRunner` builds the Nix-shell invocation, writes a Librelane config JSON, and launches the bridge script as a subprocess:

```
Host Python → nix-shell <shell.nix> --run "python nix_bridge.py <design_dir> <config_path>"
```

Results are written to `librelane_result.json` by the bridge and read back by the runner.

**Timeout:** 1 hour per physical design run.

#### Nix Bridge (`nix_bridge.py`)

Runs inside the Nix shell where EDA binaries are available. Imports `librelane.flows.Flow` and executes the Classic flow, then serializes results to JSON for the host process.

**Required by runner:**
```
nix-shell (on PATH)
LIBRELANE_DIR pointing to the librelane repository (contains shell.nix)
```

**Environment variables passed to the Nix shell:**

| Variable | Description | Default |
|---|---|---|
| `LIBRELANE_DIR` | Path to librelane repo | `../librelane` (from config) |
| `LIBRELANE_PDK` | Target PDK name | `sky130A` |
| `LIBRELANE_PDK_ROOT` | PDK root directory | `~/.ciel` |
| `LIBRELANE_TAG` | Run tag name | (optional) |
| `LIBRELANE_FRM` | Start from this step | (optional) |
| `LIBRELANE_TO` | Stop after this step | (optional) |
| `LIBRELANE_OVERWRITE` | Overwrite existing runs | (optional) |

**Supported PDKs:** sky130A (SkyWater 130nm), gf180mcuD (GlobalFoundries 180nm).

#### Nix Installation (if not already installed)

```bash
curl -L https://nixos.org/nix/install | sh
```

**Common Librelane issues:**

| Issue | Solution |
|---|---|
| `nix-shell: command not found` | Install Nix (command above) |
| `shell.nix not found` | Check `LIBRELANE_DIR` / `librelane_repo_path` in config |
| PDK not found | Verify `LIBRELANE_PDK_ROOT` contains PDK files |

---

### 7. Rich — Terminal UI

**File:** `cirbuild/cli.py`

Rich provides the interactive terminal experience:

| Feature | Usage |
|---|---|
| `Console.input()` | Colored interactive prompt |
| `Panel` | Bordered message boxes for tool results |
| `Markdown` | Rendered Markdown in agent responses |
| `Text` / `Style` | Colored role labels (`You>`, `Cirbuild>`) |

---

### 8. Jinja2 — Agent Prompt Templating

**File:** `cirbuild/agent/prompts/system.jinja2`

The agent's system prompt is rendered from a Jinja2 template at startup. The template defines:
- Agent persona and project context
- Available tool descriptions and usage patterns
- Workflow guidance (when to use which tools)
- Formatting expectations for structured outputs

Keeping prompts in version-controlled templates (rather than hardcoded strings) makes them easy to iterate without touching Python logic.

---

## Architecture Patterns

### Dual LLM Channels

```
User request
     │
     ▼
CirbuildAgent (CIRBUILD_* keys, agent_model)
     │ tool call: run_spec2rtl_pipeline
     ▼
Spec2RTLBridge
     │ invokes
     ▼
Spec2RTL Pipeline (SPEC2RTL_* keys, default_model)
```

The two channels have independent API keys, rate limits, models, and temperatures. This means a long RTL generation run does not block the conversational interface.

### Config Resolution Order

For every setting, this priority chain applies (highest wins):

```
Environment variable (CIRBUILD_*) 
    → Constructor argument
        → YAML config file (cirbuild/config/default_config.yaml)
            → Pydantic field default
```

---

## Docker & Nix Integration

### Google XLS Docker Image (`cirbuild-xls:v1`)

Used by the Spec2RTL backend for HLS synthesis. Must be present before running the RTL pipeline.

```bash
# Pull pre-built (fastest)
docker pull cirbuildproject/cirbuild-xls:v1
docker tag cirbuildproject/cirbuild-xls:v1 cirbuild-xls:v1

# Or build from source (15 min – several hours via Bazel)
docker build -t cirbuild-xls:v1 .
```

**Contents:** Google XLS compiled via Bazel, required system libraries, Python runtime for XLS scripts.

### Librelane Nix Shell

EDA tools (OpenROAD, Yosys, Magic, Netgen) are brought in via Nix, not pip. The `shell.nix` in the librelane repository defines the reproducible environment.

```
Host Python → subprocess: nix-shell → nix_bridge.py → librelane → GDSII
```

---

## Extending CirbuildSTG

### Adding a New Agent Tool

**1.** Define tool schema in `cirbuild/agent/tools.py`:
```python
{
    "type": "function",
    "function": {
        "name": "my_new_tool",
        "description": "What this tool does",
        "parameters": {
            "type": "object",
            "properties": {
                "arg1": {"type": "string", "description": "..."}
            },
            "required": ["arg1"]
        }
    }
}
```

**2.** Implement the handler in the same file:
```python
def handle_my_new_tool(self, arg1: str) -> dict:
    # Implementation
    return {"result": "..."}
```

**3.** Register in `get_tool_handlers()`:
```python
return {
    ...,
    "my_new_tool": self.handle_my_new_tool,
}
```

### Adding a New LLM Provider

LiteLLM handles provider registration automatically. Add the key to `.env`:
```bash
CIRBUILD_OPENROUTER_KEY="your-key"
CIRBUILD_AGENT_MODEL="openrouter/new-provider/model-name"
```

No code changes required.

---

## Security Notes

- **Path traversal protection** — enforced in `WorkspaceManager._safe_path()`
- **API keys** — stored in `.env` (not git-tracked); separate keys per provider and per channel
- **Subprocess isolation** — Librelane EDA tools run in a Nix-shell child process, isolated from the host Python environment

---

## Performance Notes

- BM25 store is in-memory — fast for typical session artifact volumes
- Tool-calling loop caps at 15 rounds to prevent runaway API spend
- Librelane timeout: 1 hour per physical design run
- Spec2RTL pipeline timeout: governed by `max_reflection_cycles` (default: 3) × per-module LLM latency

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `cirbuild: command not found` | Run `pip install -e .` inside the active venv |
| LiteLLM rate limit errors | Add fallback models or use `start.sh` to reinstall with latest config |
| Librelane not found | Ensure Nix is installed and `LIBRELANE_DIR` points to the librelane repo |
| Docker: `cirbuild-xls:v1` not found | Run `docker pull cirbuildproject/cirbuild-xls:v1 && docker tag ...` |
| Stale Spec2RTL version | Run `./start.sh` or manually: `pip install --force-reinstall --no-cache-dir git+...@main` |

---

## Further Reading

- [LiteLLM Documentation](https://docs.litellm.ai/)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/)
- [OpenLane/OpenROAD Documentation](https://openlane.readthedocs.io/)
- [Google XLS Documentation](https://google.github.io/xls/)
- [Rich Library](https://rich.readthedocs.io/)
- [Cirbuild-Spec2RTL README](https://github.com/CirbuildProject/Cirbuild-Spec2RTL)

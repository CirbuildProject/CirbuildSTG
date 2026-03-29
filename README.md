# CirbuildSTG

> *An agentic AI EDA assistant that takes a natural-language hardware specification and walks it all the way to a GDSII layout — giving students and engineers a guided, learn-while-building IC design experience.*

[![License](https://img.shields.io/badge/License-MIT-4CAF50?style=flat-square)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
![Version](https://img.shields.io/badge/version-0.1.0-007EC6?style=flat-square)

---

## 📌 Overview & Motivation

Modern IC design requires mastering a multi-tool, multi-language stack (HDL → RTL → synthesis → place-and-route → GDSII) that takes years to learn. The standard pedagogical approach drops students at the deep end with disconnected tools and no high-level guidance.

CirbuildSTG orchestrates the complete pre-silicon workflow through a single conversational interface. The user describes what they want in plain English; the system decomposes the request, generates RTL via the [Cirbuild-Spec2RTL](https://github.com/CirbuildProject/Cirbuild-Spec2RTL) backend, manages the workspace, and can submit the resulting Verilog directly to a physical design flow via [Librelane](https://github.com/CirbuildProject/librelane) (OpenLane/OpenROAD). It is a **Proof of Concept** for AI-accelerated, top-down IC pedagogy.

**The name stands for:** *Circuit Builder — Spec-To-GDSII.*

### System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      CirbuildSTG                        │
│                                                         │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ CLI Chat │───►│ Cirbuild     │───►│ RAG Memory   │  │
│  │ Loop     │◄───│ Agent (LLM)  │◄───│ Store (BM25) │  │
│  └──────────┘    └──────┬───────┘    └──────────────┘  │
│                         │                               │
│         ┌───────────────┼───────────────┐               │
│         ▼               ▼               ▼               │
│  ┌────────────┐  ┌────────────┐  ┌────────────────┐    │
│  │ Spec2RTL   │  │ Workspace  │  │ Librelane      │    │
│  │ Bridge     │  │ Manager    │  │ Runner         │    │
│  └─────┬──────┘  └────────────┘  └───────┬────────┘    │
│        │                                 │              │
└────────┼─────────────────────────────────┼──────────────┘
         ▼                                 ▼
   ┌──────────────┐                  ┌──────────────┐
   │ Cirbuild-    │                  │ Librelane    │
   │ Spec2RTL     │                  │ (OpenLane/   │
   │ (backend)    │                  │  OpenROAD)   │
   └──────────────┘                  └──────────────┘
```

---

## 🏗️ Key Design Decisions & Trade-offs

**1. Two independent LLM channels — agent vs. backend.**
The conversational agent (`CIRBUILD_*` keys) and the RTL generation pipeline (`SPEC2RTL_*` keys) use completely separate LiteLLM configurations. This prevents rate-limit conflicts where a long synthesis run would starve the chat interface, and allows using different models optimised for different tasks (e.g., a conversational model for the agent, a high-context reasoning model for code generation). The trade-off is requiring two sets of API keys.

**2. Custom BM25 RAG instead of an embedding model.**
Session-scoped memory retrieval uses an in-process BM25 implementation rather than an external vector database or embedding API. This avoids adding an embedding service dependency (cost, latency, setup friction) and is well-suited to hardware jargon where exact signal names and keywords matter more than semantic similarity. The limitation is that BM25 does not generalize across sessions — it is rebuilt fresh each time.

**3. Subprocess isolation for Librelane (Nix-shell bridge).**
Librelane and its EDA tool chain (OpenROAD, Yosys, Magic) are managed inside a Nix-shell environment rather than being pip-installable. The Nix-shell bridge (`cirbuild/librelane/nix_bridge.py`) is spawned as a child process, keeping host Python free of EDA binary dependencies. This avoids dependency hell but requires Nix to be installed on the host system.

---

## 🚦 Project Status

- [x] **Completed:** Interactive CLI chat loop with `/command` dispatch and Rich terminal rendering
- [x] **Completed:** LLM agent with 12 tool-calling capabilities (spec parsing, workspace management, pipeline invocation, Librelane)
- [x] **Completed:** Spec2RTL bridge — structured JSON spec validation (Pydantic) → pipeline invocation → artifact capture
- [x] **Completed:** Workspace manager with automatic version history snapshots and path traversal protection
- [x] **Completed:** Session-scoped BM25 RAG store over pipeline artifacts (specs, pseudocode, RTL, metrics)
- [x] **Completed:** Librelane subprocess runner with Nix-shell bridge and configurable PDK (sky130A, gf180mcuD)
- [x] **Completed:** Dual LLM channel isolation (agent vs. backend, separate API keys and rate-limit budgets)
- [x] **Completed:** Cirbuild-Spec2RTL backend as installable git dependency (auto-updated via launch scripts)
- [ ] **In Progress:** Full end-to-end Spec → GDSII integration testing
- [ ] **Planned:** Advisor/Supervisor human-in-the-loop intercept agent
- [ ] **Planned:** Streamlit/Gradio GUI front-end replacing the CLI

---

## 🛠️ Tech Stack

| Component | Library / Tool | Version | Role |
|---|---|---|---|
| **Agent LLM** | [LiteLLM](https://docs.litellm.ai/) | `>=1.0.0` | Unified API for OpenRouter, Gemini, Anthropic, and others |
| **Data Validation** | [Pydantic](https://docs.pydantic.dev/) v2 | `>=2.0.0` | Schema validation for hardware specs (`JsonHardwareSpec`) and settings |
| **Settings** | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | `>=2.0.0` | YAML + `CIRBUILD_` env-var overrides |
| **Configuration** | [PyYAML](https://pyyaml.org/) + [python-dotenv](https://pypi.org/project/python-dotenv/) | `>=6.0` / `>=1.0.0` | YAML config files and `.env` loading |
| **Prompt Templating** | [Jinja2](https://jinja.palletsprojects.com/) | `>=3.0.0` | Agent system prompt rendered from `system.jinja2` |
| **Terminal UI** | [Rich](https://rich.readthedocs.io/) | `>=13.0.0` | Markdown rendering, panels, colored output |
| **Session Memory** | Custom BM25 | — | In-memory keyword retrieval over pipeline artifacts (no external embeddings) |
| **RTL Generation** | [Cirbuild-Spec2RTL](https://github.com/CirbuildProject/Cirbuild-Spec2RTL) | `@main` git dep | 4+1 module LLM pipeline: spec → pseudocode → C++ → HLS → Verilog |
| **Physical Design** | [Librelane](https://github.com/CirbuildProject/librelane) (OpenLane/OpenROAD) | external | RTL-to-GDSII flow via Nix-shell subprocess bridge |
| **Containerization** | Docker | — | Pre-built Google XLS HLS toolchain (`cirbuild-xls:v1`) |
| **Testing** | [pytest](https://pytest.org/) | `>=7.0.0` | Unit test battery |
| **Dev IDE** | Antigravity agentic IDE / Kilo Code (VS Code) | — | Claude Sonnet 4.6, Claude Opus 4.6, Minimax M2.5, Gemini 3.1 Pro |

**Primary agent LLM (default config):** `openrouter/minimax/minimax-m2.5`
**Fallback chain:** `openrouter/google/gemini-2.5-flash` → `openrouter/deepseek/deepseek-v3.2`

---

## 🚀 Installation

### Prerequisites

- Python `>= 3.10`
- An LLM API key (OpenRouter recommended; covers 100+ models with one key)
- Docker (required for the Google XLS HLS backend)
- Nix (required only if using the Librelane physical design flow)
- For physical design: [Librelane](https://github.com/CirbuildProject/librelane) + a PDK (e.g., sky130A)

---

### Quickstart — Automatic Launch Scripts (Recommended)

These scripts handle the virtual environment, install all dependencies, and **automatically pull the latest Cirbuild-Spec2RTL** from GitHub every time they run using `--force-reinstall --no-cache-dir`. No manual pip commands needed.

#### Linux/macOS — `start.sh`

Create `start.sh` in the project root:

```bash
#!/bin/bash
echo "🚀 Initializing CirbuildSTG Environment..."

# 1. Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating a fresh virtual environment..."
    python3 -m venv venv
fi

# 2. Activate the virtual environment
source venv/bin/activate

# 3. Ensure core build tools are up to date
pip install --upgrade pip setuptools wheel

# 4. Force-fetch the absolute latest Spec2RTL from the remote main branch
echo "🔄 Fetching the latest Spec2RTL from remote..."
pip install --upgrade --force-reinstall --no-cache-dir \
    git+https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git@main

# 5. Install local project and remaining dependencies safely
echo "🛠️ Installing CirbuildSTG dependencies..."
pip install -r requirements.txt
pip install -e .

# 6. Launch the application
echo "✨ Launching application..."
cirbuild
```

Make it executable: `chmod +x start.sh`, then run `./start.sh`.

#### Windows — `start.bat`

Create `start.bat` in the project root:

```bat
@echo off
echo 🚀 Initializing CirbuildSTG Environment...

:: 1. Create a virtual environment if it doesn't exist
if not exist "venv\" (
    echo 📦 Creating a fresh virtual environment...
    python -m venv venv
)

:: 2. Activate the virtual environment
call venv\Scripts\activate.bat

:: 3. Ensure core build tools are up to date
python -m pip install --upgrade pip setuptools wheel

:: 4. Force-fetch the absolute latest Spec2RTL from the remote main branch
echo 🔄 Fetching the latest Spec2RTL from remote...
pip install --upgrade --force-reinstall --no-cache-dir git+https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git@main

:: 5. Install local project and remaining dependencies safely
echo 🛠️ Installing CirbuildSTG dependencies...
pip install -r requirements.txt
pip install -e .

:: 6. Launch the application
echo ✨ Launching application...
cirbuild
pause
```

> **Why these flags?**
> - `--force-reinstall --no-cache-dir` bypasses pip's aggressive git caching, guaranteeing the newest commit is pulled from GitHub every run.
> - The `venv` folder is isolated within the project directory — delete it and rerun for a completely clean slate.
> - `pip install -e .` means local changes to CirbuildSTG itself take effect without reinstalling.

---

### Manual Setup

```bash
# 1. Clone the repository
git clone https://github.com/CirbuildProject/CirbuildSTG.git
cd CirbuildSTG

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install all dependencies including spec2rtl backend
pip install --upgrade pip setuptools wheel
pip install --force-reinstall --no-cache-dir \
    git+https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git@main
pip install -r requirements.txt
pip install -e .
```

---

### Configure API Keys

Create a `.env` file in the project root. Two key prefixes are used — one for the agent and one for the Spec2RTL backend:

```bash
# ── Frontend Agent Keys (CIRBUILD_ prefix) ──
CIRBUILD_OPENROUTER_KEY="sk-or-v1-your-openrouter-key-here"
CIRBUILD_GEMINI_KEY="AIza-your-gemini-key-here"         # optional fallback
CIRBUILD_ANTHROPIC_KEY="sk-ant-your-anthropic-key-here" # optional fallback

# ── Backend Pipeline Keys (SPEC2RTL_ prefix — separate quota) ──
SPEC2RTL_OPENROUTER_KEY="sk-or-v1-your-openrouter-key-here"
SPEC2RTL_GEMINI_KEY="AIza-your-gemini-key-here"         # optional fallback
SPEC2RTL_ANTHROPIC_KEY="sk-ant-your-anthropic-key-here" # optional fallback
```

See [`env_example.md`](env_example.md) for the full list of all configuration options.

**Configuration priority:** env vars (`CIRBUILD_*` / `SPEC2RTL_*`) → YAML config → code defaults.

**Frontend config variables:**

| Variable | Default | Description |
|---|---|---|
| `CIRBUILD_AGENT_MODEL` | `openrouter/minimax/minimax-m2.5` | Agent LLM |
| `CIRBUILD_AGENT_TEMPERATURE` | `0.3` | Agent temperature |
| `CIRBUILD_WORKSPACE_DIR` | `cirbuild_workspace` | Workspace directory |
| `CIRBUILD_LIBRELANE_PDK` | `sky130A` | Target PDK |

**Backend config variables:** see [Cirbuild-Spec2RTL README](https://github.com/CirbuildProject/Cirbuild-Spec2RTL#configuration--api-keys).

---

### Set up the Google XLS Docker Environment

The default HLS backend runs inside a Docker container. Docker must be installed and running.

#### Option A: Pull the Pre-built Image (Fastest)
```bash
docker pull cirbuildproject/cirbuild-xls:v1
docker tag cirbuildproject/cirbuild-xls:v1 cirbuild-xls:v1
```

#### Option B: Build from Source (Developers)
```bash
# From the CirbuildSTG root (Dockerfile included)
docker build -t cirbuild-xls:v1 .
# ⚠ Takes 15 min – several hours (Bazel build of Google XLS)
```

---

## ⚡ Quick Start

```bash
# Start the interactive CLI
cirbuild

# Or with Python module syntax
python -m cirbuild
```

### Example session

```
🔧 CirbuildSTG v0.1
You> Design a 32-bit ALU that supports ADD, SUB, AND, OR, XOR with a zero flag.

Cirbuild> I'll parse your specification and generate RTL...
          [Tool: parse_spec_to_json] ✓
          [Tool: run_spec2rtl_pipeline] ✓

          Generated ALU module in workspace. Here's a preview:
          module ALU32(input [31:0] a, b, input [2:0] op, output reg [31:0] result, ...

You> Can you explain the XOR logic?

Cirbuild> Based on the generated RTL, when op=3'b100, the result is a ^ b...

You> /run-librelane ALU32

Cirbuild> Running physical design flow (sky130A)...
          Area: 1234.56 µm²  |  Timing: Met @ 10ns clock period
```

---

## 🖥️ CLI Commands

| Command | Description |
|---|---|
| `/spec <file>` | Load a spec file (PDF, TXT, or JSON) and run Spec2RTL |
| `/workspace` | List files in the Verilog workspace |
| `/edit <file>` | Show a workspace file for discussion-based editing |
| `/package <module>` | Package workspace files for Librelane |
| `/run-librelane <module>` | Execute the Librelane RTL-to-GDSII flow |
| `/status` | Show current session status |
| `/clear` | Clear conversation history and memory |
| `/help` | Show available commands |
| `/quit` | Exit CirbuildSTG |

Plain messages (no `/` prefix) are routed to the LLM agent and may trigger tool calls.

---

## 🔧 Agent Tools

The agent has **12 tools** for autonomous operation:

| Tool | Description |
|---|---|
| `parse_spec_to_json` | Parse natural-language spec into validated `JsonHardwareSpec` |
| `run_spec2rtl_pipeline` | Invoke Spec2RTL with a JSON spec; returns RTL path and artifacts |
| `run_spec2rtl_from_file` | Invoke Spec2RTL from PDF/TXT file |
| `query_memory` | BM25 search over stored specs, pseudocode, and RTL |
| `read_workspace_file` | Read a file from the Verilog workspace |
| `write_workspace_file` | Write/edit a file; auto-snapshots previous version |
| `list_workspace_files` | List all files in the active workspace |
| `scan_workspace` | Scan for existing module directories |
| `activate_workspace_module` | Activate a module for editing |
| `load_verilog_file` | Load an existing Verilog file directly into workspace |
| `package_for_librelane` | Package workspace into a Librelane design directory |
| `run_librelane_flow` | Execute the physical design flow via Nix-shell bridge |

---

## ⚙️ Configuration

### Default config (`cirbuild/config/default_config.yaml`)

```yaml
# Agent LLM (dedicated channel, NOT shared with spec2rtl pipeline)
agent_model: "openrouter/minimax/minimax-m2.5"
agent_fallback_models:
  - "openrouter/google/gemini-2.5-flash"
  - "openrouter/deepseek/deepseek-v3.2"
agent_temperature: 0.3
agent_max_tokens: 8192

# Workspace
workspace_dir: "cirbuild_workspace"

# Librelane physical design
librelane_repo_path: "../librelane"
librelane_pdk_root: "~/.ciel"
librelane_pdk: "sky130A"

# Spec2RTL backend (leave null to use spec2rtl's own default_config.yaml)
spec2rtl_config_path: null
```

### Custom config

```bash
cirbuild --config my_config.yaml
```

### Env-var overrides

```bash
export CIRBUILD_AGENT_MODEL="openrouter/google/gemini-2.5-flash"
export CIRBUILD_WORKSPACE_DIR="/path/to/workspace"
export CIRBUILD_LIBRELANE_PDK="gf180mcuD"
```

---

## 📂 Project Structure

```
CirbuildSTG/
├── cirbuild/
│   ├── __init__.py              # Package root, __version__ = "0.1.0"
│   ├── __main__.py              # Entry point: python -m cirbuild
│   ├── cli.py                   # CLI chat loop with /command dispatch
│   ├── agent/
│   │   ├── client.py            # CirbuildAgent — LiteLLM tool-calling loop
│   │   ├── tools.py             # 12 tool definitions + handlers
│   │   └── prompts/
│   │       └── system.jinja2    # Agent system prompt template
│   ├── config/
│   │   ├── default_config.yaml  # Default settings (YAML)
│   │   └── settings.py          # CirbuildSettings (Pydantic-settings)
│   ├── librelane/
│   │   ├── runner.py            # LibrelaneRunner — config gen + subprocess
│   │   └── nix_bridge.py        # Nix-shell bridge for EDA tool invocation
│   ├── memory/
│   │   └── rag_store.py         # In-memory BM25 RAG over pipeline artifacts
│   ├── pipeline/
│   │   ├── bridge.py            # Spec2RTLBridge — spec validation + invocation
│   │   └── json_spec.py         # JsonHardwareSpec — Pydantic input schema
│   └── workspace/
│       └── manager.py           # WorkspaceManager — file editing + history
├── docs/
│   ├── TECH_STACK.md            # In-depth technology documentation
│   └── TUTORIALS.md             # Step-by-step workflow tutorials
├── tests/                       # Pytest battery
├── start.sh                     # Linux/macOS one-click launcher
├── start.bat                    # Windows one-click launcher
├── requirements.txt             # Pinned dependencies
├── pyproject.toml               # Package metadata (cirbuild-stg v0.1.0)
├── env_example.md               # Full .env configuration template
└── README.md
```

---

## 📚 Detailed Documentation

- **[docs/TECH_STACK.md](docs/TECH_STACK.md)** — In-depth component documentation, architecture patterns, Docker/Nix integration, extending with new tools or providers
- **[docs/TUTORIALS.md](docs/TUTORIALS.md)** — Step-by-step workflow tutorials
- **[env_example.md](env_example.md)** — Complete `.env` configuration reference

---

## Manually Updating the Spec2RTL Backend

If you are not using the launch scripts and need to manually pull an update:

```bash
source venv/bin/activate
pip install --upgrade --force-reinstall --no-cache-dir \
    git+https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git@main
```

---

## License

MIT

---

## ⚠️ Disclaimer

This project is developed with the assistance of the **Antigravity** agentic IDE and Kilo Code extension (VS Code), utilizing Claude Opus 4.6, Claude Sonnet 4.6, Gemini 3.1 Pro, and Minimax M2.5. All generated RTL produced by this pipeline should be manually verified before use in research publications or commercial applications. Architectural decisions and progressive refinements reflect genuine human engineering intent. This project is a Proof of Concept intended for educational and pedagogical purposes.

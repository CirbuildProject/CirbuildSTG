# CirbuildSTG

**AI-Powered Spec-to-GDSII IC Design Assistant**

CirbuildSTG is an agentic AI EDA tool that covers the full pre-silicon Integrated Circuit design workflow — from natural-language hardware specification to GDSII layout. It orchestrates two backend subsystems through a dedicated LLM-powered chat agent:

1. **Spec2RTL** — Converts hardware specifications into synthesizable RTL (Verilog) code
2. **Librelane** — Runs the RTL-to-GDSII physical design flow using OpenLane/OpenROAD

The name stands for **Circuit Builder Spec-To-GDSII**.

## Objectives

- Explore AI-driven chip design and LLM integration in the RTL workflow
- Solve resource accessibility and guidance problems for students learning industry-standard IC design
- Provide a top-down pedagogical framework where users learn-while-building their own IC

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    CirbuildSTG                          │
│                                                         │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ CLI Chat │───>│ Cirbuild     │───>│ RAG Memory   │   │
│  │ Loop     │<───│ Agent (LLM)  │<───│ Store (BM25) │   │
│  └──────────┘    └──────┬───────┘    └──────────────┘   │
│                         │                               │
│         ┌───────────────┼───────────────┐               │
│         │               │               │               │
│         v               v               v               │
│  ┌────────────┐  ┌────────────┐  ┌────────────────┐     │
│  │ Spec2RTL   │  │ Workspace  │  │ Librelane      │     │
│  │ Bridge     │  │ Manager    │  │ Runner         │     │
│  └─────┬──────┘  └────────────┘  └───────┬────────┘     │
│        │                                 │              │
└────────┼─────────────────────────────────┼──────────────┘
         │                                 │
         v                                 v
   ┌──────────────┐                  ┌──────────────┐
   │ Cirbuild-    │                  │ librelane    │
   │ Spec2RTL     │                  │ (OpenLane)   │
   │ (backend)    │                  │              │
   └──────────────┘                  └──────────────┘
```

**Key design decisions:**

- **Separate LLM channels** — The agent has its own LLM API configuration, independent from the Spec2RTL backend's LLM. This prevents rate-limit conflicts and allows different models for different tasks.
- **JSON as native spec input** — The agent produces structured JSON specs that are validated with Pydantic before being passed to the pipeline.
- **Subprocess isolation for Librelane** — Librelane runs as a subprocess to avoid dependency conflicts.
- **In-memory BM25 RAG** — Session-scoped keyword retrieval over pipeline artifacts. No external embedding models required.
- **Workspace with history** — Automatic snapshots enable undo during interactive editing sessions.

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Agent LLM** | [LiteLLM](https://docs.litellm.ai/) | Unified API for multiple LLM providers (OpenRouter, Gemini, Anthropic) |
| **Data Validation** | [Pydantic](https://docs.pydantic.dev/) | Schema validation for hardware specifications |
| **Configuration** | [PyYAML](https://pyyaml.org/) + python-dotenv | YAML config files with env var overrides |
| **Templating** | [Jinja2](https://jinja.palletsprojects.com/) | Agent system prompt templates |
| **CLI UI** | [Rich](https://rich.readthedocs.io/) | Rich terminal output with Markdown rendering |
| **RAG Memory** | Custom BM25 implementation | Keyword-based retrieval without external embeddings |
| **RTL Generation** | [Cirbuild-Spec2RTL](https://github.com/CirbuildProject/Cirbuild-Spec2RTL) | LLM-powered spec-to-RTL pipeline |
| **Physical Design** | [Librelane](https://github.com/CirbuildProject/librelane) | OpenLane/OpenROAD wrapper for RTL-to-GDSII |
| **Containerization** | Docker + Nix | Reproducible toolchain environments |

---

## Installation

### Prerequisites

- Python 3.10+
- An LLM API key (e.g., OpenRouter, OpenAI)
- For physical design: [librelane](https://github.com/CirbuildProject/librelane) and a PDK (e.g., sky130A)

### 1. Clone the repository

```bash
git clone https://github.com/CirbuildProject/CirbuildSTG.git
cd CirbuildSTG
```

### 2. Set up a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install the package

```bash
# Install with all dependencies
pip install -e .

# Or install with Spec2RTL backend
pip install -e ".[spec2rtl]"

# Or install from requirements.txt
pip install -r requirements.txt
```

### 4. Configure your API keys

Create a `.env` file in the project root. Both the frontend agent and the backend pipeline use **provider-specific keys** so that fallback models can switch providers without rate-limit conflicts:

```bash
# Frontend agent keys (CIRBUILD_ prefix)
CIRBUILD_OPENROUTER_KEY="sk-or-v1-your-openrouter-key-here"
CIRBUILD_GEMINI_KEY="AIza-your-gemini-key-here"       # optional: only if using gemini/ fallback
CIRBUILD_ANTHROPIC_KEY="sk-ant-your-anthropic-key-here" # optional: only if using anthropic/ fallback

# Backend pipeline keys (SPEC2RTL_ prefix — separate quota from frontend)
SPEC2RTL_OPENROUTER_KEY="sk-or-v1-your-openrouter-key-here"
SPEC2RTL_GEMINI_KEY="AIza-your-gemini-key-here"       # optional: only if using gemini/ fallback
SPEC2RTL_ANTHROPIC_KEY="sk-ant-your-anthropic-key-here" # optional: only if using anthropic/ fallback
```

See [`env_example.md`](env_example.md) for the full configuration template.

### 5. Set up the Google XLS Docker Environment

CirbuildSTG uses a containerized Google XLS toolchain for High-Level Synthesis (HLS) to save you from compiling the tools from source. You **must** have Docker installed and running before starting the pipeline. 

Choose **one** of the following methods to get the required `cirbuild-xls:v1` image:

#### Option A: Pull the Pre-built Image (Fastest)
If you just want to run the pipeline immediately, you can download the pre-compiled image directly from Docker Hub and tag it for local use:
```bash
# Pull the image from Docker Hub 
docker cirbuildproject/cirbuild-xls:v1

# Tag it so the CirbuildSTG backend can find it automatically
docker tag cirbuildproject/cirbuild-xls:v1 cirbuild-xls:v1
```
#### Option B: Build Directly from Source (For Developers)
If you prefer complete transparency or want to modify the XLS environment, you can build the image directly using the Dockerfile included in this repository. (Note: This process takes about 15-20 minutes upto a few hours as it compiles Google XLS via Bazel, depending on the hardware you are working on).
```bash
# Run this from the root of the CirbuildSTG directory
docker build -t cirbuild-xls:v1 .
```

---

## Quick Start

### Start the interactive chat

```bash
# Using the CLI command
cirbuild

# Or using Python module
python -m cirbuild
```

### Example session

```
🔧 CirbuildSTG v0.1
You> Design a 32-bit ALU that supports ADD, SUB, AND, OR, XOR operations
     with a zero flag output.

Cirbuild> I'll parse your specification and generate RTL code...
          [Tool: parse_spec_to_json] ✓
          [Tool: run_spec2rtl_pipeline] ✓
          
          Generated ALU module in workspace. Here's a preview:
          ...

You> Can you explain the XOR logic?

Cirbuild> Based on the generated RTL, the XOR operation is selected
          when op=100...

You> Change the XOR to XNOR

Cirbuild> I've updated alu.v — the XOR operation now produces ~(a ^ b)...

You> /run-librelane ALU

Cirbuild> Running physical design flow...
          Area: 1234.56 µm²
          Timing: Met at 10ns clock period
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `/spec <file>` | Load a spec file (PDF, TXT, or JSON) and run the Spec2RTL pipeline |
| `/workspace` | List files in the Verilog workspace |
| `/edit <file>` | Show a workspace file for discussion-based editing |
| `/package <module>` | Package workspace files for Librelane |
| `/run-librelane <module>` | Execute the Librelane RTL-to-GDSII flow |
| `/status` | Show current session status |
| `/clear` | Clear conversation history and memory |
| `/help` | Show available commands |
| `/quit` | Exit Cirbuild |

Messages without a `/` prefix are routed to the LLM agent for natural conversation, which may trigger tool calls internally.

---

## Agent Tools

The agent has 12 tools available for autonomous operation:

| Tool | Description |
|------|-------------|
| `parse_spec_to_json` | Parse natural-language spec into structured JSON |
| `run_spec2rtl_pipeline` | Execute Spec2RTL pipeline with JSON input |
| `run_spec2rtl_from_file` | Execute Spec2RTL pipeline from a file |
| `query_memory` | BM25 search over stored specs, pseudocode, and RTL |
| `read_workspace_file` | Read a file from the Verilog workspace |
| `write_workspace_file` | Write/edit a file with automatic history snapshot |
| `list_workspace_files` | List all files in the active workspace |
| `scan_workspace` | Scan workspace for existing module directories |
| `activate_workspace_module` | Activate a workspace module for editing |
| `load_verilog_file` | Load existing Verilog file directly into workspace |
| `package_for_librelane` | Package workspace into a Librelane design directory |
| `run_librelane_flow` | Execute the Librelane physical design flow |

---

## Configuration

### Default configuration

The default config is at `cirbuild/config/default_config.yaml`:

```yaml
# Agent LLM (dedicated channel, NOT shared with spec2rtl)
agent_model: "openrouter/minimax/minimax-m2.5"
agent_fallback_models:
  - "openrouter/gemini/gemini-2.5-flash"
agent_temperature: 0.3
agent_max_tokens: 4096

# Workspace
workspace_dir: "cirbuild_workspace"

# Librelane
librelane_repo_path: "../librelane"
librelane_pdk_root: "~/.ciel"
librelane_pdk: "sky130A"

# Spec2RTL Backend
spec2rtl_config_path: null  # Uses spec2rtl defaults
```

### Custom configuration

Pass a custom config file:

```bash
cirbuild --config my_config.yaml
```

### Environment variables

All settings can be overridden with `CIRBUILD_` prefixed environment variables:

```bash
export CIRBUILD_AGENT_MODEL="openrouter/google/gemini-2.5-flash"
export CIRBUILD_WORKSPACE_DIR="/path/to/workspace"
export CIRBUILD_LIBRELANE_PDK="gf180mcuD"
```

Environment variables take highest priority, followed by constructor values, then YAML config, then defaults.

---

### Using .env File for Configuration

For convenience, you can configure both the **CirbuildSTG frontend** and **Spec2RTL backend** using a single `.env` file in the project root.

#### Quick Setup

```bash
# Copy the example template
cp env_example.md .env

# Edit .env with your API keys
```

#### What Can Be Configured

**Frontend (Cirbuild Agent):**
| Variable | Description |
|----------|-------------|
| `CIRBUILD_OPENROUTER_KEY` | API key for `openrouter/` models |
| `CIRBUILD_GEMINI_KEY` | API key for `gemini/` models |
| `CIRBUILD_ANTHROPIC_KEY` | API key for `anthropic/` models |
| `CIRBUILD_AGENT_MODEL` | Override the default LLM model |
| `CIRBUILD_AGENT_TEMPERATURE` | Set agent temperature |

**Backend (Spec2RTL Pipeline):**
| Variable | Description |
|----------|-------------|
| `SPEC2RTL_OPENROUTER_KEY` | API key for `openrouter/` models |
| `SPEC2RTL_GEMINI_KEY` | API key for `gemini/` models |
| `SPEC2RTL_ANTHROPIC_KEY` | API key for `anthropic/` models |
| `SPEC2RTL_DEFAULT_MODEL` | Override the default RTL generation model |
| `SPEC2RTL_HLS_COMPILER` | Set HLS compiler (`google_xls`, `bambu`, `vitis`) |

The correct key is selected automatically based on the model string prefix — no extra configuration needed when switching providers.

> **Note:** The `.env` file is NOT tracked by git. See [`env_example.md`](env_example.md) for the complete list of all configuration options.

---

## Project Structure

```
CirbuildSTG/
├── cirbuild/
│   ├── __init__.py              # Package root, __version__ = "0.1.0"
│   ├── __main__.py              # Entry point: python -m cirbuild
│   ├── cli.py                   # CLI chat loop with /command dispatch
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── client.py            # CirbuildAgent — LLM client with tool-calling loop
│   │   ├── tools.py             # 12 tool definitions + handlers
│   │   └── prompts/
│   │       └── system.jinja2    # Agent system prompt template
│   ├── config/
│   │   ├── __init__.py
│   │   ├── default_config.yaml  # Default settings
│   │   └── settings.py          # CirbuildSettings (Pydantic)
│   ├── librelane/
│   │   ├── __init__.py
│   │   ├── runner.py            # LibrelaneRunner — config gen + subprocess
│   │   └── nix_bridge.py        # Nix-shell bridge for Librelane execution
│   ├── memory/
│   │   ├── __init__.py
│   │   └── rag_store.py         # BM25 RAG store — session-scoped retrieval
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── bridge.py            # Spec2RTLBridge — pipeline invocation + artifacts
│   │   └── json_spec.py         # JsonHardwareSpec — Pydantic validation
│   └── workspace/
│       ├── __init__.py
│       └── manager.py           # WorkspaceManager — file editing + history
├── docs/                        # Additional documentation
│   ├── TECH_STACK.md           # Detailed tech stack documentation
│   └── TUTORIALS.md            # Usage tutorials
├── plans/
│   └── Cirbuild_Spec2RTL_Integration_Plan.md
├── pyproject.toml
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Detailed Documentation

For more detailed documentation, see the files in the `docs/` folder:

- **[docs/TECH_STACK.md](docs/TECH_STACK.md)** — In-depth explanation of the technology stack, dependencies, and architecture
- **[docs/TUTORIALS.md](docs/TUTORIALS.md)** — Step-by-step tutorials for common workflows

---

## Updating Subsystems

If a new update is pushed to the Spec2RTL repository:

```bash
pip install --upgrade --force-reinstall git+https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git@main
```

---

## License

MIT

## ⚠️ Disclaimer

This project is completely written, debugged, and verified via the use of the **Antigravity** agentic IDE and Kilo Code Extension in VS Code IDE, utilizing models of Claude Opus 4.6, Claude Sonnet 4.6, Gemini 3.1 Pro, and Minimax M2.5. Any generated code through this pipeline should be manually verified before mission-critical use (e.g., research literature, commercial usage, etc.). The architectural considerations and progressive refinements are genuine human intent. 

Note: This project is not intended for production use, and primarily structured to be a Proof of Concept for educational / pedagogical purposes. 

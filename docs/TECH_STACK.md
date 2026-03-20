# CirbuildSTG Tech Stack Documentation

This document provides an in-depth explanation of the technologies and components that power CirbuildSTG.

---

## Overview

CirbuildSTG is an agentic AI EDA tool that combines Large Language Models with traditional Electronic Design Automation tools to create an end-to-end hardware design workflow. The system integrates:

1. **LLM-powered agents** for natural language understanding and code generation
2. **RTL generation pipelines** for converting specifications to Verilog
3. **Physical design flows** for converting RTL to GDSII layout
4. **Memory and workspace management** for tracking design artifacts

---

## Core Technologies

### 1. LiteLLM — Unified LLM Interface

**Purpose:** Provides a unified API layer for multiple LLM providers

**Why LiteLLM?**
- Single interface for OpenRouter, Google Gemini, Anthropic, OpenAI, and others
- Automatic API key routing based on model prefix
- Built-in fallback mechanisms for reliability
- Token counting and cost tracking

**Configuration:**
```python
# Default model (MiniMax M2.5 via OpenRouter)
agent_model: "openrouter/minimax/minimax-m2.5"

# Fallback models
agent_fallback_models:
  - "openrouter/google/gemini-2.5-flash"
  - "openrouter/deepseek/deepseek-v3.2"
```

**API Key Resolution:**
The system automatically selects the correct API key based on the model prefix:
- `openrouter/*` → Uses `CIRBUILD_OPENROUTER_KEY`
- `gemini/*` → Uses `CIRBUILD_GEMINI_KEY`
- `anthropic/*` → Uses `CIRBUILD_ANTHROPIC_KEY`

---

### 2. Pydantic — Data Validation

**Purpose:** Validates hardware specifications and configuration settings

**Key Models:**

#### `JsonHardwareSpec`
Validates the JSON specification format required by the Spec2RTL pipeline:
```python
class JsonHardwareSpec(BaseModel):
    module_name: str
    description: str
    inputs: Dict[str, str]
    outputs: Dict[str, str]
    behavior: str
    constraints: List[str]
    classification: Literal["COMBINATIONAL", "SEQUENTIAL_PIPELINE", "STATE_MACHINE"]
```

#### `CirbuildSettings`
Application-wide configuration with environment variable support:
```python
class CirbuildSettings(BaseSettings):
    agent_model: str = "openrouter/minimax/minimax-m2.5"
    workspace_dir: Path = Path("cirbuild_workspace")
    librelane_pdk: str = "sky130A"
    # ... with CIRBUILD_ prefix support
```

**Priority Order:**
1. Environment variables (highest)
2. Constructor values
3. YAML config file
4. Default values (lowest)

---

### 3. BM25 Retrieval — In-Memory RAG

**Purpose:** Provides session-scoped keyword-based retrieval without external embeddings

**Why BM25?**
- No external embedding models required
- Optimized for hardware description syntax
- Preserves exact signal names and keywords
- Lightweight and fast

**Implementation Details:**

The `RAGStore` class implements BM25 ranking with:
- **k1 = 1.5**: Term frequency saturation parameter
- **b = 0.75**: Document length normalization
- **Chunk size**: 500 characters with 100 character overlap

**Namespaces:**
- `spec`: Hardware specifications
- `pseudocode`: Design plans
- `rtl`: Generated Verilog code
- `metrics`: Physical design results

**Usage:**
```python
# Store artifacts
store.store_pipeline_artifacts(artifacts)

# Query memory
results = store.query("ALU operations", namespace="rtl", top_k=5)
```

---

### 4. Workspace Manager — File Editing with History

**Purpose:** Manages Verilog/SystemVerilog files with automatic versioning

**Directory Structure:**
```
cirbuild_workspace/
└── <module_name>/
    ├── <module_name>.v          # Main RTL file
    ├── <module_name>_tb.v       # Testbench (if generated)
    └── .history/
        ├── 001_<module_name>.v  # Version 1
        ├── 002_<module_name>.v  # Version 2
        └── ...
```

**Features:**
- Path traversal protection
- Automatic history snapshots before edits
- Module activation for multi-design workspaces
- File packaging for physical design

---

### 5. Spec2RTL Backend — RTL Generation

**Purpose:** Converts hardware specifications to synthesizable Verilog

**Architecture:**
The backend is a separate package (`Cirbuild-Spec2RTL`) that:
1. Parses natural language specifications
2. Generates pseudocode/behavioral description
3. Performs High-Level Synthesis (HLS)
4. Outputs synthesizable RTL

**Supported HLS Compilers:**
- **Google XLS** (default): Fast HLS via Docker container
- **Bambu**: GCC-based HLS from Politecnico di Milano
- **Vitis HLS**: Xilinx proprietary (requires installation)

**Integration:**
The `Spec2RTLBridge` class provides:
- Input validation
- Pipeline invocation
- Artifact capture for RAG storage

---

### 6. Librelane — Physical Design

**Purpose:** Executes RTL-to-GDSII physical design flow

**What is Librelane?**
Librelane is a wrapper around OpenLane/OpenROAD that:
- Simplifies configuration
- Manages PDK setup
- Provides programmatic API access
- Handles Nix-shell isolation

**The Nix-Shell Bridge:**

To ensure reproducibility and dependency isolation, Librelane runs inside a Nix-shell:

```
Host Python → nix-shell → nix_bridge.py → Librelane → GDSII
```

The `nix_bridge.py` script:
1. Runs inside the Nix environment where EDA tools are available
2. Invokes Librelane's programmatic API
3. Writes results to `librelane_result.json`
4. Returns control to the host Python process

**PDK Support:**
- **sky130A/SkyWater**: Open-source 130nm process
- **gf180mcuD**: GlobalFoundries 180nm process

---

### 7. Rich — Terminal UI

**Purpose:** Provides rich terminal output with Markdown rendering

**Features Used:**
- `Console.input()`: Interactive input with color
- `Panel`: Bordered message boxes
- `Markdown`: Rendered Markdown output
- `Text`: Styled text with colors

---

### 8. Jinja2 — Prompt Templating

**Purpose:** Renders the agent's system prompt from templates

**Template Location:**
`cirbuild/agent/prompts/system.jinja2`

The template defines:
- Agent persona and capabilities
- Workflow patterns
- Tool usage guidelines

---

## Architecture Patterns

### Tool-Calling Loop

The agent implements a ReAct-style (Reasoning + Acting) tool-calling loop:

```python
for round in range(max_rounds):
    response = llm.complete(messages + history, tools=tools)
    
    if not response.tool_calls:
        return response.content
    
    for tool_call in response.tool_calls:
        result = execute_tool(tool_call.name, tool_call.args)
        history.append(tool_call + result)
```

### Separate LLM Channels

CirbuildSTG uses **two separate LLM configurations**:

1. **Agent LLM** (`CIRBUILD_*`): Powers the conversational interface
2. **Backend LLM** (`SPEC2RTL_*`): Used by Spec2RTL for RTL generation

This separation prevents:
- Rate limit conflicts
-Quota exhaustion
- Different model requirements for different tasks

---

## Dependencies

### Required
```toml
litellm>=1.0.0        # LLM API abstraction
pydantic>=2.0.0      # Data validation
pydantic-settings>=2.0.0  # Settings management
pyyaml>=6.0           # YAML config parsing
python-dotenv>=1.0.0  # .env file loading
jinja2>=3.0.0         # Prompt templating
rich>=13.0.0          # Terminal UI
```

### Optional
```toml
spec2rtl @ git+...    # RTL generation backend
pytest>=7.0.0         # Testing
```

---

## Docker & Nix Integration

### Google XLS Docker Image

CirbuildSTG uses Docker to provide a pre-built Google XLS toolchain:

**Image:** `cirbuildproject/cirbuild-xls:v1`

**What's Inside:**
- Google XLS (compiled via Bazel)
- Required system dependencies
- Python runtime for XLS scripts

**Building from Source:**
```bash
docker build -t cirbuild-xls:v1 .
# Takes 15-20 minutes to several hours
```

### Librelane Nix Shell

Librelane uses Nix for environment isolation. The `shell.nix` file (located in the librelane repository) provides a reproducible environment with all required EDA tools.

**What shell.nix Provides:**
- **OpenLane**: RTL-to-GDSII flow orchestrator
- **OpenROAD**: Place and route engine
- **Yosys**: Logic synthesis tool
- **Magic**: Layout editor and DRC checker
- **Netgen**: LVS (Layout vs. Schematic) tool
- **PDK files**: sky130A, gf180mcuD process design kits

**How It Works:**

The `LibrelaneRunner` class in [`cirbuild/librelane/runner.py`](../cirbuild/librelane/runner.py) executes the physical design flow via a Nix-shell bridge:

```
Host Python → nix-shell shell.nix → nix_bridge.py → Librelane → GDSII
```

1. **runner.py** builds a `nix-shell <shell.nix> --run "python nix_bridge.py <design_dir> <config_path>"` command
2. **nix_bridge.py** runs inside the Nix environment where EDA binaries are available
3. The bridge script imports `librelane.flows.Flow` and executes the Classic flow
4. Results are written to `librelane_result.json` for the host Python to read

**Environment Variables Passed to Nix Shell:**

| Variable | Description | Default |
|----------|-------------|---------|
| `LIBRELANE_DIR` | Path to librelane repository | `../librelane` (from config) |
| `LIBRELANE_PDK` | Target PDK name | `sky130A` |
| `LIBRELANE_PDK_ROOT` | PDK root directory | `~/.ciel` |
| `LIBRELANE_TAG` | Run tag name | (optional) |
| `LIBRELANE_FRM` | Start from this step | (optional) |
| `LIBRELANE_TO` | Stop after this step | (optional) |
| `LIBRELANE_OVERWRITE` | Overwrite existing runs | (optional) |

**Locating shell.nix:**

The runner looks for `shell.nix` in this order:
1. `LIBRELANE_DIR` environment variable
2. `librelane_repo_path` from CirbuildSTG config (default: `../librelane`)

**Nix Installation:**

Nix must be installed on the host system. The `nix-shell` command must be available on PATH.

**Common Nix Issues:**

| Issue | Solution |
|-------|----------|
| `nix-shell: command not found` | Install Nix: `curl -L https://nixos.org/nix/install \| sh` |
| `shell.nix not found` | Verify `LIBRELANE_DIR` or `librelane_repo_path` points to librelane repo |
| Permission denied | Run `nix-shell` with appropriate permissions |
| PDK not found | Verify `LIBRELANE_PDK_ROOT` contains the PDK files |

---

## Security Considerations

### Path Traversal Protection

The workspace manager prevents path traversal attacks:
```python
def _safe_path(self, filename: str) -> Path:
    resolved = (module_dir / filename).resolve()
    if not resolved.is_relative_to(module_dir):
        raise ValueError(f"Path traversal detected: {filename!r}")
    return resolved
```

### API Key Management

- Keys stored in `.env` (not tracked by git)
- Separate keys for agent vs. backend
- Provider-specific key selection

---

## Extending CirbuildSTG

### Adding New Tools

1. Define tool in OpenAI format in `cirbuild/agent/tools.py`:
```python
{
    "type": "function",
    "function": {
        "name": "my_new_tool",
        "description": "What the tool does",
        "parameters": { ... }
    }
}
```

2. Implement handler:
```python
def handle_my_new_tool(self, **args) -> dict:
    # Implementation
    return {"result": "success"}
```

3. Register in `get_tool_handlers()`:
```python
return {
    ...
    "my_new_tool": handle_my_new_tool,
}
```

### Adding New LLM Providers

LiteLLM supports adding custom providers. Add configuration to `.env`:
```bash
# For a new provider
MY_PROVIDER_KEY="your-key-here"
CIRBUILD_AGENT_MODEL="my_provider/my-model"
```

---

## Performance Notes

- **BM25** is in-memory and fast for typical session sizes
- **Tool-calling loop** has a 15-round maximum to prevent infinite loops
- **Librelane timeout** is 1 hour per run
- **Streaming logs** show real-time progress for physical design

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| LiteLLM rate limits | Use fallback models or add more API keys |
| Librelane not found | Ensure Nix is installed and librelane is on PATH |
| PDK errors | Verify PDK_ROOT and PDK name in config |
| Docker issues | Ensure Docker daemon is running |

---

## Further Reading

- [LiteLLM Documentation](https://docs.litellm.ai/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [OpenLane Documentation](https://openlane.readthedocs.io/)
- [Google XLS Documentation](https://google.github.io/xls/)
- [Rich Library](https://rich.readthedocs.io/)

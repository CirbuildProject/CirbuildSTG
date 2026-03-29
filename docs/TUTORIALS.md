# CirbuildSTG Tutorials

This document provides step-by-step tutorials for common workflows in CirbuildSTG.

---

## Table of Contents

1. [First-Time Setup](#1-first-time-setup)
2. [Nix Environment Setup for Librelane](#2-nix-environment-setup-for-librelane)
3. [Designing Your First Module](#3-designing-your-first-module)
4. [Working with Existing RTL](#4-working-with-existing-rtl)
5. [Running Physical Design](#5-running-physical-design)
6. [Using Memory and RAG](#6-using-memory-and-rag)
7. [Advanced: Custom Configurations](#7-advanced-custom-configurations)

---

## 1. First-Time Setup

### Step 1: Clone and Install

```bash
# Clone the repository
git clone https://github.com/CirbuildProject/CirbuildSTG.git
cd CirbuildSTG

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -e .
```

### Step 2: Configure API Keys

```bash
# Copy the example environment file
cp env_example.md .env

# Edit .env with your API keys
nano .env  # or your preferred editor
```

Add your API keys:
```bash
# Frontend agent
CIRBUILD_OPENROUTER_KEY="sk-or-v1-..."

# Backend (Spec2RTL)
SPEC2RTL_OPENROUTER_KEY="sk-or-v1-..."
```

### Step 3: Verify Docker Setup

```bash
# Check Docker is running
docker ps

# Pull the XLS toolchain image (or build)
docker pull cirbuildproject/cirbuild-xls:v1
docker tag cirbuildproject/cirbuild-xls:v1 cirbuild-xls:v1
```

### Step 4: Test the Installation

```bash
# Start the interactive CLI
cirbuild
```

You should see the welcome banner:
```
🔧 CirbuildSTG v0.1
...
Type your hardware specification or use /help for commands.
Type /quit to exit.
```

---

## 2. Nix Environment Setup for Librelane

The Librelane physical design flow requires a Nix environment with EDA tools. This section covers installing Nix and configuring the environment.

### Step 1: Install Nix

Nix is a package manager that provides reproducible environments. Install it on your system:

**Linux/macOS:**
```bash
# Install Nix (single-user)
curl -L https://nixos.org/nix/install | sh

# Or multi-user installation (recommended for production)
curl -L https://nixos.org/nix/install | sh -s -- --daemon
```

**Verify installation:**
```bash
nix-shell --version
# Should output: nix-shell (Nix) 2.x.x
```

### Step 2: Clone the Librelane Repository

Librelane provides the `shell.nix` file that defines the EDA environment:

```bash
# Clone librelane (adjust path as needed)
git clone https://github.com/CirbuildProject/librelane.git ../librelane

# Verify shell.nix exists
ls ../librelane/shell.nix
```

### Step 3: Configure Librelane Path

Update your CirbuildSTG configuration to point to the librelane repository:

**Option A: Via .env file:**
```bash
# Add to .env
CIRBUILD_LIBRELANE_REPO_PATH="../librelane"
```

**Option B: Via YAML config:**
```yaml
# my_config.yaml
librelane_repo_path: "../librelane"
```

**Option C: Via environment variable:**
```bash
export CIRBUILD_LIBRELANE_REPO_PATH="/path/to/librelane"
```

### Step 4: Set Up PDK (Process Design Kit)

Librelane requires a PDK (Process Design Kit) for the target technology node.

**For sky130A (default):**
```bash
# Create PDK directory
mkdir -p ~/.ciel

# Download sky130A PDK (example - actual method may vary)
# Refer to librelane documentation for PDK setup instructions
```

**For gf180mcuD:**
```bash
# Set PDK in configuration
export CIRBUILD_LIBRELANE_PDK="gf180mcuD"
export CIRBUILD_LIBRELANE_PDK_ROOT="/opt/pdk/gf180mcuD"
```

### Step 5: Verify Nix Environment

Test that the Nix environment works correctly:

```bash
# Enter the librelane nix-shell
cd ../librelane
nix-shell shell.nix

# Inside the shell, verify tools are available
yosys --version
openroad -version
magic --version

# Exit the shell
exit
```

### Step 6: Test Librelane Integration

Start CirbuildSTG and test the Librelane integration:

```bash
cirbuild
```

Then try:
```
You> /run-librelane test_module
```

If Nix is not installed or shell.nix is not found, you'll see an error message with troubleshooting guidance.

### Troubleshooting Nix Setup

| Issue | Solution |
|-------|----------|
| `nix-shell: command not found` | Nix is not installed. Run the installation command above. |
| `shell.nix not found` | Verify `librelane_repo_path` points to the librelane repository. |
| `Permission denied` | Run with appropriate permissions or use multi-user Nix installation. |
| `PDK not found` | Verify `LIBRELANE_PDK_ROOT` contains the PDK files. |
| `nix-shell hangs` | Check network connectivity; Nix may be downloading dependencies. |
| `ImportError: librelane` | Ensure librelane is accessible via `LIBRELANE_DIR` or installed in the Nix environment. |

### Nix Environment Variables

The following environment variables are passed to the Nix shell when running Librelane:

| Variable | Description | Default |
|----------|-------------|---------|
| `LIBRELANE_DIR` | Path to librelane repository | From config |
| `LIBRELANE_PDK` | Target PDK name | `sky130A` |
| `LIBRELANE_PDK_ROOT` | PDK root directory | `~/.ciel` |
| `LIBRELANE_TAG` | Run tag name | (optional) |
| `LIBRELANE_FRM` | Start from this step | (optional) |
| `LIBRELANE_TO` | Stop after this step | (optional) |
| `LIBRELANE_OVERWRITE` | Overwrite existing runs | (optional) |

---

## 3. Designing Your First Module

In this tutorial, you'll design a simple 32-bit ALU using natural language.

### Step 1: Start CirbuildSTG

```bash
cirbuild
```

### Step 2: Describe Your Design

Type the following specification:

```
You> Design a 32-bit ALU that supports ADD, SUB, AND, OR, XOR operations
     with a zero flag output.
```

### Step 3: Review Generated RTL

The agent will:
1. Parse your specification into JSON
2. Run the Spec2RTL pipeline
3. Display the generated RTL code

Expected output:
```
Cirbuild> SUCCESS: The Verilog file 'alu.v' is now in the workspace.
         
         ```verilog
         module alu (
             input  wire [31:0] a,
             input  wire [31:0] b,
             input  wire [2:0]  op,
             output reg  [31:0] result,
             output wire         zero_flag
         );
            // ... implementation
         endmodule
         ```
```

### Step 4: Ask Questions About the Design

```
You> Can you explain how the XOR operation is implemented?
```

The agent will analyze the RTL and explain the implementation.

### Step 5: Make Modifications

```
You> Change the XOR operation to XNOR
```

The agent will update the RTL:
```
Cirbuild> Updated alu.v — the XOR operation now produces ~(a ^ b)
```

---

## 4. Working with Existing RTL

If you already have Verilog files, you can load them directly without running the pipeline.

### Method A: Using the /load Command

```bash
cirbuild
```

Then type:
```
You> /load /path/to/your/design.v my_module
```

### Method B: Place Files Manually

1. Create a directory in the workspace:
```bash
mkdir -p cirbuild_workspace/my_module
```

2. Copy your Verilog file:
```bash
cp my_design.v cirbuild_workspace/my_module/
```

3. In CirbuildSTG:
```
You> /workspace
```

The agent will scan and find your module.

### Method C: Load and Work with Existing Files

```
You> Scan the workspace for existing modules
```

The agent will find your modules and you can activate them:
```
You> Activate the module "my_module"
```

---

## 5. Running Physical Design

Once you have RTL, you can run the full physical design flow to generate GDSII.

### Step 1: Package for Librelane

```
You> Package the workspace for Librelane with module name "alu"
```

This creates:
- Design directory structure
- Configuration file
- Copies RTL files

### Step 2: Run the Physical Design Flow

```
You> Run librelane for module "alu"
```

This will:
1. Launch the Nix-shell environment
2. Run OpenLane synthesis, place, and route
3. Generate GDSII and DEF files
4. Report PPA metrics

### Step 3: Review Results

After completion, you'll see:
- **Area**: Chip area in µm²
- **Timing**: Clock period met vs. violated
- **Power**: Dynamic and leakage power
- **Outputs**: GDSII, DEF, netlist files

---

## 6. Using Memory and RAG

CirbuildSTG maintains a session memory that stores your specifications, RTL code, and design metrics.

### Querying Memory

```
You> Query memory for "ALU operations"
```

This uses BM25 to find relevant chunks from:
- Your specifications
- Generated RTL
- Physical design results

### Viewing Session History

```
You> What modules have we designed in this session?
```

The agent will query the RAG store to find all modules.

### Clearing Memory

```
You> /clear
```

Clears conversation history and RAG memory for a fresh session.

---

## 7. Advanced: Custom Configurations

### Custom Model Selection

Override the default model in `.env`:
```bash
CIRBUILD_AGENT_MODEL="openrouter/google/gemini-2.5-flash"
```

Or use Anthropic:
```bash
CIRBUILD_AGENT_MODEL="anthropic/claude-3-sonnet"
CIRBUILD_ANTHROPIC_KEY="sk-ant-..."
```

### Custom Workspace Location

```bash
CIRBUILD_WORKSPACE_DIR="/home/user/my_designs"
```

### Custom PDK

```bash
CIRBUILD_LIBRELANE_PDK="gf180mcuD"
CIRBUILD_LIBRELANE_PDK_ROOT="/opt/pdk/gf180mcuD"
```

### YAML Configuration

Create a custom config file:
```yaml
# my_config.yaml
agent_model: "openrouter/deepseek/deepseek-v3.2"
agent_temperature: 0.5
workspace_dir: "my_workspace"
librelane_pdk: "sky130A"
```

Use it:
```bash
cirbuild --config my_config.yaml
```

---

## Common Workflows

### Workflow 1: Quick RTL Generation

1. Start Cirbuild: `cirbuild`
2. Describe your module
3. Review generated RTL
4. Exit or continue editing

### Workflow 2: Full Design Flow

1. Describe module → Generate RTL
2. Ask questions / Make edits
3. Package for Librelane
4. Run physical design
5. Review PPA metrics
6. Iterate if needed

### Workflow 3: Working with Existing Designs

1. Load existing .v file
2. Ask questions about the design
3. Make modifications
4. Re-run synthesis
5. Run physical design

---

## CLI Command Reference

| Command | Example | Description |
|---------|---------|-------------|
| `/spec` | `/spec design.txt` | Run pipeline on spec file |
| `/load` | `/load design.v` | Load existing Verilog |
| `/workspace` | `/workspace` | List workspace files |
| `/edit` | `/edit alu.v` | Show file for editing |
| `/package` | `/package alu` | Package for Librelane |
| `/run-librelane` | `/run-librelane alu` | Run physical design |
| `/status` | `/status` | Show session status |
| `/clear` | `/clear` | Clear memory |
| `/help` | `/help` | Show commands |
| `/quit` | `/quit` | Exit |

---

## Troubleshooting

### Issue: "No active workspace module"

**Cause:** Trying to access workspace without activating a module.

**Solution:**
1. Run the Spec2RTL pipeline first, or
2. Use `/load` to load an existing file, or
3. Ask agent to "scan workspace for modules"

### Issue: "API key not found"

**Cause:** Missing or incorrect API key.

**Solution:**
1. Check `.env` file exists
2. Verify key format (no quotes, no spaces)
3. Ensure correct prefix (CIRBUILD_ vs SPEC2RTL_)

### Issue: Librelane timeout

**Cause:** Design too complex or system resources low.

**Solution:**
1. Simplify design
2. Increase clock period in config
3. ReduceFP_CORE_UTIL

### Issue: Docker image not found

**Cause:** XLS Docker image not pulled/built.

**Solution:**
```bash
docker pull cirbuildproject/cirbuild-xls:v1
docker tag cirbuildproject/cirbuild-xls:v1 cirbuild-xls:v1
```

---

## Next Steps

- Read [TECH_STACK.md](TECH_STACK.md) for deeper technical details
- Explore the example specifications in the repository
- Join the Cirbuild community for support

---

## Getting Help

- Check the main README.md
- Review environment configuration in env_example.md
- Examine the example specifications

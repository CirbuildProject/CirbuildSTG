# Environment Configuration Guide

This file contains all environment variable placeholders for configuring both the CirbuildSTG frontend agent and the Spec2RTL backend pipeline.

> **Note:** The `.env` file is NOT tracked by git. Copy this template to `.env` and fill in your API keys.

## Quick Setup

```bash
# Copy this file to .env
cp env_example.md .env

# Edit .env with your API keys and preferences
```

---

## CirbuildSTG Frontend (Agent) Configuration

These settings configure the **Cirbuild chat agent** — the AI assistant you interact with through the CLI.

The agent uses **provider-specific API keys** so that primary and fallback models can use different providers without rate-limit conflicts. The key is selected dynamically based on the model string prefix.

| Environment Variable | Required | Default | Description |
|---------------------|----------|---------|-------------|
| `CIRBUILD_OPENROUTER_KEY` | Yes* | — | API key for `openrouter/` models (e.g. OpenRouter) |
| `CIRBUILD_GEMINI_KEY` | Yes* | — | API key for `gemini/` models (Google AI Studio) |
| `CIRBUILD_ANTHROPIC_KEY` | Yes* | — | API key for `anthropic/` models (Anthropic) |
| `CIRBUILD_AGENT_MODEL` | No | `openrouter/minimax/minimax-m2.5` | LLM model for the frontend agent |
| `CIRBUILD_AGENT_TEMPERATURE` | No | `0.3` | Temperature for agent responses |
| `CIRBUILD_AGENT_MAX_TOKENS` | No | `4096` | Max tokens for agent responses |

> * At minimum, set the key for your primary model's provider. Set additional keys only if you configure fallback models from other providers.

### How Key Selection Works

The agent inspects the model string prefix before each API call and injects the matching key:

| Model prefix | Key used |
|---|---|
| `openrouter/...` | `CIRBUILD_OPENROUTER_KEY` |
| `gemini/...` | `CIRBUILD_GEMINI_KEY` |
| `anthropic/...` | `CIRBUILD_ANTHROPIC_KEY` |

This means if your primary model is `openrouter/minimax/minimax-m2.5` and your fallback is `gemini/gemini-2.5-flash`, the agent will automatically use `CIRBUILD_OPENROUTER_KEY` for the primary call and `CIRBUILD_GEMINI_KEY` for the fallback — no extra configuration needed.

### Frontend Example

```bash
# ==========================================
# CirbuildSTG Frontend Agent
# ==========================================

# Provider API Keys (set only the ones you need)
CIRBUILD_OPENROUTER_KEY="sk-or-v1-your-openrouter-key-here"
CIRBUILD_GEMINI_KEY="AIza-your-gemini-key-here"
CIRBUILD_ANTHROPIC_KEY="sk-ant-your-anthropic-key-here"

# Agent Model Override
CIRBUILD_AGENT_MODEL="openrouter/minimax/minimax-m2.5"

# Agent Parameters
CIRBUILD_AGENT_TEMPERATURE=0.3
CIRBUILD_AGENT_MAX_TOKENS=4096
```

---

## Spec2RTL Backend Configuration

These settings configure the **Spec2RTL pipeline** — the RTL generation engine that runs behind the scenes.

The backend uses **provider-specific API keys** (separate from the frontend) to prevent rate-limit conflicts between the two subsystems. The key is selected dynamically based on the model string prefix.

| Environment Variable | Required | Default | Description |
|---------------------|----------|---------|-------------|
| `SPEC2RTL_OPENROUTER_KEY` | Yes* | — | API key for `openrouter/` models (e.g. OpenRouter) |
| `SPEC2RTL_GEMINI_KEY` | Yes* | — | API key for `gemini/` models (Google AI Studio) |
| `SPEC2RTL_ANTHROPIC_KEY` | Yes* | — | API key for `anthropic/` models (Anthropic) |
| `SPEC2RTL_DEFAULT_MODEL` | No | `openrouter/minimax/minimax-m2.5` | Primary LLM for RTL generation |
| `SPEC2RTL_FALLBACK_MODELS` | No | (list) | Fallback models if primary fails |
| `SPEC2RTL_LLM_TEMPERATURE` | No | `0.0` | Temperature for LLM calls |
| `SPEC2RTL_LLM_MAX_TOKENS` | No | `4096` | Max tokens for LLM calls |
| `SPEC2RTL_HLS_COMPILER` | No | `google_xls` | HLS compiler (`google_xls`, `bambu`, `vitis`) |
| `SPEC2RTL_BUILD_DIR` | No | `builds` | Output directory for generated files |
| `SPEC2RTL_LOG_LEVEL` | No | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

> * At minimum, set the key for your primary model's provider. Set additional keys only if you configure fallback models from other providers.

### How Key Selection Works

The pipeline inspects the model string prefix before each API call and injects the matching key:

| Model prefix | Key used |
|---|---|
| `openrouter/...` | `SPEC2RTL_OPENROUTER_KEY` |
| `gemini/...` | `SPEC2RTL_GEMINI_KEY` |
| `anthropic/...` | `SPEC2RTL_ANTHROPIC_KEY` |

### Backend Example

```bash
# ==========================================
# Spec2RTL Backend Pipeline
# ==========================================

# Provider API Keys (set only the ones you need)
SPEC2RTL_OPENROUTER_KEY="sk-or-v1-your-openrouter-key-here"
SPEC2RTL_GEMINI_KEY="AIza-your-gemini-key-here"
SPEC2RTL_ANTHROPIC_KEY="sk-ant-your-anthropic-key-here"

# Model Selection
SPEC2RTL_DEFAULT_MODEL="openrouter/minimax/minimax-m2.5"

# LLM Parameters
SPEC2RTL_LLM_TEMPERATURE=0.0
SPEC2RTL_LLM_MAX_TOKENS=4096

# HLS Compiler
SPEC2RTL_HLS_COMPILER="google_xls"

# Build Settings
SPEC2RTL_BUILD_DIR="builds"
SPEC2RTL_LOG_LEVEL="INFO"
```

---

## Full Configuration Template

```bash
# ==========================================
# CirbuildSTG Unified Environment Configuration
# ==========================================

# ============================================================
# FRONTEND: Cirbuild Agent (Chat Interface)
# ============================================================
# Provider API Keys — key is selected based on model prefix
# Set only the keys for providers you actually use
CIRBUILD_OPENROUTER_KEY="sk-or-v1-your-openrouter-key-here"
CIRBUILD_GEMINI_KEY="AIza-your-gemini-key-here"
CIRBUILD_ANTHROPIC_KEY="sk-ant-your-anthropic-key-here"

# Agent Model Override
CIRBUILD_AGENT_MODEL="openrouter/minimax/minimax-m2.5"

# Agent Parameters
CIRBUILD_AGENT_TEMPERATURE=0.3
CIRBUILD_AGENT_MAX_TOKENS=4096


# ============================================================
# BACKEND: Spec2RTL Pipeline (RTL Generation)
# ============================================================
# Provider API Keys — separate from frontend to avoid rate-limit conflicts
# Key is selected based on model prefix
SPEC2RTL_OPENROUTER_KEY="sk-or-v1-your-openrouter-key-here"
SPEC2RTL_GEMINI_KEY="AIza-your-gemini-key-here"
SPEC2RTL_ANTHROPIC_KEY="sk-ant-your-anthropic-key-here"

# Model Selection
SPEC2RTL_DEFAULT_MODEL="openrouter/minimax/minimax-m2.5"

# LLM Parameters
SPEC2RTL_LLM_TEMPERATURE=0.0
SPEC2RTL_LLM_MAX_TOKENS=4096

# HLS Compiler (google_xls, bambu, vitis)
SPEC2RTL_HLS_COMPILER="google_xls"

# Build Settings
SPEC2RTL_BUILD_DIR="builds"
SPEC2RTL_LOG_LEVEL="INFO"
```

---

## Important Notes

### 1. Priority Order

Configuration is resolved in this priority order (highest wins):
1. **Environment variables** (`.env` file) ← Use this for API keys
2. **YAML config files** ← Use for complex/fallback configurations
3. **Code defaults** ← Pre-configured sensible defaults

### 2. When to Use What

| Use Case | Recommended Method |
|----------|-------------------|
| API keys | `.env` file |
| Single model override | `.env` file |
| Custom fallback models | YAML config file |
| Multiple parameter tuning | YAML config file |
| Testing different configurations | YAML config file |

### 3. YAML vs .env

- **`.env`**: Simple key-value pairs, ideal for API keys and single overrides
- **YAML file**: Complex nested configurations, lists, multiple parameters

For advanced customization (e.g., fallback models list, custom retry counts), edit the YAML config:
- CirbuildSTG: `cirbuild/config/default_config.yaml`
- Spec2RTL: `spec2rtl/config/default_config.yaml`

### 4. Default Models

Both CirbuildSTG and Spec2RTL default to:
```
openrouter/minimax/minimax-m2.5
```

This is a cost-effective, high-performance model available through OpenRouter.

### 5. API Key Security

- **Never commit** `.env` to version control
- The `.env` file is already in `.gitignore`
- Use different API keys for frontend and backend to prevent rate-limit conflicts between the two subsystems

### 6. Provider-Specific Key Design

Both the frontend agent and the backend pipeline use **provider-specific keys** rather than a single shared key. This design:

- **Prevents rate-limit conflicts** — the frontend and backend each have their own quota
- **Enables cross-provider fallbacks** — if your primary model (e.g. `openrouter/`) is rate-limited, the fallback can use a different provider (e.g. `gemini/`) with its own key
- **Remains API-agnostic** — you can mix and match any LiteLLM-supported providers without changing code

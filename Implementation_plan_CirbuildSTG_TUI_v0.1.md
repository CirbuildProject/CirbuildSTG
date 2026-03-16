# Implementation Specification: CirbuildSTG Agentic TUI Workflow

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Module 1: Subsystem Packaging (Cirbuild-Spec2RTL)](#module-1-subsystem-packaging-cirbuild-spec2rtl)
3. [Module 2: State Management & Soft Interrupts (The Core)](#module-2-state-management--soft-interrupts-the-core)
4. [Module 3: Asynchronous Pipeline Integration (CirbuildSTG Core)](#module-3-asynchronous-pipeline-integration-cirbuildstg-core)
5. [Module 4: TUI & Agent Interface](#module-4--tui--agent-interface)
6. [Module 5: CLI Entry & Persona Bootstrap](#module-5-cli-entry--persona-bootstrap)

---

## Architecture Overview

> **Type:** Asynchronous, event-driven Electronic Design Automation (EDA) pipeline  
> **Pattern:** Human-in-the-Loop (HITL) architecture  
> **UI Design:** Text User Interface (TUI) with split-pane design (Chat Agent + Live Logs)

### Core Design Principle

Because the underlying `Spec2RTLPipeline` relies on heavy, synchronous execution blocks (e.g., LLM calls and compilation checks), the orchestrator bridges the gap by running these synchronous blocks inside `asyncio.to_thread()`. This allows the orchestrator to apply **Cooperative Multitasking** (Soft Interrupts via `asyncio.Event`) at the boundaries between major pipeline modules **without freezing the TUI event loop**.

---

## Module 1: Subsystem Packaging (Cirbuild-Spec2RTL)

| Attribute | Details |
|-----------|---------|
| **Intended Function** | Decouple the Spec-to-RTL translation tool so it can be installed via standard `pip` into the CirbuildSTG environment |
| **Dependencies** | `setuptools` (build backend) |

### Implementation Strategy

- **Build Config:** Create a standard `pyproject.toml` in the Cirbuild-Spec2RTL root declaring it as a package.

- **Git Hygiene:** Implement a strict `.gitignore` to prevent committing `build/`, `dist/`, and `*.egg-info/` artifacts.

- **Code Preservation:** The internal codebase of Spec2RTL remains synchronous and unchanged. The pausing and thread management will be handled entirely by the CirbuildSTG wrapper.

---

## Module 2: State Management & Soft Interrupts (The Core)

| Attribute | Details |
|-----------|---------|
| **Intended Function** | Serve as the shared memory space between the TUI Chat Agent and the background pipeline execution task |
| **Dependencies** | `asyncio`, `dataclasses`, `typing` |

### Implementation Strategy

#### State Object
Create a `PipelineState` dataclass containing:

| Field | Type | Description |
|-------|------|-------------|
| `proceed_event` | `asyncio.Event()` | Event to signal pipeline to proceed |
| `pause_requested` | `bool` | Flag triggered by the Agent (defaults to `False`) |
| `current_stage` | `str` | Active pipeline phase (e.g., "Understanding", "Coding", "Synthesis") |
| `current_artifacts` | `dict` / `str` | Intermediate data (e.g., DecompositionPlan, final_cpp) for user review |
| `user_advice` | `str` (optional) | User instructions to inject into the next module |

#### Log Queue
- Initialize an `asyncio.Queue()` to safely pass log records from the Spec2RTLPipeline logger to the TUI.

---

## Module 3: Asynchronous Pipeline Integration (CirbuildSTG Core)

| Attribute | Details |
|-----------|---------|
| **Intended Function** | Adapt the existing Spec2RTLPipeline to run within an async event loop, utilizing thread delegation to keep the UI responsive, and implementing breakpoints between the existing module calls |
| **Dependencies** | Cirbuild-Spec2RTL (via Git pip install) |

### Implementation Strategy

#### Async Refactoring
- Create an async wrapper for `run_from_text`:
  ```python
  async def async_run_from_text(self, spec_text: str, state: PipelineState, target_compiler: str = "Google XLS")
  ```

#### Thread Delegation
- Because functions like `self._module1.run()` are synchronous and heavy, execute them without blocking the UI using:
  ```python
  plan, info_dicts = await asyncio.to_thread(self._module1.run, pages, spec_text)
  ```

#### Checkpoint Injection
Insert lock checks at the natural boundaries of the pipeline:

| Checkpoint | Location | Action |
|------------|----------|--------|
| **Checkpoint 1** | After Module 1 | If `state.pause_requested`: Save `plan.module_name` to `state.current_artifacts`, clear the event, and `await state.proceed_event.wait()` |
| **Checkpoint 2** | After Module 2 / Reflection | If `state.pause_requested`: Save the combined `final_cpp` to `state.current_artifacts`, clear the event, and `await state.proceed_event.wait()` |

#### Context Application
- Upon waking from an `await`, check for `state.user_advice` and append it to the relevant data structures (like `info_dicts`) before passing them to the next module.

#### Logging Override
- Create a custom Python `logging.Handler` that pushes log records into the `asyncio.Queue` instead of standard output, attaching this handler to `logger = logging.getLogger("spec2rtl.pipeline")`.

---

## Module 4: TUI & Agent Interface

| Attribute | Details |
|-----------|---------|
| **Intended Function** | Provide the interactive dashboard that manages the pipeline execution state |
| **Dependencies** | `textual`, `openai` (Async client) |

### Implementation Strategy

#### UI Layout
- Build a Textual app with a CSS grid:
  - **Left Pane:** Chat input + history
  - **Right Pane:** Live pipeline logs via `RichLog`

#### Log Consumer
- Run a background worker in the Textual app that `await log_queue.get()` and writes the output to the Right Pane.

#### Agent Tooling
Equip the LLM client with tools to toggle the pipeline state:

| Tool | Function |
|------|----------|
| `request_pause()` | Sets `state.pause_requested = True` |
| `resume_pipeline(advice)` | Captures user input into `state.user_advice`, sets `state.pause_requested = False`, and calls `state.proceed_event.set()` |

#### Execution Trigger
- When the user provides a specification, the app calls `asyncio.create_task(pipeline.async_run_from_text(...))` to kick off Module 3 in the background.

---

## Module 5: CLI Entry & Persona Bootstrap

| Attribute | Details |
|-----------|---------|
| **Intended Function** | Handle the `Cirbuild -activate` CLI command and initialize the user's role before the TUI starts |
| **Dependencies** | `typer`, `pyyaml` |

### Implementation Strategy

#### Entry Point
- Use Typer to construct the CLI.

#### Profile Load/Create
- Look for `user_profile.yaml`. If absent, prompt the terminal to collect the user's educational/occupational role and intended usage.

#### System Prompt Formatting
- Pass the YAML data into the Textual app's initialization to dictate the Agent's persona (e.g., instructional for students, concise for supervisors).

---

## 📌 Quick Reference Summary

| Module | Name | Key Dependencies |
|--------|------|------------------|
| 1 | Subsystem Packaging | `setuptools` |
| 2 | State Management | `asyncio`, `dataclasses`, `typing` |
| 3 | Async Pipeline Integration | Cirbuild-Spec2RTL |
| 4 | TUI & Agent Interface | `textual`, `openai` |
| 5 | CLI Entry | `typer`, `pyyaml` |

---

*Document Version: v0.1*  
*Project: CirbuildSTG TUI Workflow*

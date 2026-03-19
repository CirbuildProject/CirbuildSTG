"""Librelane RTL-to-GDSII flow runner for the Cirbuild agent.

Generates configuration, invokes the librelane flow via a Nix-shell bridge
subprocess, and parses results.

Architecture (Runner Script / JSON Bridge):
  1. ``run_flow`` builds a ``nix-shell <shell.nix> --run "python nix_bridge.py ..."``
     command and executes it as a subprocess.
  2. ``nix_bridge.py`` (co-located in this package) runs inside the Nix environment
     where EDA binaries are available, calls ``Flow.start()``, and writes the
     structured result to ``<design_dir>/librelane_result.json``.
  3. ``run_flow`` reads that JSON file, appends the subprocess stdout/stderr logs,
     and returns the merged dict to the caller.

Streaming logs:
  stdout and stderr from the nix-shell subprocess are streamed line-by-line to
  the logger in real time (via ``subprocess.Popen`` + thread-based readers) so
  that librelane progress is visible immediately in the terminal rather than
  appearing only after the full run completes.
"""

import json
import logging
import os
import subprocess
import threading
import yaml
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cirbuild.config.settings import CirbuildSettings

logger = logging.getLogger("cirbuild.librelane")

# Path to the bridge script — always co-located with this module.
_BRIDGE_SCRIPT = Path(__file__).parent / "nix_bridge.py"


class LibrelaneRunner:
    """Runner for the Librelane RTL-to-GDSII physical design flow.

    Manages design directories, generates configuration files, and
    invokes the librelane flow as a subprocess.

    Args:
        settings: CirbuildSTG settings.
    """

    def __init__(self, settings: CirbuildSettings | None = None) -> None:
        self._settings = settings or CirbuildSettings.from_yaml()
        self._librelane_path = Path(self._settings.librelane_repo_path).resolve()

    def generate_config(
        self,
        design_dir: Path,
        module_name: str,
        clock_port: str = "clk",
        clock_period: float = 10.0,
        extra_config: Dict[str, Any] | None = None,
    ) -> Path:
        """Generate a librelane config.yaml for the design.

        Creates a minimal but functional config based on the librelane
        SPM example format.

        Args:
            design_dir: Path to the design directory (must contain src/*.v).
            module_name: Top-level module name (DESIGN_NAME).
            clock_port: Clock port name. Defaults to 'clk'.
            clock_period: Target clock period in ns. Defaults to 10.
            extra_config: Additional config overrides.

        Returns:
            Path to the generated config.yaml.
        """
        config: Dict[str, Any] = {
            "DESIGN_NAME": module_name,
            "VERILOG_FILES": "dir::src/*.v",
            "CLOCK_PERIOD": clock_period,
            "CLOCK_PORT": clock_port,
        }

        # Add PDK-specific defaults
        pdk = self._settings.librelane_pdk
        if pdk.startswith("sky130"):
            config["pdk::sky130*"] = {
                "FP_CORE_UTIL": 45,
                "CLOCK_PERIOD": clock_period,
            }
        elif pdk.startswith("gf180"):
            config["pdk::gf180mcu*"] = {
                "FP_CORE_UTIL": 40,
                "CLOCK_PERIOD": clock_period,
                "MAX_FANOUT_CONSTRAINT": 4,
                "PL_TARGET_DENSITY": 0.5,
            }

        # Apply extra overrides
        if extra_config:
            config.update(extra_config)

        config_path = design_dir / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        logger.info("Generated librelane config: %s", config_path)
        return config_path

    def check_existing_runs(self, design_dir: Path) -> List[Dict[str, Any]]:
        """Check for existing librelane runs in the design directory.

        Implements the "checkpoint" feature — allows the agent to detect
        previous runs and offer to show results instead of re-running.

        Args:
            design_dir: Path to the design directory.

        Returns:
            List of dicts with run info (tag, path, timestamp).
        """
        runs_dir = design_dir / "runs"
        if not runs_dir.exists():
            return []

        runs: List[Dict[str, Any]] = []
        for run_dir in sorted(runs_dir.iterdir()):
            if run_dir.is_dir():
                # Try to get modification time
                try:
                    mtime = datetime.fromtimestamp(run_dir.stat().st_mtime)
                    timestamp = mtime.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    timestamp = "unknown"

                run_info: Dict[str, Any] = {
                    "tag": run_dir.name,
                    "path": str(run_dir),
                    "timestamp": timestamp,
                }

                # Check for key output files
                for pattern in ["*.gds", "*.def", "*.v", "*final*"]:
                    found = list(run_dir.rglob(pattern))
                    if found:
                        run_info[f"has_{pattern.replace('*', '')}"] = True

                runs.append(run_info)

        return runs

    def run_flow(
        self,
        design_dir: Path,
        config_path: Path | None = None,
        tag: str | None = None,
        frm: str | None = None,
        to: str | None = None,
        overwrite: bool = False,
        use_programmatic: bool = True,
    ) -> Dict[str, Any]:
        """Execute the librelane physical design flow via the Nix-shell bridge.

        Invokes ``nix-shell <shell.nix> --run "python nix_bridge.py <design_dir>
        <config_path>"`` so that the EDA binaries and librelane programmatic API
        are available inside the Nix environment while the host Python process
        remains isolated.

        After the subprocess exits the method reads
        ``<design_dir>/librelane_result.json`` (written by ``nix_bridge.py``),
        appends the raw subprocess stdout/stderr logs to that dictionary, and
        returns the merged result.

        Args:
            design_dir: Path to the design directory.
            config_path: Path to config.yaml. Auto-detected if None.
            tag: Run tag name (passed as LIBRELANE_TAG env var to the bridge).
            frm: Start from this step (passed as LIBRELANE_FRM env var).
            to: Stop after this step (passed as LIBRELANE_TO env var).
            overwrite: Whether to overwrite existing runs (passed as env var).
            use_programmatic: Unused — kept for API compatibility.

        Returns:
            Dict with run results including success status, paths, metrics, and
            subprocess logs.  Always contains at least ``success``, ``method``,
            ``stdout``, and ``stderr`` keys.
        """
        if config_path is None:
            config_path = design_dir / "config.yaml"

        if not config_path.exists():
            return {
                "success": False,
                "error": f"Config file not found: {config_path}. Run package_for_librelane first.",
            }

        # ------------------------------------------------------------------ #
        # Locate shell.nix — prefer LIBRELANE_DIR env var, fall back to the
        # settings-configured repo path.
        # ------------------------------------------------------------------ #
        librelane_dir = os.environ.get(
            "LIBRELANE_DIR",
            str(Path(self._settings.librelane_repo_path).resolve()),
        )
        shell_nix = Path(librelane_dir) / "shell.nix"

        result_json_path = design_dir / "librelane_result.json"

        # ------------------------------------------------------------------ #
        # Build the nix-shell command
        # ------------------------------------------------------------------ #
        inner_cmd = (
            f"python -u {_BRIDGE_SCRIPT} "
            f"{design_dir.resolve()} "
            f"{config_path.resolve()}"
        )
        cmd = ["nix-shell", str(shell_nix), "--run", inner_cmd]

        # Pass PDK settings and optional flow parameters via environment so
        # the bridge script can pick them up without extra CLI parsing.
        bridge_env = {
            **os.environ,
            "LIBRELANE_DIR": librelane_dir,
            "LIBRELANE_PDK": self._settings.librelane_pdk,
            "LIBRELANE_PDK_ROOT": str(
                Path(self._settings.librelane_pdk_root).expanduser()
            ),
        }
        if tag:
            bridge_env["LIBRELANE_TAG"] = tag
        if frm:
            bridge_env["LIBRELANE_FRM"] = frm
        if to:
            bridge_env["LIBRELANE_TO"] = to
        if overwrite:
            bridge_env["LIBRELANE_OVERWRITE"] = "1"

        logger.info("=" * 80)
        logger.info("LIBRELANE NIX-BRIDGE EXECUTION STARTING")
        logger.info("Command: %s", " ".join(cmd))
        logger.info("Bridge script: %s", _BRIDGE_SCRIPT)
        logger.info("shell.nix: %s", shell_nix)
        logger.info("Design dir: %s", design_dir)
        logger.info("Config: %s", config_path)
        logger.info("=" * 80)

        stdout_lines: List[str] = []
        stderr_lines: List[str] = []
        returncode: int = -1

        def _stream_pipe(pipe, line_store: List[str], log_fn) -> None:
            """Read *pipe* line-by-line, log each line immediately, and collect."""
            try:
                for raw in iter(pipe.readline, ""):
                    line = raw.rstrip("\n")
                    line_store.append(line)
                    if line.strip():
                        sys.stdout.write(line + "\n") # Stream straight to terminal
                        sys.stdout.flush()
                        log_fn(line)
            finally:
                pipe.close()

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,          # line-buffered
                cwd=str(design_dir),
                env=bridge_env,
            )

            logger.info("=" * 80)
            logger.info("NIX-BRIDGE LIVE OUTPUT")
            logger.info("=" * 80)

            # Drain stdout and stderr concurrently so neither pipe blocks.
            t_out = threading.Thread(
                target=_stream_pipe,
                args=(proc.stdout, stdout_lines, logger.info),
                daemon=True,
            )
            t_err = threading.Thread(
                target=_stream_pipe,
                args=(proc.stderr, stderr_lines, logger.warning),
                daemon=True,
            )
            t_out.start()
            t_err.start()

            try:
                proc.wait(timeout=3600)  # 1 hour timeout
            except subprocess.TimeoutExpired:
                proc.kill()
                t_out.join(timeout=5)
                t_err.join(timeout=5)
                return {
                    "success": False,
                    "method": "nix_bridge",
                    "error": "Librelane nix-bridge flow timed out after 1 hour.",
                    "stdout": "\n".join(stdout_lines),
                    "stderr": "\n".join(stderr_lines),
                }

            t_out.join()
            t_err.join()
            returncode = proc.returncode

            logger.info("=" * 80)
            logger.info("NIX-BRIDGE FINISHED (exit code %d)", returncode)
            logger.info("=" * 80)

        except FileNotFoundError:
            return {
                "success": False,
                "method": "nix_bridge",
                "error": (
                    "nix-shell not found. Ensure Nix is installed and 'nix-shell' "
                    f"is on PATH. shell.nix expected at: {shell_nix}"
                ),
                "stdout": "\n".join(stdout_lines),
                "stderr": "\n".join(stderr_lines),
            }
        except Exception as exc:
            return {
                "success": False,
                "method": "nix_bridge",
                "error": f"Unexpected error launching nix-shell: {str(exc)}",
                "stdout": "\n".join(stdout_lines),
                "stderr": "\n".join(stderr_lines),
            }

        stdout_full = "\n".join(stdout_lines)
        stderr_full = "\n".join(stderr_lines)

        # ------------------------------------------------------------------ #
        # Read the JSON result written by nix_bridge.py
        # ------------------------------------------------------------------ #
        output: Dict[str, Any]
        if result_json_path.exists():
            try:
                output = json.loads(result_json_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("Failed to parse librelane_result.json: %s", exc)
                output = {
                    "success": False,
                    "method": "nix_bridge",
                    "error": f"Could not parse librelane_result.json: {exc}",
                }
        else:
            # Bridge did not produce a result file — synthesise an error dict
            error_lines = [
                line.strip()
                for line in (stdout_full + "\n" + stderr_full).split("\n")
                if line.strip() and any(
                    kw in line.lower()
                    for kw in ["error", "failed", "fatal", "exception", "abort"]
                )
            ]
            error_summary = "; ".join(error_lines[:5]) if error_lines else (
                f"nix-shell exited with code {returncode}"
            )
            output = {
                "success": False,
                "method": "nix_bridge",
                "error": f"librelane_result.json not found after bridge run. {error_summary}",
            }

        # ------------------------------------------------------------------ #
        # Append subprocess logs and return
        # ------------------------------------------------------------------ #
        output["stdout"] = stdout_full
        output["stderr"] = stderr_full
        output["return_code"] = returncode
        output.setdefault("design_dir", str(design_dir))

        if output.get("success"):
            logger.info("✅ Librelane nix-bridge flow completed successfully")
            runs = self.check_existing_runs(design_dir)
            if runs:
                output["latest_run"] = runs[-1]
        else:
            error_diagnosis = self._diagnose_exit_code(
                returncode, output.get("error")
            )
            logger.error("❌ Librelane nix-bridge flow failed")
            logger.error("Exit Code: %d", returncode)
            logger.error("Error: %s", output.get("error", "Unknown error"))
            logger.error("Diagnosis: %s", error_diagnosis)
            output["error_diagnosis"] = error_diagnosis
            output["exit_code"] = returncode

        return output


    def _diagnose_exit_code(self, exit_code: int, error_message: Optional[str] = None) -> str:
        """Diagnose librelane exit codes and provide helpful guidance.

        Args:
            exit_code: The exit code from librelane execution.
            error_message: Optional error message extracted from stderr.

        Returns:
            Diagnosis string with explanation and suggested fixes.
        """
        diagnosis_map = {
            1: (
                "GENERAL ERROR - Check logs above for details. Common causes:\n"
                "  - Verilog syntax errors in src/*.v files\n"
                "  - Missing or invalid config.yaml\n"
                "  - PDK setup issues (wrong PDK_ROOT or PDK name)"
            ),
            2: (
                "COMMAND LINE ERROR - Verify librelane invocation:\n"
                "  - Check that librelane is installed: python -m librelane --version\n"
                "  - Verify config.yaml path is correct\n"
                "  - Check PDK_ROOT and PDK name settings"
            ),
            127: (
                "COMMAND NOT FOUND - librelane executable not accessible:\n"
                "  - Ensure librelane is installed: pip install librelane\n"
                "  - Verify Python environment is activated\n"
                "  - Check PATH includes librelane installation"
            ),
            124: (
                "TIMEOUT - Librelane execution exceeded 1 hour:\n"
                "  - Design is too complex for current settings\n"
                "  - Try: reduce FP_CORE_UTIL, increase CLOCK_PERIOD\n"
                "  - Check if design has routing loops (congestion)"
            ),
            -9: (
                "KILLED BY SIGNAL - Process forcibly terminated:\n"
                "  - Out of memory (OOM) - Check available RAM\n"
                "  - System resource limit exceeded\n"
                "  - Try: reduce parallelism, simplify design"
            ),
            -15: (
                "SIGTERM - Process terminated:\n"
                "  - User cancelled or system shutdown\n"
                "  - Resource limit hit (memory, CPU)\n"
                "  - Check system logs for details"
            ),
        }

        diagnosis = diagnosis_map.get(exit_code)
        
        if diagnosis:
            return diagnosis

        # Generic diagnosis for unknown exit codes
        if error_message and "out of memory" in error_message.lower():
            return (
                "OUT OF MEMORY ERROR - Librelane ran out of available RAM:\n"
                "  - Available RAM for design is insufficient\n"
                "  - Try: close other applications\n"
                "  - Or: reduce FP_CORE_UTIL, split design into smaller blocks"
            )
        elif error_message and "permission denied" in error_message.lower():
            return (
                "PERMISSION DENIED - Cannot access required files/directories:\n"
                "  - Check directory and file permissions\n"
                "  - Ensure workspace is writable\n"
                "  - Verify PDK files are readable"
            )
        elif error_message and "not found" in error_message.lower():
            return (
                "FILE/TOOL NOT FOUND - Missing required files or tools:\n"
                "  - Check Verilog files exist in src/\n"
                "  - Verify PDK installation is complete\n"
                "  - Check for missing dependencies (yosys, openroad, magic, etc.)"
            )
        else:
            return (
                f"EXIT CODE {exit_code} - Unknown error\n"
                "  - Check logs above for error messages\n"
                "  - Common issues: syntax errors, missing files, PDK setup\n"
                "  - Consider running: python -m librelane --help"
            )
        
    def _format_metrics_for_storage(self, metrics: Dict[str, Any], module_name: str) -> str:
        """Format state metrics into a readable string for RAG storage."""
        lines = [f"=== Programmatic Metrics for {module_name} ==="]
        for key, value in metrics.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)
    
    def parse_run_results(self, run_dir: Path) -> Dict[str, Any]:
        """Parse results from a completed librelane run.

        Looks for key output files and extracts PPA metrics
        from report files.

        Args:
            run_dir: Path to a specific run directory.

        Returns:
            Dict with parsed results (area, timing, power, output files).
        """
        results: Dict[str, Any] = {
            "run_dir": str(run_dir),
            "outputs": {},
            "metrics": {},
        }

        if not run_dir.exists():
            results["error"] = f"Run directory not found: {run_dir}"
            return results

        # Look for key output files
        output_patterns = {
            "gds": "**/*.gds",
            "def": "**/*final*.def",
            "netlist": "**/*final*.nl.v",
            "sdc": "**/*.sdc",
            "spef": "**/*.spef",
        }

        for name, pattern in output_patterns.items():
            found = list(run_dir.glob(pattern))
            if found:
                results["outputs"][name] = [str(f) for f in found]

        # Try to parse timing/area reports
        report_patterns = [
            "**/*sta*summary*",
            "**/*area*",
            "**/*power*",
            "**/*metrics*",
        ]

        for pattern in report_patterns:
            for report_file in run_dir.glob(pattern):
                try:
                    content = report_file.read_text(encoding="utf-8", errors="ignore")
                    results["metrics"][report_file.name] = content[:1000]
                except Exception:
                    pass

        return results

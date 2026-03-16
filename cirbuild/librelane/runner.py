"""Librelane RTL-to-GDSII flow runner for the Cirbuild agent.

Generates configuration, invokes the librelane flow as a subprocess,
and parses results. Replaces the stub in spec2rtl/librelane/.
"""

import logging
import subprocess
import sys
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cirbuild.config.settings import CirbuildSettings

logger = logging.getLogger("cirbuild.librelane")


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
    ) -> Dict[str, Any]:
        """Execute the librelane physical design flow.

        Invokes ``python -m librelane`` as a subprocess with the
        appropriate arguments.

        Args:
            design_dir: Path to the design directory.
            config_path: Path to config.yaml. Auto-detected if None.
            tag: Run tag name. Auto-generated if None.
            frm: Start from this step (e.g., 'Synthesis').
            to: Stop after this step (e.g., 'Floorplan').
            overwrite: Whether to overwrite existing runs with same tag.

        Returns:
            Dict with run results including success status, paths, and logs.
        """
        if config_path is None:
            config_path = design_dir / "config.yaml"

        if not config_path.exists():
            return {
                "success": False,
                "error": f"Config file not found: {config_path}. Run package_for_librelane first.",
            }

        # Build command
        cmd = [
            sys.executable, "-m", "librelane",
            "--pdk-root", str(Path(self._settings.librelane_pdk_root).expanduser()),
            "--pdk", self._settings.librelane_pdk,
        ]

        if tag:
            cmd.extend(["--tag", tag])
        if frm:
            cmd.extend(["--frm", frm])
        if to:
            cmd.extend(["--to", to])
        if overwrite:
            cmd.append("--overwrite")

        cmd.append(str(config_path))

        logger.info("Running librelane: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(design_dir),
                timeout=3600,  # 1 hour timeout
            )

            output: Dict[str, Any] = {
                "success": result.returncode == 0,
                "return_code": result.returncode,
                "stdout_tail": result.stdout[-2000:] if result.stdout else "",
                "stderr_tail": result.stderr[-2000:] if result.stderr else "",
                "design_dir": str(design_dir),
            }

            if result.returncode == 0:
                logger.info("✅ Librelane flow completed successfully")
                # Try to find the latest run directory
                runs = self.check_existing_runs(design_dir)
                if runs:
                    output["latest_run"] = runs[-1]
            else:
                logger.error("❌ Librelane flow failed (exit code %d)", result.returncode)
                output["error"] = f"Flow failed with exit code {result.returncode}"

            return output

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Librelane flow timed out after 1 hour.",
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": (
                    "Could not find Python or librelane. "
                    f"Ensure librelane is installed and accessible. "
                    f"Repo path: {self._librelane_path}"
                ),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": f"Unexpected error: {str(exc)}",
            }

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

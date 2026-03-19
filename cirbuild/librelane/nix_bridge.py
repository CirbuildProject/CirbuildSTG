"""Librelane Nix Bridge Script.

Standalone script invoked inside a nix-shell environment where the EDA binaries
and librelane programmatic API are available.  The main runner (runner.py) calls
this script via ``nix-shell --run "python nix_bridge.py <design_dir> <config_path>"``
so that process isolation is maintained between the host Python environment and
the Nix-managed EDA environment.

Usage:
    python nix_bridge.py <design_dir> <config_path>

Outputs:
    <design_dir>/librelane_result.json  — JSON file with flow results, metrics,
    and any error information.  The runner reads this file after the subprocess
    exits to obtain structured results.
"""

import json
import os
import sys
import traceback
from pathlib import Path


def _extract_metrics_from_state(state, flow=None):
    """Extract PPA and quality metrics from a librelane State object.

    Args:
        state: The State object returned from Flow.start().
        flow: The Flow instance that produced the state (optional).

    Returns:
        Dict with extracted metrics.
    """
    metrics = {"state_dict": {}}

    try:
        if hasattr(state, "metrics") and state.metrics:
            metrics["state_dict"] = dict(state.metrics)
    except Exception as exc:
        metrics["state_dict_error"] = str(exc)

    try:
        step_objects = getattr(flow, "step_objects", None) if flow is not None else None
        if step_objects and isinstance(step_objects, list):
            metrics["step_metrics"] = {}
            for step_obj in step_objects:
                step_name = getattr(step_obj, "id", str(step_obj))
                step_data = {"name": step_name}
                for attr in ["result", "metrics", "output", "files", "reports"]:
                    if hasattr(step_obj, attr):
                        try:
                            step_data[attr] = getattr(step_obj, attr)
                        except Exception:
                            pass
                metrics["step_metrics"][step_name] = step_data
    except Exception as exc:
        metrics["step_metrics_error"] = str(exc)

    return metrics


def _make_json_serializable(obj):
    """Recursively convert an object to a JSON-serialisable form.

    librelane State/Step objects may contain Path instances, enums, or other
    non-serialisable types.  This helper converts them to strings so that
    json.dump() does not raise.
    """
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_serializable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    # Anything that is not a basic JSON type gets stringified
    if not isinstance(obj, (str, int, float, bool, type(None))):
        try:
            return str(obj)
        except Exception:
            return "<unserializable>"
    return obj


def main():
    if len(sys.argv) < 3:
        error_payload = {
            "success": False,
            "method": "nix_bridge",
            "error": (
                "nix_bridge.py requires exactly two positional arguments: "
                "<design_dir> <config_path>"
            ),
        }
        print(json.dumps(error_payload), file=sys.stderr)
        sys.exit(1)

    design_dir = Path(sys.argv[1]).resolve()
    config_path = Path(sys.argv[2]).resolve()
    result_path = design_dir / "librelane_result.json"

    # ------------------------------------------------------------------ #
    # Resolve LIBRELANE_DIR — used to locate the librelane package when it
    # is not installed as a regular pip package in the Nix environment.
    # ------------------------------------------------------------------ #
    librelane_dir = os.environ.get("LIBRELANE_DIR", "")
    if librelane_dir:
        librelane_dir_path = Path(librelane_dir).resolve()
        if librelane_dir_path.exists() and str(librelane_dir_path) not in sys.path:
            sys.path.insert(0, str(librelane_dir_path))

    # ------------------------------------------------------------------ #
    # Import librelane programmatic API
    # ------------------------------------------------------------------ #
    try:
        from librelane.flows import Flow, FlowException, FlowError  # noqa: F401
    except ImportError as exc:
        payload = {
            "success": False,
            "method": "nix_bridge",
            "error": f"Cannot import librelane: {exc}. LIBRELANE_DIR={librelane_dir!r}",
        }
        result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload), file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Validate inputs
    # ------------------------------------------------------------------ #
    if not config_path.exists():
        payload = {
            "success": False,
            "method": "nix_bridge",
            "error": f"Config file not found: {config_path}",
        }
        result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Run the flow
    # ------------------------------------------------------------------ #
    pdk = os.environ.get("LIBRELANE_PDK", "sky130A")
    pdk_root = os.environ.get("LIBRELANE_PDK_ROOT", os.path.expanduser("~/.ciel"))

    output = {
        "success": False,
        "method": "nix_bridge",
        "design_dir": str(design_dir),
        "config_path": str(config_path),
        "pdk": pdk,
        "pdk_root": pdk_root,
    }

    try:
        ClassicFlow = Flow.factory.get("Classic")
        if ClassicFlow is None:
            output["error"] = "Classic flow not found in Flow.factory"
            result_path.write_text(
                json.dumps(_make_json_serializable(output), indent=2), encoding="utf-8"
            )
            sys.exit(1)

        flow = ClassicFlow(
            str(config_path),
            pdk=pdk,
            pdk_root=pdk_root,
        )

        final_state = flow.start()
        metrics = _extract_metrics_from_state(final_state, flow)

        output["success"] = True
        output["metrics"] = metrics
        output["state_available"] = True

        print("✅ nix_bridge: Librelane flow completed successfully", flush=True)

    except (FlowException, FlowError) as exc:
        output["success"] = False
        output["error"] = f"Flow exception: {str(exc)}"
        output["traceback"] = traceback.format_exc()
        print(f"❌ nix_bridge: Flow exception: {exc}", file=sys.stderr, flush=True)

    except Exception as exc:
        output["success"] = False
        output["error"] = f"Unexpected error: {str(exc)}"
        output["traceback"] = traceback.format_exc()
        print(f"❌ nix_bridge: Unexpected error: {exc}", file=sys.stderr, flush=True)

    # ------------------------------------------------------------------ #
    # Write result JSON
    # ------------------------------------------------------------------ #
    try:
        serialisable = _make_json_serializable(output)
        result_path.write_text(json.dumps(serialisable, indent=2), encoding="utf-8")
        print(f"nix_bridge: Result written to {result_path}", flush=True)
    except Exception as exc:
        # Last-resort: write a minimal error payload
        fallback = {
            "success": False,
            "method": "nix_bridge",
            "error": f"Failed to serialise result: {exc}",
        }
        result_path.write_text(json.dumps(fallback, indent=2), encoding="utf-8")

    sys.exit(0 if output.get("success") else 1)


if __name__ == "__main__":
    main()

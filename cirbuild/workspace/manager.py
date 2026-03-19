"""Verilog workspace manager for the Cirbuild agent.

Provides a dedicated directory for editing RTL files produced by
the spec2rtl pipeline, with automatic history snapshots for undo.
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("cirbuild.workspace")


class WorkspaceManager:
    """Manages a dedicated workspace for Verilog/SystemVerilog editing.

    Structure::

        workspace_root/
        └── <module_name>/
            ├── <module_name>.v
            ├── <module_name>_tb.v
            └── .history/
                ├── 001_<module_name>.v
                └── 002_<module_name>.v

    Args:
        workspace_root: Root directory for all workspaces.
    """

    def __init__(self, workspace_root: Path) -> None:
        self._root = Path(workspace_root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._active_module: Optional[str] = None

    @property
    def active_module(self) -> Optional[str]:
        """The currently active module name."""
        return self._active_module

    @property
    def active_dir(self) -> Optional[Path]:
        """Path to the active module's workspace directory."""
        if self._active_module:
            return self._root / self._active_module
        return None

    def _safe_path(self, filename: str) -> Path:
        """Resolve filename and ensure it stays within the active workspace."""
        if not self._active_module:
            raise RuntimeError(
                "No active workspace module. "
                "Use scan_workspace to find existing modules in cirbuild_workspace/, "
                "then activate_workspace_module to select one. "
                "Or run the Spec2RTL pipeline to generate a new module."
            )
        module_dir = (self._root / self._active_module).resolve()
        resolved = (module_dir / filename).resolve()
        if not resolved.is_relative_to(module_dir):
            raise ValueError(f"Path traversal detected: {filename!r}")
        return resolved

    def activate_module(self, module_name: str) -> Path:
        """Activate an existing workspace module without copying any files.

        Use this when the user has manually placed files in the workspace
        directory and wants the agent to work with them directly.

        Args:
            module_name: Name of the module directory under workspace_root.

        Returns:
            Path to the module's workspace directory.

        Raises:
            FileNotFoundError: If the module directory does not exist.
        """
        safe_name = (
            str(module_name).strip().lower().replace(" ", "_").replace("-", "_")
        )
        module_dir = self._root / safe_name
        if not module_dir.exists():
            raise FileNotFoundError(
                f"Workspace directory not found: {module_dir}. "
                "Check that the module name matches the directory name."
            )
        self._active_module = safe_name
        logger.info("Activated workspace module: %s", safe_name)
        return module_dir

    def scan_for_modules(self) -> List[Dict]:
        """Scan the workspace root for existing module directories.

        Returns all subdirectories that contain at least one .v or .sv file.
        Useful when the user has manually placed files in the workspace.

        Returns:
            List of dicts with keys: module_name, directory, files.
        """
        found: List[Dict] = []
        if not self._root.exists():
            return found

        for entry in sorted(self._root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            verilog_files = [
                f.name
                for f in entry.iterdir()
                if f.is_file() and f.suffix.lower() in (".v", ".sv") and not f.name.startswith(".")
            ]
            if verilog_files:
                found.append({
                    "module_name": entry.name,
                    "directory": str(entry),
                    "files": verilog_files,
                })

        return found

    def init_from_synthesis(
        self,
        rtl_path: str,
        module_name: str,
    ) -> Path:
        """Initialize workspace from a synthesis result.

        Copies the generated RTL file into a new workspace directory
        and sets it as the active module.

        Args:
            rtl_path: Path to the generated RTL file.
            module_name: Name of the hardware module.

        Returns:
            Path to the workspace directory.
        """
        # Validate and sanitize module_name
        if not module_name or not str(module_name).strip():
            # Fallback to RTL filename if module_name is empty/None
            rtl_file = Path(rtl_path).stem
            module_name = rtl_file or "unknown_module"
            logger.warning(
                "Module name was empty; using RTL filename fallback: %s",
                module_name,
            )
        
        safe_name = (
            str(module_name).strip().lower().replace(" ", "_").replace("-", "_")
        )
        module_dir = self._root / safe_name
        module_dir.mkdir(parents=True, exist_ok=True)

        # Create history directory
        history_dir = module_dir / ".history"
        history_dir.mkdir(exist_ok=True)

        # Copy RTL file with standardized naming
        src = Path(rtl_path)
        if src.exists():
            # Use module name for the RTL file, preserving extension
            rtl_extension = src.suffix  # e.g., ".v" or ".sv"
            dest_filename = f"{safe_name}{rtl_extension}"
            dest = module_dir / dest_filename
            shutil.copy2(src, dest)
            # Save initial version to history
            self._save_history(dest)
            logger.info(
                "Initialized workspace for '%s' from %s → %s",
                safe_name, src.name, dest_filename
            )
        else:
            logger.warning("RTL file not found: %s", rtl_path)

        self._active_module = safe_name
        return module_dir

    def read_file(self, filename: str) -> str:
        """Read a file from the active workspace.

        Args:
            filename: Name of the file to read.

        Returns:
            File contents as a string.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            RuntimeError: If no workspace is active.
            ValueError: If the path escapes the workspace sandbox.
        """
        file_path = self._safe_path(filename)
        if not file_path.exists():
            raise FileNotFoundError(
                f"File not found in workspace: {filename}"
            )

        return file_path.read_text(encoding="utf-8")

    def write_file(self, filename: str, content: str) -> Path:
        """Write a file to the active workspace with history snapshot.

        Args:
            filename: Name of the file to write.
            content: Full file content.

        Returns:
            Path to the written file.

        Raises:
            RuntimeError: If no workspace is active.
            ValueError: If the path escapes the workspace sandbox.
        """
        file_path = self._safe_path(filename)

        # Save history before overwriting
        if file_path.exists():
            self._save_history(file_path)

        file_path.write_text(content, encoding="utf-8")
        logger.info("Wrote %s to workspace", filename)
        return file_path

    def list_files(self) -> List[str]:
        """List all files in the active workspace (excluding .history).

        Returns:
            List of filenames.

        Raises:
            RuntimeError: If no workspace is active.
        """
        if not self._active_module:
            raise RuntimeError(
                "No active workspace module. "
                "Use scan_workspace to find existing modules in cirbuild_workspace/, "
                "then activate_workspace_module to select one. "
                "Or run the Spec2RTL pipeline to generate a new module."
            )

        module_dir = self._root / self._active_module
        if not module_dir.exists():
            return []

        files = []
        for f in sorted(module_dir.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                files.append(f.name)
        return files

    def get_history(self, filename: str) -> List[Path]:
        """Get history snapshots for a file.

        Args:
            filename: Name of the file.

        Returns:
            List of history file paths, oldest first.
        """
        if not self._active_module:
            return []

        history_dir = self._root / self._active_module / ".history"
        if not history_dir.exists():
            return []

        stem = Path(filename).stem
        suffix = Path(filename).suffix
        pattern = f"*_{stem}{suffix}"

        return sorted(history_dir.glob(pattern))

    def _save_history(self, file_path: Path) -> None:
        """Save a snapshot of a file to the history directory."""
        if not file_path.exists():
            return

        history_dir = file_path.parent / ".history"
        history_dir.mkdir(exist_ok=True)

        # Find the highest existing snapshot number
        stem = file_path.stem
        suffix = file_path.suffix
        existing = list(history_dir.glob(f"*_{stem}{suffix}"))

        max_num = 0
        for snap in existing:
            try:
                num = int(snap.stem.split("_", 1)[0])
                max_num = max(max_num, num)
            except (ValueError, IndexError):
                pass

        next_num = max_num + 1
        snapshot_name = f"{next_num:03d}_{stem}{suffix}"
        snapshot_path = history_dir / snapshot_name
        shutil.copy2(file_path, snapshot_path)
        logger.debug("Saved history snapshot: %s", snapshot_name)

    def package_for_librelane(
        self,
        target_dir: Path,
        module_name: Optional[str] = None,
    ) -> List[Path]:
        """Package workspace files into a librelane-compatible directory.

        Creates the directory structure expected by librelane::

            target_dir/
            └── src/
                └── *.v

        Args:
            target_dir: Target directory for the librelane design.
            module_name: Module name override. Uses active module if None.

        Returns:
            List of copied file paths.
        """
        mod = module_name or self._active_module
        if not mod:
            raise RuntimeError(
                "No active workspace module. "
                "Use scan_workspace to find existing modules in cirbuild_workspace/, "
                "then activate_workspace_module to select one. "
                "Or run the Spec2RTL pipeline to generate a new module."
            )

        module_dir = self._root / mod
        if not module_dir.exists():
            raise FileNotFoundError(
                f"Workspace not found for module: {mod}"
            )

        # Create librelane src directory
        src_dir = target_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        copied: List[Path] = []
        for f in module_dir.iterdir():
            if (
                f.is_file()
                and f.suffix in (".v", ".sv")
                and not f.name.startswith(".")
            ):
                dest = src_dir / f.name
                shutil.copy2(f, dest)
                copied.append(dest)
                logger.info("Packaged %s → %s", f.name, dest)

        return copied

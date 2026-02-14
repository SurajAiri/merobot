"""Sandboxed file read/write tools."""

from pathlib import Path
from typing import Any

from loguru import logger

from merobot.config import get_config
from merobot.constants import TOOL_MAX_READ_BYTES, TOOL_MAX_WRITE_BYTES
from merobot.tools.base import BaseTool


def _get_sandbox_root() -> Path:
    """Get the sandbox root from config (agent.workspace_path)."""
    return get_config().agent.resolved_workspace


def _resolve_safe_path(user_path: str, sandbox: Path) -> Path | str:
    """
    Resolve a user-provided path within the sandbox.

    Returns the resolved Path if safe, or an error string if not.
    """
    candidate = Path(user_path)
    if not candidate.is_absolute():
        candidate = sandbox / candidate

    resolved = candidate.resolve()

    try:
        resolved.relative_to(sandbox)
    except ValueError:
        return (
            f"Error: Path '{user_path}' resolves to '{resolved}' "
            f"which is outside the allowed workspace '{sandbox}'."
        )

    return resolved


class FileReadTool(BaseTool):
    """
    Read file contents from within the sandboxed workspace directory.
    """

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        sandbox = _get_sandbox_root()
        return (
            f"Read the contents of a file from the workspace directory ({sandbox}). "
            "Paths can be relative (to workspace) or absolute (must be within workspace). "
            "Cannot access files outside the workspace for security."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to read (relative to workspace or absolute within it).",
                    "minLength": 1,
                },
                "max_bytes": {
                    "type": "integer",
                    "description": f"Maximum bytes to read. Default & max: {TOOL_MAX_READ_BYTES} (1 MB).",
                    "minimum": 1,
                    "maximum": TOOL_MAX_READ_BYTES,
                },
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        user_path: str = kwargs.get("path", "").strip()
        max_bytes: int = kwargs.get("max_bytes", TOOL_MAX_READ_BYTES)

        if not user_path:
            return "Error: 'path' parameter is required."

        sandbox = _get_sandbox_root()
        max_bytes = max(1, min(TOOL_MAX_READ_BYTES, max_bytes))

        if not sandbox.exists():
            return f"Error: Workspace directory '{sandbox}' does not exist. Create it first."

        result = _resolve_safe_path(user_path, sandbox)
        if isinstance(result, str):
            return result
        filepath: Path = result

        if not filepath.exists():
            return f"Error: File not found — '{user_path}' (resolved: {filepath})"

        if not filepath.is_file():
            if filepath.is_dir():
                return self._list_directory(filepath, sandbox)
            return f"Error: '{user_path}' is not a regular file."

        logger.info(f"File read: {filepath}")

        try:
            size = filepath.stat().st_size
            if size > max_bytes:
                content = filepath.read_text(encoding="utf-8", errors="replace")[:max_bytes]
                return (
                    f"**File**: {filepath.relative_to(sandbox)}\n"
                    f"**Size**: {size:,} bytes (showing first {max_bytes:,})\n\n"
                    f"```\n{content}\n```\n\n"
                    f"*[...truncated, {size - max_bytes:,} bytes remaining]*"
                )
            else:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                return (
                    f"**File**: {filepath.relative_to(sandbox)}\n"
                    f"**Size**: {size:,} bytes\n\n"
                    f"```\n{content}\n```"
                )
        except PermissionError:
            return f"Error: Permission denied reading '{user_path}'."
        except Exception as e:
            logger.error(f"File read error: {e}")
            return f"Error: Could not read file — {type(e).__name__}: {e}"

    @staticmethod
    def _list_directory(dirpath: Path, sandbox: Path) -> str:
        """List directory contents as a helpful fallback."""
        try:
            entries = sorted(dirpath.iterdir())
            lines = [
                f"**Directory**: {dirpath.relative_to(sandbox)}/\n",
                f"**Contents** ({len(entries)} items):\n",
            ]
            for entry in entries[:50]:
                icon = "📁" if entry.is_dir() else "📄"
                size = ""
                if entry.is_file():
                    size = f" ({entry.stat().st_size:,} bytes)"
                lines.append(f"- {icon} {entry.name}{size}")

            if len(entries) > 50:
                lines.append(f"\n*...and {len(entries) - 50} more entries*")

            return "\n".join(lines)
        except Exception as e:
            return f"Error listing directory: {e}"


class FileWriteTool(BaseTool):
    """
    Write or append content to files within the sandboxed workspace directory.
    """

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        sandbox = _get_sandbox_root()
        return (
            f"Write or append content to a file in the workspace directory ({sandbox}). "
            "Creates parent directories automatically. "
            "Cannot write outside the workspace for security."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to write (relative to workspace or absolute within it).",
                    "minLength": 1,
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file.",
                },
                "mode": {
                    "type": "string",
                    "description": "Write mode: 'write' (overwrite) or 'append'. Default: 'write'.",
                    "enum": ["write", "append"],
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, **kwargs: Any) -> str:
        user_path: str = kwargs.get("path", "").strip()
        content: str = kwargs.get("content", "")
        mode: str = kwargs.get("mode", "write").strip()

        if not user_path:
            return "Error: 'path' parameter is required."

        sandbox = _get_sandbox_root()

        content_bytes = len(content.encode("utf-8"))
        if content_bytes > TOOL_MAX_WRITE_BYTES:
            return (
                f"Error: Content is {content_bytes:,} bytes, "
                f"exceeds maximum of {TOOL_MAX_WRITE_BYTES:,} bytes (5 MB)."
            )

        sandbox.mkdir(parents=True, exist_ok=True)

        result = _resolve_safe_path(user_path, sandbox)
        if isinstance(result, str):
            return result
        filepath: Path = result

        logger.info(f"File write ({mode}): {filepath}")

        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)

            if mode == "append":
                with open(filepath, "a", encoding="utf-8") as f:
                    f.write(content)
                action = "Appended to"
            else:
                filepath.write_text(content, encoding="utf-8")
                action = "Wrote"

            final_size = filepath.stat().st_size

            return (
                f"✅ {action} file successfully.\n"
                f"**Path**: {filepath.relative_to(sandbox)}\n"
                f"**Written**: {content_bytes:,} bytes\n"
                f"**Total size**: {final_size:,} bytes"
            )
        except PermissionError:
            return f"Error: Permission denied writing to '{user_path}'."
        except Exception as e:
            logger.error(f"File write error: {e}")
            return f"Error: Could not write file — {type(e).__name__}: {e}"

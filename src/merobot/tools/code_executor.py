"""Sandboxed Python code executor tool.

Runs Python code in a subprocess with timeout and output limits.
Code is written to a temp file in the workspace and executed via subprocess.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

from merobot.config import get_config
from merobot.constants import CODE_EXEC_MAX_OUTPUT, CODE_EXEC_TIMEOUT
from merobot.tools.base import BaseTool


class CodeExecutorTool(BaseTool):
    """Execute Python code in a sandboxed subprocess."""

    @property
    def name(self) -> str:
        return "code_executor"

    @property
    def description(self) -> str:
        return (
            "Execute Python code and return the output (stdout + stderr). "
            f"Code runs in a subprocess with a {CODE_EXEC_TIMEOUT}s timeout. "
            "Use this for calculations, data processing, generating text, "
            "or any task that benefits from running code. "
            "The code has access to standard library modules and installed packages."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute.",
                    "minLength": 1,
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        f"Execution timeout in seconds. Default: {CODE_EXEC_TIMEOUT}."
                    ),
                    "minimum": 1,
                    "maximum": 120,
                },
            },
            "required": ["code"],
        }

    async def execute(self, **kwargs: Any) -> str:
        code: str = kwargs.get("code", "").strip()
        timeout: int = kwargs.get("timeout", CODE_EXEC_TIMEOUT)

        if not code:
            return "Error: 'code' parameter is required."

        timeout = max(1, min(120, timeout))
        workspace = get_config().agent.resolved_workspace
        workspace.mkdir(parents=True, exist_ok=True)

        # Write code to a temp file in the workspace
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                dir=str(workspace),
                delete=False,
                prefix="exec_",
            ) as f:
                f.write(code)
                temp_path = Path(f.name)
        except Exception as e:
            return f"Error: Failed to write code file — {type(e).__name__}: {e}"

        logger.info(f"Executing code: {temp_path}")

        try:
            process = await asyncio.create_subprocess_exec(
                "python3",
                str(temp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace),
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return (
                    f"⏱️ Execution timed out after {timeout}s.\n"
                    "Consider optimizing the code or increasing the timeout."
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # Build result
            parts = []

            if stdout:
                truncated = stdout[:CODE_EXEC_MAX_OUTPUT]
                parts.append(f"**stdout**:\n```\n{truncated}\n```")
                if len(stdout) > CODE_EXEC_MAX_OUTPUT:
                    parts.append(
                        f"*[stdout truncated: {len(stdout):,} chars, "
                        f"showing first {CODE_EXEC_MAX_OUTPUT:,}]*"
                    )

            if stderr:
                truncated = stderr[:CODE_EXEC_MAX_OUTPUT]
                parts.append(f"**stderr**:\n```\n{truncated}\n```")

            parts.append(f"**Return code**: {process.returncode}")

            if not stdout and not stderr:
                parts.insert(0, "Code executed successfully with no output.")

            return "\n\n".join(parts)

        except Exception as e:
            logger.error(f"Code execution error: {e}")
            return f"Error: Code execution failed — {type(e).__name__}: {e}"

        finally:
            # Clean up temp file
            try:
                temp_path.unlink()
            except OSError:
                pass

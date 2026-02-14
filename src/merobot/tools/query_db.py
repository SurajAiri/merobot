"""SQLite query tool for data tabulation and recording.

Provides the agent with a persistent SQLite database for storing and
querying structured data. The DB lives in the workspace directory.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from loguru import logger

from merobot.config import get_config
from merobot.constants import SQLITE_DB_FILENAME
from merobot.tools.base import BaseTool

# Statements that modify data (need commit)
_WRITE_PREFIXES = ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "REPLACE")


class SQLiteQueryTool(BaseTool):
    """Execute SQL queries against a local SQLite database."""

    @property
    def name(self) -> str:
        return "sqlite_query"

    @property
    def description(self) -> str:
        workspace = get_config().agent.resolved_workspace
        db_path = workspace / SQLITE_DB_FILENAME
        return (
            f"Execute SQL queries against a local SQLite database ({db_path}). "
            "Use this to store, query, and manage structured data. "
            "Supports SELECT (returns formatted table), INSERT, UPDATE, DELETE, "
            "CREATE TABLE, DROP TABLE, and ALTER TABLE. "
            "The database is auto-created if it doesn't exist. "
            "Use this for recording information, tracking tasks, storing notes, "
            "or any structured data the user wants to persist."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL query to execute.",
                    "minLength": 1,
                },
                "params": {
                    "type": "array",
                    "description": (
                        "Optional list of parameters for parameterized queries "
                        "(use ? placeholders in the query)."
                    ),
                    "items": {},
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query: str = kwargs.get("query", "").strip()
        params: list = kwargs.get("params", [])

        if not query:
            return "Error: 'query' parameter is required."

        workspace = get_config().agent.resolved_workspace
        workspace.mkdir(parents=True, exist_ok=True)
        db_path = workspace / SQLITE_DB_FILENAME

        logger.info(f"SQLite query: {query[:100]}")

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            is_write = query.strip().upper().startswith(_WRITE_PREFIXES)

            cursor.execute(query, params)

            if is_write:
                conn.commit()
                affected = cursor.rowcount
                result = (
                    f"✅ Query executed successfully.\n"
                    f"**Rows affected**: {affected}"
                )
                if query.strip().upper().startswith("CREATE"):
                    result = "✅ Table created successfully."
                elif query.strip().upper().startswith("DROP"):
                    result = "✅ Table dropped successfully."
            else:
                rows = cursor.fetchall()
                if not rows:
                    result = "Query returned no results."
                else:
                    result = self._format_table(rows)

            cursor.close()
            conn.close()
            return result

        except sqlite3.Error as e:
            logger.error(f"SQLite error: {e}")
            return f"Error: SQLite — {e}"
        except Exception as e:
            logger.error(f"SQLite query error: {e}")
            return f"Error: {type(e).__name__}: {e}"

    @staticmethod
    def _format_table(rows: list[sqlite3.Row]) -> str:
        """Format query results as a markdown table."""
        if not rows:
            return "No results."

        columns = rows[0].keys()
        # Header
        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"

        # Rows
        lines = [header, separator]
        for row in rows[:100]:  # Cap at 100 rows
            values = [str(row[col]) if row[col] is not None else "NULL" for col in columns]
            lines.append("| " + " | ".join(values) + " |")

        result = "\n".join(lines)
        if len(rows) > 100:
            result += f"\n\n*[Showing 100 of {len(rows)} rows]*"

        result = f"**{len(rows)} row(s) returned**:\n\n{result}"
        return result

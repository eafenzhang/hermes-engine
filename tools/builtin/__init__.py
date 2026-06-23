"""Built-in tools package — registers all built-in tools with the executor."""

from __future__ import annotations

from tools.executor import executor
from tools.builtin import read_file, write_file, execute_command


def register_all() -> None:
    """Register all built-in tools with the global executor."""
    executor.register("read_file", read_file.read_file, read_file.SCHEMA)
    executor.register("write_file", write_file.write_file, write_file.SCHEMA)
    executor.register("execute_command", execute_command.execute_command, execute_command.SCHEMA)

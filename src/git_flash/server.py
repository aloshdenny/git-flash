# FILE: src/git_flash/server.py
import subprocess
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

mcp = FastMCP(
    name="Git Command Server",
    instructions="A server that executes git commands in a specified directory.",
)

@mcp.tool(name="run_git_command")
def run_git_command(command: str, working_directory: str) -> dict[str, Any]:
    """
    Executes a git command in the specified working directory.

    Args:
        command: The git command to run (e.g., 'status', 'branch -a', 'commit -m "msg"').
        working_directory: The absolute path of the repository to operate on.

    Returns:
        A dictionary with the command's stdout, stderr, and return code.
    """
    if not command:
        raise ToolError("No command provided.")

    # For security, split the command string and prepend 'git'
    # This ensures only git commands can be run.
    command_parts = ["git"] + command.split()
    
    try:
        process = subprocess.run(
            command_parts,
            capture_output=True,
            text=True,
            cwd=working_directory,
            check=False,  # Don't raise an exception on non-zero exit codes
        )
        return {
            "stdout": process.stdout.strip(),
            "stderr": process.stderr.strip(),
            "return_code": process.returncode,
        }
    except FileNotFoundError:
        raise ToolError("Command 'git' not found. Is git installed and in your PATH?")
    except Exception as e:
        raise ToolError(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    mcp.run()
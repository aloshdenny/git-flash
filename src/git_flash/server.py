# FILE: src/git_flash/server.py
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from typing import List

from fastmcp import FastMCP

# --- Tool Implementations ---

mcp = FastMCP("GitFlash Server")

def _get_safe_path(working_directory: str, target_path_str: str) -> Path:
    """
    Resolves a path ensuring it's safely within the working directory.
    Prevents directory traversal attacks (e.g., '../../').
    """
    work_dir = Path(working_directory).resolve()
    target_path = Path(target_path_str)

    # If the target path is absolute, it's a security risk.
    if target_path.is_absolute():
        raise PermissionError(f"Absolute paths are not allowed: '{target_path_str}'")

    # Resolve the combined path
    safe_path = (work_dir / target_path).resolve()

    # The most important check: ensure the resolved path is a subpath of work_dir
    if work_dir not in safe_path.parents and safe_path != work_dir:
        raise PermissionError(f"Path access denied: '{target_path_str}' is outside the project directory.")

    return safe_path

@mcp.tool(name="run_git_command")
def run_git_command(command: str, working_directory: str) -> dict[str, Any]:
    """Executes a git command in the specified directory."""
    try:
        # Split command string into a list for subprocess
        command_parts = command.split()
        process = subprocess.run(
            ["git"] + command_parts,
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
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "return_code": 1}

@mcp.tool(name="list_files")
def list_files(path: str, working_directory: str) -> str:
    """Lists files and directories in a given path relative to the project root."""
    try:
        safe_path = _get_safe_path(working_directory, path)
        if not safe_path.exists():
            return f"Error: Path does not exist: '{path}'"
        if not safe_path.is_dir():
            return f"Error: Path is not a directory: '{path}'"
        
        files = os.listdir(safe_path)
        return "\n".join(files) if files else "Directory is empty."
    except Exception as e:
        return f"Error listing files at '{path}': {e}"

@mcp.tool(name="read_file")
def read_file(path: str, working_directory: str) -> str:
    """Reads the content of a file at a given path relative to the project root."""
    try:
        safe_path = _get_safe_path(working_directory, path)
        if not safe_path.is_file():
            return f"Error: Path is not a file or does not exist: '{path}'"
        return safe_path.read_text()
    except Exception as e:
        return f"Error reading file '{path}': {e}"

@mcp.tool(name="write_file")
def write_file(path: str, content: str, working_directory: str) -> str:
    """Writes (or overwrites) content to a file at a given path relative to the project root."""
    try:
        safe_path = _get_safe_path(working_directory, path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content)
        return f"Successfully wrote to '{path}'."
    except Exception as e:
        return f"Error writing to file '{path}': {e}"

@mcp.tool(name="move_file")
def move_file(source: str, destination: str, working_directory: str) -> str:
    """Moves or renames a file or directory from a source to a destination, relative to the project root."""
    try:
        safe_source = _get_safe_path(working_directory, source)
        # For destination, we only ensure the *parent* is safe.
        safe_dest_parent = _get_safe_path(working_directory, str(Path(destination).parent))
        safe_destination = safe_dest_parent / Path(destination).name
        
        shutil.move(str(safe_source), str(safe_destination))
        return f"Successfully moved '{source}' to '{destination}'."
    except Exception as e:
        return f"Error moving '{source}' to '{destination}': {e}"

@mcp.tool(name="delete_file")
def delete_file(path: str, working_directory: str) -> str:
    """Deletes a file at a given path relative to the project root."""
    try:
        safe_path = _get_safe_path(working_directory, path)
        if not safe_path.is_file():
            return f"Error: Path is not a file or does not exist: '{path}'"
        safe_path.unlink()
        return f"Successfully deleted file '{path}'."
    except Exception as e:
        return f"Error deleting file '{path}': {e}"

@mcp.tool(name="create_directory")
def create_directory(path: str, working_directory: str) -> str:
    """Creates a new directory (and any parent directories) at a given path relative to the project root."""
    try:
        safe_path = _get_safe_path(working_directory, path)
        safe_path.mkdir(parents=True, exist_ok=True)
        return f"Successfully created directory '{path}'."
    except Exception as e:
        return f"Error creating directory '{path}': {e}"

@mcp.tool(name="delete_directory")
def delete_directory(path: str, working_directory: str) -> str:
    """Deletes a directory and all its contents recursively, at a given path relative to the project root."""
    try:
        safe_path = _get_safe_path(working_directory, path)
        if not safe_path.is_dir():
            return f"Error: Path is not a directory or does not exist: '{path}'"
        shutil.rmtree(safe_path)
        return f"Successfully deleted directory '{path}' and all its contents."
    except Exception as e:
        return f"Error deleting directory '{path}': {e}"
    
@mcp.tool(name="list_directory_tree")
def list_directory_tree(path: str, working_directory: str) -> str:
    """
    Lists all files and directories recursively starting at a given path.
    """
    try:
        safe_path = _get_safe_path(working_directory, path)
        if not safe_path.exists():
            return f"Error: Path does not exist: '{path}'"
        
        tree_output = []
        for root, dirs, files in os.walk(safe_path):
            level = Path(root).relative_to(safe_path).parts
            indent = "    " * len(level)
            tree_output.append(f"{indent}{Path(root).name}/")
            for f in files:
                tree_output.append(f"{indent}    {f}")
        return "\n".join(tree_output)
    except Exception as e:
        return f"Error listing directory tree at '{path}': {e}"

@mcp.tool(name="read_directory_files")
def read_directory_files(path: str, working_directory: str) -> dict:
    """
    Reads the content of all files in a given directory (non-recursive).
    """
    try:
        safe_path = _get_safe_path(working_directory, path)
        if not safe_path.is_dir():
            return {"error": f"Path is not a directory: '{path}'"}
        
        file_contents = {}
        for f in safe_path.iterdir():
            if f.is_file():
                file_contents[str(f.name)] = f.read_text()
        return file_contents or {"info": "No readable files found in directory."}
    except Exception as e:
        return {"error": f"Error reading files in directory '{path}': {e}"}

@mcp.tool(name="get_current_directory")
def get_current_directory() -> str:
    """Returns the current working directory path. This is an alias for 'pwd' or 'ls -d .'."""
    return os.getcwd()
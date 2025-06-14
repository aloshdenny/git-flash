# FILE: src/git_flash/client.py
import asyncio
import os
import subprocess
from pathlib import Path
from typing import Optional, Any

import typer
from google import generativeai as genai
from rich.console import Console
from rich.panel import Panel

from fastmcp import Client
from .server import mcp

cli_app = typer.Typer(
    name="git-flash",
    help="An AI assistant to handle git and file system operations using FastMCP.",
    add_completion=False,
    rich_markup_mode="markdown",
)
console = Console()

# --- API KEY HANDLING (Unchanged) ---
CONFIG_DIR = Path.home() / ".config" / "git-flash"
ENV_FILE = CONFIG_DIR / ".env"

def get_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return api_key
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if ENV_FILE.exists():
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            return api_key
    api_key = typer.prompt("Please enter your Gemini API key", hide_input=True)
    if not api_key:
        console.print("[bold red]Error: No API key provided.[/bold red]")
        raise typer.Exit(code=1)
    if typer.confirm(f"Save this key to [bold cyan]{ENV_FILE}[/bold cyan] for future use?"):
        with open(ENV_FILE, "w") as f:
            f.write(f'GEMINI_API_KEY="{api_key}"\n')
        console.print("[green]✓ API key saved.[/green]")
    return api_key

try:
    gemini_api_key = get_api_key()
    genai.configure(api_key=gemini_api_key)
except Exception as e:
    console.print(f"[bold red]Error initializing Gemini client: {e}[/bold red]")
    raise typer.Exit(code=1)

# --- CORE ASYNC LOGIC ---

async def _run_generative_git_flow(instruction: str, dry_run: bool):
    """Handles the agentic, multi-turn conversation with Gemini."""
    console.print(Panel(f"▶️  [bold]User Goal:[/bold] {instruction}", border_style="cyan", expand=False))

    # All available tools for the Gemini model
    available_tools = genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="run_git_command",
                description="Executes a git command. Do not include 'git' in the command string.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={"command": genai.protos.Schema(type=genai.protos.Type.STRING)},
                    required=["command"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="list_files",
                description="Lists files and directories in a specified path. Use '.' for the current directory.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={"path": genai.protos.Schema(type=genai.protos.Type.STRING)},
                    required=["path"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="read_file",
                description="Reads and returns the content of a specified file.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={"path": genai.protos.Schema(type=genai.protos.Type.STRING)},
                    required=["path"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="write_file",
                description="Writes or overwrites content to a specified file. Creates the file if it does not exist.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "path": genai.protos.Schema(type=genai.protos.Type.STRING),
                        "content": genai.protos.Schema(type=genai.protos.Type.STRING),
                    },
                    required=["path", "content"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="move_file",
                description="Moves or renames a file or directory.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "source": genai.protos.Schema(type=genai.protos.Type.STRING),
                        "destination": genai.protos.Schema(type=genai.protos.Type.STRING),
                    },
                    required=["source", "destination"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="delete_file",
                description="Deletes a specified file.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={"path": genai.protos.Schema(type=genai.protos.Type.STRING)},
                    required=["path"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="create_directory",
                description="Creates a new directory, including any necessary parent directories.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={"path": genai.protos.Schema(type=genai.protos.Type.STRING)},
                    required=["path"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="delete_directory",
                description="Deletes a directory and all of its contents recursively.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={"path": genai.protos.Schema(type=genai.protos.Type.STRING)},
                    required=["path"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="list_directory_tree",
                description="Recursively lists the directory tree structure starting at a given path.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={"path": genai.protos.Schema(type=genai.protos.Type.STRING)},
                    required=["path"],  
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="read_directory_files",
                description="Reads the contents of all files in the given directory (non-recursive).",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={"path": genai.protos.Schema(type=genai.protos.Type.STRING)},
                    required=["path"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="get_current_directory",
                description="Returns the current working directory path.",
                parameters=genai.protos.Schema(type=genai.protos.Type.OBJECT, properties={}),
            ),
        ]
    )

    model = genai.GenerativeModel(model_name="gemini-2.5-flash-preview-05-20", tools=[available_tools])
    chat = model.start_chat()
    # Provide the initial project context
    initial_prompt = (
        f"You are Git Flash, an AI assistant for git and file system operations. "
        f"You are operating in the directory: {os.getcwd()}. "
        f"The user's goal is: {instruction}"
    )
    response = await chat.send_message_async(initial_prompt)

    # In-memory client to our local server
    mcp_client = Client(mcp)
    async with mcp_client as client:
        while response.candidates[0].content.parts and response.candidates[0].content.parts[0].function_call:
            function_call = response.candidates[0].content.parts[0].function_call
            tool_name = function_call.name
            tool_args = {key: value for key, value in function_call.args.items()}

            command_display = f"{tool_name}({', '.join(f'{k}={v!r}' for k, v in tool_args.items())})"
            console.print(f"🤖  [bold yellow]Agent wants to run:[/bold yellow] `{command_display}`")
            
            if dry_run:
                console.print("[bold magenta]-- DRY RUN: SKIPPING COMMAND --[/bold magenta]")
                tool_output: Any = {"status": "Dry run mode, command not executed."}
            else:
                # Add working directory to all tool calls for context and security
                tool_args["working_directory"] = os.getcwd()
                tool_result = await client.call_tool(tool_name, tool_args)
                tool_output = tool_result[0].text if tool_result else "Tool returned no output."
            
            console.print(Panel(f"[bold]Result:[/bold]\n{tool_output}", border_style="dim", expand=False))

            response = await chat.send_message_async(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=tool_name,
                        response={"result": tool_output},
                    )
                )
            )
    
    console.print(Panel(f"✅  [bold]Final Response:[/bold]\n{response.text}", border_style="green", expand=False))


async def _run_auto_commit(dry_run: bool):
    """Handles the original auto-commit message flow."""
    cwd = os.getcwd()
    console.print("[bold cyan]Staging all changes and generating commit message...[/bold cyan]")
    
    subprocess.run(["git", "add", "."], cwd=cwd, check=True)
    
    diff_process = subprocess.run(
        ["git", "diff", "--staged"], capture_output=True, text=True, cwd=cwd
    )
    if not diff_process.stdout:
        console.print("No staged changes to commit.")
        return

    prompt = f"Based on the following git diff, generate a concise and descriptive commit message following the Conventional Commits specification:\n\n{diff_process.stdout}. Don't use any inline code formatting. Do not ask any further questions. Just provide the commit message."
    
    model = genai.GenerativeModel(model_name="gemini-2.5-flash-preview-05-20")
    response = await model.generate_content_async(prompt)
    commit_message = response.text.strip()
    # Remove surrounding triple backticks if they exist
    if commit_message.startswith("```") and commit_message.endswith("```"):
        commit_message = commit_message.strip("`").strip()

    
    await _run_manual_commit(commit_message, dry_run)


async def _run_manual_commit(commit_message: str, dry_run: bool):
    """Handles committing with a user-provided message."""
    cwd = os.getcwd()
    console.print(Panel(f"[bold]Commit Message:[/bold]\n{commit_message}", border_style="green", expand=False))
    
    if dry_run:
        console.print("[bold magenta]-- DRY RUN: Staging changes but not committing or pushing. --[/bold magenta]")
        subprocess.run(["git", "add", "."], cwd=cwd, check=True)
        return

    try:
        subprocess.run(["git", "add", "."], cwd=cwd, check=True)
        subprocess.run(["git", "commit", "-m", commit_message], cwd=cwd, check=True)
        console.print("[green]✓ Commit successful.[/green]")
        
        current_branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, cwd=cwd).stdout.strip()
        console.print(f"Pushing to origin/{current_branch}...")
        subprocess.run(["git", "push", "origin", current_branch], cwd=cwd, check=True, capture_output=True)
        console.print("[green]✓ Push successful.[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error during git operation:[/bold red]\n{e.stderr}")


@cli_app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    instruction: Optional[str] = typer.Argument(None, help="The natural language instruction for the git agent."),
    commit_message: Optional[str] = typer.Option(
        None, "--message", "-m", help="A specific commit message to use."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Perform a dry run."),
):
    """
    An AI assistant for git and file system operations.

    - Provide an instruction in natural language: `git-flash "create a new branch called hotfix and switch to it"`
    - Manipulate files: `git-flash "read the README.md file and summarize its contents"`
    - Provide a specific commit message: `git-flash -m "fix: resolve issue #123"`
    - Run with no arguments for an auto-generated commit message.
    - Does not ask for confirmation before executing commands or any further questions.
    - Use `--dry-run` to simulate actions without making changes.
    """
    if ctx.invoked_subcommand is not None:
        return

    if instruction:
        asyncio.run(_run_generative_git_flow(instruction, dry_run))
    elif commit_message:
        asyncio.run(_run_manual_commit(commit_message, dry_run))
    else:
        asyncio.run(_run_auto_commit(dry_run))

if __name__ == "__main__":
    cli_app()
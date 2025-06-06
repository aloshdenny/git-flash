# FILE: src/git_flash/client.py
import asyncio
import os
import subprocess
from pathlib import Path
from typing import Optional

import typer
from google import generativeai as genai
from rich.console import Console
from rich.panel import Panel

from fastmcp import Client
from .server import mcp

cli_app = typer.Typer(
    name="git-flash",
    help="An AI assistant to handle git commits using FastMCP.",
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

    # The `run_git_command` tool definition for Gemini
    git_tool = genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="run_git_command",
                description="Executes a git command in the current project directory.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "command": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="The git command arguments to run (e.g., 'status', 'branch new-feature'). Do not include 'git'.",
                        ),
                    },
                    required=["command"],
                ),
            )
        ]
    )

    model = genai.GenerativeModel(model_name="gemini-1.5-flash", tools=[git_tool])
    chat = model.start_chat()
    response = await chat.send_message_async(instruction)

    # In-memory client to our local server
    mcp_client = Client(mcp)
    async with mcp_client as client:
        while response.candidates[0].content.parts and response.candidates[0].content.parts[0].function_call:
            function_call = response.candidates[0].content.parts[0].function_call
            command = function_call.args["command"]
            console.print(f"🤖  [bold yellow]Agent wants to run:[/bold yellow] `git {command}`")
            
            if dry_run:
                console.print("[bold magenta]-- DRY RUN: SKIPPING COMMAND --[/bold magenta]")
                tool_output = {"stdout": "Dry run mode, command not executed.", "stderr": "", "return_code": 0}
            else:
                tool_output = await client.call_tool(
                    "run_git_command",
                    {"command": command, "working_directory": os.getcwd()},
                )
                tool_output = tool_output[0].text  # The tool returns a JSON string
            
            console.print(Panel(f"[bold]Result:[/bold]\n{tool_output}", border_style="dim", expand=False))
            response = await chat.send_message_async(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name="run_git_command",
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

    prompt = f"Based on the following git diff, generate a concise and descriptive commit message following the Conventional Commits specification:\n\n{diff_process.stdout}"
    
    model = genai.GenerativeModel(model_name="gemini-1.5-flash")
    response = await model.generate_content_async(prompt)
    commit_message = response.text.strip()
    
    console.print(Panel(f"[bold]Generated Commit Message:[/bold]\n{commit_message}", border_style="green", expand=False))
    
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
    An AI assistant for git operations.

    - Provide an instruction in natural language: `git flash "create a new branch called hotfix and switch to it"`
    - Provide a specific commit message: `git flash -m "fix: resolve issue #123"`
    - Run with no arguments for an auto-generated commit message.
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
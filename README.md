# Git MCP Assistant

This tool uses FastMCP and the Google Gemini API to provide an AI-powered git assistant. It can function as an agent to execute a series of git commands based on natural language, or it can be used to simply generate a commit message for your staged changes.

## Setup

1.  **Set Your API Key**: This tool requires a Gemini API key. The first time you run it, it will prompt you to enter your key and offer to save it to `~/.config/git-flash/.env`. Alternatively, you can set it as an environment variable:
    ```bash
    export GEMINI_API_KEY="your-gemini-api-key"
    ```

2.  **Install the Package**: Navigate to the `git-flash` directory and install it using `pip`. Using the `-e` flag (editable mode) is recommended for development.
    ```bash
    pip install -e .
    ```
    This command installs the `git-flash` command into your system's PATH.

## Usage

You can run the assistant from within **any git repository directory**.

### Mode 1: Agentic Flow (Natural Language)

Provide an instruction in plain English, and the agent will determine the necessary git commands and execute them one by one.

**Examples:**
```bash
# Create a new branch and switch to it
git flash "create a new feature branch called 'login-flow' and check it out"

# Stash changes, switch branches, and pop the stash
git flash "stash my current work, switch to the 'main' branch, and then apply my stash"

# List all branches, local and remote
git flash "show me all the branches"
```

### Mode 2: Manual Commit Message

If you know what you want to commit, use the -m or --message option. This will stage all current changes and commit with your message.

```bash
git mcp -m "feat: add user authentication endpoint"
```

### Dry Run

For any of the modes, you can add the --dry-run flag to see what commands the agent would run without actually executing them. This is great for safety and testing.

```bash
git mcp "create a hotfix branch and merge it into main" --dry-run
```
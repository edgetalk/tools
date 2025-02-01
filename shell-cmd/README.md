# Shell Command Tool

A tool for executing shell commands through a persistent shell server.

## Tool Description

The shell-cmd tool provides a robust interface to:
- Execute shell commands in a persistent session
- Maintain state between command executions
- Handle environment variables and working directory persistence
- Support for background processes and long-running commands

## How It Works

The tool uses a persistent shell server to:
1. Take shell commands as input
2. Execute commands in a maintained shell session
3. Preserve environment state between calls
4. Support for:
   - Background processes
   - Environment variables
   - Working directory persistence
   - Command output capture

Note: 
- Commands requiring user input (like sudo password prompts) are not supported
- Long-running commands should be executed in the background
- Large output may be truncated for performance
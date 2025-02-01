# Infrastructure Setup

This directory contains infrastructure and setup files required to run various Edge Talk tools in a sandboxed environment.

## Contents

### Docker Setup (`docker/`)
- `Dockerfile` - Container definition for running tools in a sandboxed environment
- `shell_server.py` - Python-based shell server that enables persistent shell sessions

## Usage

These infrastructure components are particularly important for:
- `shell-cmd` tool - Requires the shell server for persistent shell sessions
- `text-editor` tool - Benefits from sandboxed environment for file operations
- `github-tools` - Can be sandboxed for safe GitHub operations

### Setting Up the Docker Environment

1. Build the container:
```bash
cd infrastructure/docker
docker build -t edgetalk-tools .
```

2. Run the container:
```bash
docker run -d \
  --name edgetalk-tools \
  -v /path/to/your/workspace:/workspace \
  edgetalk-tools
```

### Shell Server

The shell server (`shell_server.py`) provides:
- Persistent shell sessions
- Environment variable maintenance
- Working directory persistence
- Safe command execution
- Output capture and formatting

## Security Notes

- All tool operations are sandboxed within the Docker container
- File system access is limited to mounted volumes
- Network access can be restricted through Docker networking
- Environment variables are isolated to the container
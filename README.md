# edge talk Tools

A collection of tools and utilities for edge talk, providing various integrations and functionalities to enhance your development workflow.

## Available Tools

### Development Tools
- [GitHub Tools](github-tools/README.md) - Comprehensive GitHub API integration for repository, PR, and issue management
- [Shell Command Tool](shell-cmd/README.md) - Execute shell commands in a persistent session
- [Text Editor Tool](text-editor/README.md) - View, create, and edit files with state management

### Email & Communication
- [Email Search Tool](search-emails/README.md) - Search and retrieve Gmail messages using Google's Gmail API

### Travel & Transportation
- [Flight Information Tool](flight-info/README.md) - Real-time flight status and details using flight numbers via Aviation Stack API
- [Flight Search Tool](find-flights/README.md) - Real-time flight information search between airports using Aviation Stack API

### Media & Content
- [YouTube Captions Tool](youtube-captions/README.md) - Retrieve video information and captions from YouTube videos

## Infrastructure

The [infrastructure](infrastructure/README.md) directory contains setup files for running tools in a sandboxed environment:
- Docker container definition
- Shell server for persistent sessions
- Security and isolation features

## Requirements

Different tools may require specific API keys or authentication:
- GitHub token for GitHub operations
- Gmail API access for email search
- Aviation Stack API key for flight information
- YouTube API access for video captions

Docker is required for running tools in a sandboxed environment. See the [infrastructure setup guide](infrastructure/README.md) for details.

## Contributing

Feel free to contribute new tools or improvements to existing ones. Make sure to:
1. Follow the existing directory structure
2. Include comprehensive documentation
3. Add tool entry to this README
4. Test thoroughly before submitting
5. Use the provided Docker environment for testing
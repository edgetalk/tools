# GitHub Tools

A comprehensive set of tools for interacting with GitHub's API to manage repositories, pull requests, and issues.

## Tool Description

The github-tools provides a powerful interface to:
- Create and manage pull requests
- List, create and update repository issues
- Retrieve repository metadata and information
- Handle repository permissions and access control

## How It Works

The tool uses the GitHub API to:
1. Authenticate using provided tokens
2. Support multiple operations:
   - Pull Request Management:
     * Create new PRs
     * Specify source and target branches
     * Add detailed descriptions
   - Issue Management:
     * List repository issues
     * Create new issues
     * Update existing issues
     * Add labels and assignees
   - Repository Information:
     * Get repository details
     * Access metadata
     * Check repository status

Note: Requires GitHub token with appropriate permissions:
- repo scope for private repositories
- public_repo scope for public repositories
- issues scope for issue management
- pull_requests scope for PR operations
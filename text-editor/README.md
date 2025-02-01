# Text Editor Tool

A custom tool for viewing, creating, and editing files with persistent state management.

## Tool Description

The text-editor tool provides a comprehensive interface to:
- View file and directory contents
- Create new files with specified content
- Edit existing files with precise control
- Maintain editing state across sessions
- Support for undo operations

## How It Works

The tool provides several commands:
1. `view`: Display file contents or directory structure
   - Shows line numbers for files
   - Lists non-hidden files up to 2 levels deep for directories
   - Supports viewing specific line ranges

2. `create`: Create new files
   - Prevents overwriting existing files
   - Takes full file content as input

3. `str_replace`: Replace content in existing files
   - Exact string matching for replacements
   - Requires unique context for replacement
   - Optional new content specification

4. `insert`: Insert content at specific locations
   - Line number-based insertion
   - Adds content after specified line

5. `undo_edit`: Revert recent changes
   - Maintains history of changes
   - Supports single-step undo

Note: 
- Long outputs are automatically truncated
- State is maintained between commands
- Careful attention to whitespace is required for replacements
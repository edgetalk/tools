#!/usr/bin/env python3
"""
Cross-platform Shell Server with Repository Mapping

TREE-SITTER INSTALLATION INSTRUCTIONS:
=======================================

The repo-map functionality requires tree-sitter and language parsers.
Install the following packages for full language support:

# Core tree-sitter (required)
pip install tree-sitter==0.24.0

# Language parsers (install the ones you need)
pip install tree-sitter-python==0.23.6      # Python support
pip install tree-sitter-javascript==0.23.1  # JavaScript support  
pip install tree-sitter-typescript==0.23.2  # TypeScript support
pip install tree-sitter-cpp==0.23.4         # C++ support
pip install tree-sitter-java==0.23.5        # Java support
pip install tree-sitter-go==0.23.4          # Go support

# For Rust and C, use compatible versions:
pip install tree-sitter-rust==0.21.2        # Rust support (compatible version)
pip install tree-sitter-c==0.21.3           # C support (compatible version)

# Install all at once:
pip install tree-sitter==0.24.0 tree-sitter-python==0.23.6 tree-sitter-javascript==0.23.1 tree-sitter-typescript==0.23.2 tree-sitter-cpp==0.23.4 tree-sitter-java==0.23.5 tree-sitter-go==0.23.4 tree-sitter-rust==0.21.2 tree-sitter-c==0.21.3

NOTES:
- tree-sitter is optional - the server works without it
- repo-map command will show helpful error if tree-sitter is missing
- Rust and C parsers use older versions due to language version compatibility
- If you get version conflicts, create a separate conda environment

CONDA ENVIRONMENT (RECOMMENDED):
conda create -n tree-sitter python=3.12
conda activate tree-sitter
# Then install packages as above
"""

import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import select
import json
import signal
import sys
import time
import re
import subprocess
import threading
import platform
import shlex
from io import StringIO
from pathlib import Path

# Optional tree-sitter imports - gracefully handle if not available
try:
    import tree_sitter
    from tree_sitter import Language, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    print("[Info] tree-sitter not available - repo-map command will be disabled")

# Tree-sitter language mappings and queries
LANGUAGE_EXTENSIONS = {
    'python': ['.py', '.pyx', '.pyi'],
    'javascript': ['.js', '.jsx', '.mjs'],
    'typescript': ['.ts', '.tsx'],
    'rust': ['.rs'],
    'cpp': ['.cpp', '.cc', '.cxx', '.c++', '.hpp', '.hh', '.hxx', '.h++', ".h"],
    'c': ['.c'],
    'java': ['.java'],
    'go': ['.go'],
    'c_sharp': ['.cs'],
    'ruby': ['.rb'],
    'php': ['.php'],
    'swift': ['.swift'],
    'kotlin': ['.kt', '.kts'],
    'scala': ['.scala'],
    'bash': ['.sh', '.bash'],
}

# Tree-sitter queries for extracting function/class signatures
TREE_SITTER_QUERIES = {
    'python': """
        (class_definition
          name: (identifier) @class_name) @class_def
        
        (function_definition
          name: (identifier) @function_name
          parameters: (parameters) @params) @function_def
    """,
    'javascript': """
        (class_declaration
          name: (identifier) @class_name
          superclass: (class_heritage)? @superclass) @class_def
        
        (function_declaration
          name: (identifier) @function_name
          parameters: (formal_parameters) @params) @function_def
        
        (method_definition
          name: (property_name) @method_name
          parameters: (formal_parameters) @params) @method_def
        
        (arrow_function
          parameters: (formal_parameters) @params) @arrow_function
    """,
    'typescript': """
        (class_declaration
          name: (type_identifier) @class_name
          heritage_clause: (heritage_clause)? @heritage) @class_def
        
        (function_declaration
          name: (identifier) @function_name
          parameters: (formal_parameters) @params
          return_type: (type_annotation)? @return_type) @function_def
        
        (method_definition
          name: (property_name) @method_name
          parameters: (formal_parameters) @params
          return_type: (type_annotation)? @return_type) @method_def
        
        (interface_declaration
          name: (type_identifier) @interface_name) @interface_def
    """,
    'rust': """
        (struct_item
          name: (type_identifier) @struct_name) @struct_def
        
        (enum_item
          name: (type_identifier) @enum_name) @enum_def
        
        (function_item
          name: (identifier) @function_name
          parameters: (parameters) @params) @function_def
        
        (impl_item
          type: (type_identifier) @impl_type) @impl_def
        
        (trait_item
          name: (type_identifier) @trait_name) @trait_def
    """,
    'cpp': """
        (class_specifier
          name: (type_identifier) @class_name) @class_def
        
        (struct_specifier
          name: (type_identifier) @struct_name) @struct_def
        
        (function_definition) @function_def
        
        (function_declarator
          declarator: (identifier) @function_name) @function_decl
    """,
    'c': """
        (struct_specifier
          name: (type_identifier) @struct_name) @struct_def
        
        (function_definition
          declarator: (function_declarator
            declarator: (identifier) @function_name
            parameters: (parameter_list) @params)) @function_def
        
        (declaration
          declarator: (function_declarator
            declarator: (identifier) @function_name
            parameters: (parameter_list) @params)) @function_decl
    """,
    'java': """
        (class_declaration
          name: (identifier) @class_name
          superclass: (superclass)? @superclass
          interfaces: (super_interfaces)? @interfaces) @class_def
        
        (interface_declaration
          name: (identifier) @interface_name) @interface_def
        
        (method_declaration
          name: (identifier) @method_name
          parameters: (formal_parameters) @params
          type: (type_identifier)? @return_type) @method_def
        
        (constructor_declaration
          name: (identifier) @constructor_name
          parameters: (formal_parameters) @params) @constructor_def
    """,
    'go': """
        (type_declaration
          (type_spec
            name: (type_identifier) @type_name
            type: (struct_type))) @struct_def
        
        (type_declaration
          (type_spec
            name: (type_identifier) @type_name
            type: (interface_type))) @interface_def
        
        (function_declaration
          name: (identifier) @function_name
          parameters: (parameter_list) @params
          result: (parameter_list)? @return_type) @function_def
        
        (method_declaration
          receiver: (parameter_list) @receiver
          name: (identifier) @method_name
          parameters: (parameter_list) @params
          result: (parameter_list)? @return_type) @method_def
    """,
}


class RepoMapper:
    """Handles repository mapping using git and tree-sitter"""
    
    def __init__(self, repo_path=None):
        self.repo_path = repo_path or os.getcwd()
        self.languages = {}
        self.parsers = {}
        self._load_available_languages()
    
    def _load_available_languages(self):
        """Load available tree-sitter languages"""
        if not TREE_SITTER_AVAILABLE:
            return
            
        # Try to load common tree-sitter language libraries
        language_names = ['python', 'javascript', 'typescript', 'rust', 'cpp', 'c', 'java', 'go']
        
        for lang_name in language_names:
            try:
                # Try different possible module names
                possible_names = [
                    f'tree_sitter_{lang_name}',
                    f'tree-sitter-{lang_name}',
                    lang_name
                ]
                
                for module_name in possible_names:
                    try:
                        module = __import__(module_name)
                        if hasattr(module, 'language'):
                            language_func = module.language()
                            language = Language(language_func)
                            self.languages[lang_name] = language
                            parser = Parser()
                            parser.language = language
                            self.parsers[lang_name] = parser
                            print(f"[Debug] Loaded tree-sitter language: {lang_name}")
                            break
                    except ImportError:
                        continue
                        
            except Exception as e:
                print(f"[Debug] Could not load tree-sitter language {lang_name}: {e}")
                continue
    
    def _get_language_for_file(self, file_path):
        """Determine the programming language for a file based on extension"""
        ext = Path(file_path).suffix.lower()
        
        for lang, extensions in LANGUAGE_EXTENSIONS.items():
            if ext in extensions:
                return lang
        return None
    
    def _get_git_files(self):
        """Get list of files tracked by git in the current directory and subdirectories"""
        try:
            # First, get the git repository root
            repo_root_result = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if repo_root_result.returncode != 0:
                print(f"[Warning] Failed to get git repo root: {repo_root_result.stderr}")
                return []
            
            repo_root = repo_root_result.stdout.strip()
            
            # Calculate relative path from repo root to current directory
            rel_path = os.path.relpath(self.repo_path, repo_root)
            
            # If we're at the repo root, use all files; otherwise limit to current subfolder
            if rel_path == '.':
                # At repo root, get all files
                git_cmd = ['git', 'ls-files']
            else:
                # In a subfolder, only get files in this subfolder and below
                git_cmd = ['git', 'ls-files', rel_path]
            
            result = subprocess.run(
                git_cmd,
                cwd=repo_root,  # Run from repo root for consistent paths
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
                # Convert relative paths to absolute paths
                return [os.path.join(repo_root, f) for f in files]
            else:
                print(f"[Warning] Git ls-files failed: {result.stderr}")
                return []
                
        except Exception as e:
            print(f"[Warning] Failed to get git files: {e}")
            return []
    
    def _parse_file_signatures(self, file_path, language):
        """Parse a file and extract function/class signatures"""
        if language not in self.parsers or language not in TREE_SITTER_QUERIES:
            return []
        
        try:
            with open(file_path, 'rb') as f:
                source_code = f.read()
            
            parser = self.parsers[language]
            tree = parser.parse(source_code)
            
            query = self.languages[language].query(TREE_SITTER_QUERIES[language])
            captures = query.captures(tree.root_node)
            
            signatures = []
            
            # captures is a dict where keys are capture names and values are lists of nodes
            for capture_name, nodes in captures.items():
                for node in nodes:
                    node_text = source_code[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')
                    
                    if capture_name.endswith('_def'):
                        # This is a complete definition, extract the signature
                        if capture_name == 'class_def':
                            signatures.append({
                                'type': 'class',
                                'name': self._extract_name_from_node(node, source_code, 'class'),
                                'line': node.start_point[0] + 1,
                                'signature': self._extract_signature(node, source_code, 'class')
                            })
                        elif capture_name in ['function_def', 'method_def', 'async_function_def']:
                            signatures.append({
                                'type': 'function',
                                'name': self._extract_name_from_node(node, source_code, 'function'),
                                'line': node.start_point[0] + 1,
                                'signature': self._extract_signature(node, source_code, 'function')
                            })
                        elif capture_name in ['struct_def', 'enum_def', 'trait_def', 'interface_def']:
                            signatures.append({
                                'type': capture_name.replace('_def', ''),
                                'name': self._extract_name_from_node(node, source_code, 'type'),
                                'line': node.start_point[0] + 1,
                                'signature': self._extract_signature(node, source_code, 'type')
                            })
                    elif capture_name == 'function_decl':
                        # Handle C++ function declarations
                        signatures.append({
                            'type': 'function',
                            'name': self._extract_name_from_node(node, source_code, 'function'),
                            'line': node.start_point[0] + 1,
                            'signature': self._extract_signature(node, source_code, 'function')
                        })
            
            return signatures
            
        except Exception as e:
            print(f"[Warning] Failed to parse {file_path}: {e}")
            return []
    
    def _extract_name_from_node(self, node, source_code, node_type):
        """Extract the name from a definition node"""
        try:
            # Look for identifier nodes within the definition
            for child in node.children:
                if child.type == 'identifier' or child.type == 'type_identifier':
                    return source_code[child.start_byte:child.end_byte].decode('utf-8', errors='ignore')
                # Recursively search in child nodes
                for grandchild in child.children:
                    if grandchild.type == 'identifier' or grandchild.type == 'type_identifier':
                        return source_code[grandchild.start_byte:grandchild.end_byte].decode('utf-8', errors='ignore')
            return "unknown"
        except:
            return "unknown"
    
    def _extract_signature(self, node, source_code, node_type):
        """Extract a clean signature from a definition node"""
        try:
            # Get the first line of the definition
            lines = source_code[node.start_byte:node.end_byte].decode('utf-8', errors='ignore').split('\n')
            first_line = lines[0].strip()
            
            # For multi-line signatures, try to get the complete signature
            if node_type == 'function' and not first_line.endswith(':') and not first_line.endswith('{') and not first_line.endswith(';'):
                # Look for more lines that might be part of the signature
                for i, line in enumerate(lines[1:], 1):
                    first_line += ' ' + line.strip()
                    if line.strip().endswith(':') or line.strip().endswith('{') or line.strip().endswith(';'):
                        break
                    if i > 3:  # Don't go too far
                        break
            
            # Clean up the signature
            first_line = re.sub(r'\s+', ' ', first_line)  # Normalize whitespace
            return first_line
            
        except:
            return "unknown signature"
    
    def generate_repo_map(self):
        """Generate a repository map with function and class signatures"""
        if not TREE_SITTER_AVAILABLE:
            return "Error: tree-sitter not available. Install tree-sitter and language parsers to use repo-map."
        
        if not self.languages:
            return "Error: No tree-sitter language parsers found. Install tree-sitter language libraries (e.g., tree-sitter-python, tree-sitter-rust, etc.)"
        
        git_files = self._get_git_files()
        if not git_files:
            return "Error: No git repository found or no tracked files."
        
        repo_map = {}
        supported_files = 0
        
        for file_path in git_files:
            if not os.path.exists(file_path):
                continue
                
            language = self._get_language_for_file(file_path)
            if language and language in self.parsers:
                supported_files += 1
                signatures = self._parse_file_signatures(file_path, language)
                if signatures:
                    rel_path = os.path.relpath(file_path, self.repo_path)
                    repo_map[rel_path] = {
                        'language': language,
                        'signatures': signatures
                    }
        
        # Format the output
        if not repo_map:
            return f"No parseable files found. Checked {len(git_files)} git-tracked files, {supported_files} had supported extensions."
        
        # Get relative path info for the header
        try:
            repo_root_result = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            if repo_root_result.returncode == 0:
                repo_root = repo_root_result.stdout.strip()
                rel_path = os.path.relpath(self.repo_path, repo_root)
                scope_info = f" in ./{rel_path}" if rel_path != '.' else " (entire repository)"
            else:
                scope_info = ""
        except:
            scope_info = ""
        
        output_lines = []
        output_lines.append(f"Repository Map{scope_info} ({len(repo_map)} files with {sum(len(data['signatures']) for data in repo_map.values())} signatures)")
        output_lines.append("=" * 80)
        
        for file_path, data in sorted(repo_map.items()):
            output_lines.append(f"\n📁 {file_path} ({data['language']})")
            output_lines.append("-" * 40)
            
            # Group signatures by type
            classes = [s for s in data['signatures'] if s['type'] == 'class']
            functions = [s for s in data['signatures'] if s['type'] == 'function']
            others = [s for s in data['signatures'] if s['type'] not in ['class', 'function']]
            
            for sig_group, icon in [(classes, '🏛️'), (functions, '⚡'), (others, '🔧')]:
                for sig in sorted(sig_group, key=lambda x: x['line']):
                    output_lines.append(f"  {icon} L{sig['line']:4d}: {sig['signature']}")
        
        return '\n'.join(output_lines)

# ANSI Color Codes
COLOR_RED = '\033[91m'
COLOR_RESET = '\033[0m'

# Add a regex pattern to detect shell prompts
PROMPT_PATTERN = re.compile(r'[^>\n]*[$#>]\s*$')
# Add Windows-specific prompt pattern that better matches cmd.exe prompts like "C:\path>"
WINDOWS_PROMPT_PATTERN = re.compile(r'[A-Za-z]:\\.*>(\s*)$')

# Determine the operating system
IS_WINDOWS = platform.system() == 'Windows'

# Import platform-specific modules
if not IS_WINDOWS:
    # Unix-specific imports
    import pty
    import fcntl
    import termios
    import struct
    import tty

    def read_single_keypress():
        """Read a single keypress from stdin in a Unix-compatible way"""
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch
else:
    # Windows-specific imports
    import msvcrt
    
    def read_single_keypress():
        """Read a single keypress from stdin in a Windows-compatible way"""
        return msvcrt.getch().decode('utf-8', errors='replace')


class BaseShell:
    """Base class for shell implementations with common functionality"""
    def __init__(self, secure_mode=False):
        self.secure_mode = secure_mode
        self.cwd = os.getcwd()  # Track initial working directory
        self.last_used = time.time()  # Track when the shell was last used
        self.pending_interactive_context = None  # Clear any pending state on initialization

    def execute(self, cmd):
        """Execute a command in the shell - to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement execute()")

    def cleanup(self):
        """Clean up resources - to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement cleanup()")

    def _strip_control_sequences(self, text):
        """Strip common terminal control sequences from the output"""
        # Pattern to match common terminal control sequences
        # This includes color codes, cursor movement, and other control characters
        control_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][0-9;]*[a-zA-Z]|\r|\x1b\(B')
        # Remove the control sequences
        return control_pattern.sub('', text)

    def _is_prompt(self, text):
        """Check if the text ends with a shell prompt"""
        if IS_WINDOWS:
            return bool(WINDOWS_PROMPT_PATTERN.search(text.rstrip())) or bool(PROMPT_PATTERN.search(text.rstrip()))
        else:
            return bool(PROMPT_PATTERN.search(text.rstrip()))


class UnixShell(BaseShell):
    """Unix-specific shell implementation using PTY"""
    def __init__(self, secure_mode=False):
        super().__init__(secure_mode)
        self.master_fd = None
        self.pid = None
        self.marker_prefix = "UNIX_MARKER_"  # Prefix for command completion markers
        
        try:
            self.master_fd, slave_fd = pty.openpty()
        except OSError as e:
            print(f"[Error] Failed to create PTY: {str(e)}")
            if "administratively prohibited" in str(e):
                print(
                    "[Error] System denied PTY creation. This may be due to security policies or resource limits."
                )
            raise

        try:
            # Set non-blocking mode on master fd
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, os.O_NONBLOCK)
            self.pid = os.fork()
            if self.pid == 0:  # Child
                try:
                    os.close(self.master_fd)
                    os.setsid()
                    os.dup2(slave_fd, 0)
                    os.dup2(slave_fd, 1)
                    os.dup2(slave_fd, 2)
                    term_size = struct.pack("HHHH", 24, 80, 0, 0)
                    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, term_size)
                    # Start with parent process environment
                    env = os.environ.copy()
                    # Override specific environment variables for non-interactive behavior
                    env.update({
                        "TERM": "xterm",
                        "PS1": "$ ",  # Prevent paging in various tools
                        "PAGER": "cat",
                        "GIT_PAGER": "cat",
                        "LESS": "-FRX",
                        "MORE": "-FX",
                        # Disable interactive prompting in common utilities
                        "GIT_CONFIG_PARAMETERS": "'core.pager=cat' 'color.ui=never'",
                        # No fancy prompts
                        "PROMPT_COMMAND": "",
                    })
                    os.execvpe("/bin/bash", ["/bin/bash", "--login"], env)
                except Exception as e:
                    print(f"[Error] Child process setup failed: {str(e)}")
                    os._exit(1)
            os.close(slave_fd)
            # Set up non-interactive terminal
            self._setup_non_interactive_terminal()
            self._read_output(timeout=1.0)
        except Exception as e:
            print(f"[Error] Shell initialization failed: {str(e)}")
            self.cleanup()
            raise

    def _setup_non_interactive_terminal(self):
        """Configure the terminal to be non-interactive"""
        try:
            # Disable terminal paging
            cmds = [
                "stty -icanon -echo",
                "export PAGER=cat",
                "export GIT_PAGER=cat",
                "export LESS='-FRX'",
                "export MORE='-FX'",
                "export GIT_CONFIG_PARAMETERS=\"'core.pager=cat' 'color.ui=never'\"",
                "alias more=cat",
                "alias less=cat",
                "alias git='git -c core.pager=cat -c color.ui=never'",
            ]
            for cmd in cmds:
                os.write(self.master_fd, (cmd + "\n").encode())
            self._read_output(timeout=0.1)  # Clear output
        except Exception as e:
            print(f"[Warning] Failed to set up non-interactive terminal: {str(e)}")

    def _read_output(self, timeout=0.1):
        output = []
        try:
            while True:
                r, _, _ = select.select([self.master_fd], [], [], timeout)
                if not r:
                    break
                data = os.read(self.master_fd, 1024)
                if not data:
                    break
                output.append(data.decode("utf-8", errors="replace"))
        except (OSError, IOError):
            pass
        # Join the output into a string
        result = "".join(output)
        # Remove common terminal control sequences
        result = self._strip_control_sequences(result)
        return result

    def _update_cwd(self):
        """Ask the shell for its current working directory and update self.cwd."""
        marker = "---CWD_MARKER---"
        try:
            os.write(self.master_fd, (f'pwd && echo "{marker}"\n').encode())
            pwd_output = ""
            # Read output specifically for pwd, longer timeout might be needed if shell is slow
            for _ in range(15):  # Read for up to ~3 seconds
                chunk = self._read_output(0.2)
                if chunk:
                    pwd_output += chunk
                if marker in pwd_output:  # Check accumulated output
                    break
                if not chunk:  # Stop if no output for a while
                    time.sleep(0.1)
            pwd_lines = pwd_output.splitlines()
            found_cwd = False
            # Find the line immediately preceding the marker
            for i in range(len(pwd_lines)):
                if pwd_lines[i] == marker and i > 0:
                    potential_cwd = pwd_lines[i-1]
                    # Basic validation: Check if it looks like a path
                    if potential_cwd.startswith("/") or potential_cwd.startswith("~"):
                        self.cwd = potential_cwd
                        print(f"[Debug] Updated CWD via pwd: {self.cwd}")
                        found_cwd = True
                        break
                    else:
                        print(f"[Warning] Line before CWD marker doesn't look like a path: {potential_cwd}")
            if not found_cwd:
                # Fallback: Try to find the last line before marker that looks like a path
                for i in range(len(pwd_lines) - 2, -1, -1):
                    if pwd_lines[i+1] == marker and (pwd_lines[i].startswith("/") or pwd_lines[i].startswith("~")):
                        self.cwd = pwd_lines[i]
                        print(f"[Debug] Updated CWD via pwd (fallback): {self.cwd}")
                        found_cwd = True
                        break
            if not found_cwd:
                print(f"[Warning] Could not reliably determine CWD from pwd output: {pwd_output}")
        except Exception as e:
            print(f"[Warning] Failed to update CWD via pwd: {e}")
            # Keep the old self.cwd as a fallback

    def execute(self, cmd):
        self.last_used = time.time()  # Update last used timestamp

        # --- Interaction Handling: Check for and clear pending interactive command ---
        if self.pending_interactive_context:
            print(f"[Info] New command received while interactive command (PID: {self.pid}) was pending.")
            # In secure mode, confirm cancellation of previous command
            if self.secure_mode:
                print(f'{COLOR_RED}[Secure Mode] Cancel previous interactive command and run: {cmd}{COLOR_RESET}')
                print(f'{COLOR_RED}[Secure Mode] Press ENTER to continue or ESC to abort{COLOR_RESET}')
                key = read_single_keypress()
                if key == '\x1b':  # ESC key
                    print(f'{COLOR_RED}[Secure Mode] Command aborted by user{COLOR_RESET}')
                    # Return JSON error for consistency
                    return json.dumps({'status': 'error', 'message': 'New command aborted by user in secure mode, previous interactive command still running'})
                elif key != '\r':  # Not ENTER key
                    print(f'{COLOR_RED}[Secure Mode] Invalid key. Command aborted{COLOR_RESET}')
                    return json.dumps({'status': 'error', 'message': 'Command aborted: Invalid key press in secure mode, previous interactive command still running'})
            print(f"[Info] Cancelling previous command.")
            # We don't kill the process as it's the same shell process
            # Just clear the pending state
            self.pending_interactive_context = None
            # Send Ctrl+C to interrupt any running command
            try:
                os.write(self.master_fd, "\x03".encode())
                time.sleep(0.1)  # Give it a moment to process the interrupt
                self._read_output(0.2)  # Clear any output from the interrupt
            except OSError as e:
                print(f"[Warning] Failed to send interrupt: {e}")
        # --- End Interaction Handling ---

        # Secure mode confirmation
        if self.secure_mode:
            print(f'{COLOR_RED}[Secure Mode] Execute command: {cmd}{COLOR_RESET}')
            print(f'{COLOR_RED}[Secure Mode] Press ENTER to continue or ESC to abort{COLOR_RESET}')
            key = read_single_keypress()
            if key == '\x1b':  # ESC key
                print(f'{COLOR_RED}[Secure Mode] Command aborted by user{COLOR_RESET}')
                # Return JSON error for consistency
                return json.dumps({'status': 'error', 'message': 'Command aborted by user in secure mode'})
            elif key != '\r':  # Not ENTER key
                print(f'{COLOR_RED}[Secure Mode] Invalid key. Command aborted{COLOR_RESET}')
                return json.dumps({'status': 'error', 'message': 'Command aborted: Invalid key press in secure mode'})

        # Generic solution for handling interactive programs
        # Use unbuffer to force programs to use line-buffered output
        if '|' not in cmd and not cmd.strip().startswith(('cd ', 'export ', 'alias ')):
            # Only modify commands that aren't pipelines or shell built-ins
            # Adding 'PAGER=cat' as a prefix forces non-interactive operation
            cmd = f"PAGER=cat LESS=FRX GIT_PAGER=cat {cmd}"
            print(f"[Debug] Modified command for non-interactive mode: {cmd}")

        print(f"[Debug] Executing command: {cmd}")
        
        # Generate a unique marker for this command
        marker_id = f"{self.marker_prefix}{time.time()}"
        
        try:
            os.write(self.master_fd, (cmd + "\n").encode())
        except OSError as e:
            print(f"[Error] Failed to write command to shell: {e}")
            # Try to recover by restarting the shell
            self.cleanup()
            self.__init__(secure_mode=self.secure_mode)
            # Try again with the new shell
            os.write(self.master_fd, (cmd + "\n").encode())

        # --- EXECUTE LOGIC START ---
        output_buffer = []
        command_completed = False
        prompt_detected = False
        timed_out_waiting = False

        # Read initial output, checking for prompt or hang
        # Increased loop count and slightly longer total wait time
        for i in range(30):  # Check for ~3 seconds total (30 * 0.1s)
            try:
                chunk = self._read_output(0.1)
                if chunk:
                    output_buffer.append(chunk)
                    current_output = "".join(output_buffer)
                    # Check if a prompt appears in the current accumulated output
                    if self._is_prompt(current_output):
                        prompt_detected = True
                        print(f"[Debug] Prompt detected: {current_output[-30:].strip()}")
                        break
                elif i > 15:  # No new output for 1.5+ seconds
                    # Check if process is still running
                    try:
                        pid, status = os.waitpid(self.pid, os.WNOHANG)
                        if pid == 0:  # Process is still running
                            # Simply conclude it's waiting for input if it's been quiet for a while
                            # but the process is still running - this avoids terminating an interactive process
                            print(f"[Debug] No output for 1.5+ seconds but process is still running, assuming interactive")
                            timed_out_waiting = True
                            break
                        else:  # Process ended without prompt
                            command_completed = True
                            break
                    except OSError:  # Process error
                        command_completed = True
                        break
            except Exception as e:
                print(f"[Warning] Error during output reading: {e}")
                break

        # --- Interaction Handling: Check for Hang ---
        if timed_out_waiting and not prompt_detected:
            print(f"[Info] Command '{cmd}' timed out waiting for output/prompt. Process {self.pid} still running. Entering interactive mode.")
            self.pending_interactive_context = {
                'cmd': cmd
            }
            # Return minimal output collected so far, plus the interaction signal
            initial_output = "".join(output_buffer)
            # Clean the initial output
            lines = initial_output.split("\n")
            if lines and lines[0].strip() == cmd:
                lines = lines[1:]  # Remove command echo
            cleaned_output = "\n".join(line for line in lines if line.strip())  # Remove empty lines

            # Return JSON response for interaction
            response_data = {
                'status': 'requires_interaction',
                'output': self._strip_control_sequences(cleaned_output),  # Return stripped initial output
                'message': 'Command is waiting. Use /cmd with "input_str" to view output or send input. Use /cmd with a new "cmd" to cancel and run a new command.'
            }
            return json.dumps(response_data)  # Return JSON string directly
        # --- End Interaction Handling ---

        # If we got here, the command either completed or returned to prompt quickly
        self.pending_interactive_context = None  # Ensure no pending state

        # Process output if command completed or prompt was seen
        result = "".join(output_buffer)

        # Update CWD after command execution
        self._update_cwd()

        # Clean output: remove command echo and trailing prompt
        lines = result.split("\n")
        if lines and lines[0].strip() == cmd:
            lines = lines[1:]

        # More robust prompt removal from final line
        if lines and self._is_prompt(lines[-1]):
            lines.pop()  # Remove the prompt line completely

        final_output = "\n".join(line for line in lines if line.strip())  # Filter empty lines

        # Return JSON response for completion
        response_data = {
            'status': 'completed',
            'output': self._strip_control_sequences(final_output)
        }
        return json.dumps(response_data)  # Return JSON string directly
        # --- EXECUTE LOGIC END ---

    def cleanup(self):
        self.pending_interactive_context = None  # Clear any pending state on cleanup
        if hasattr(self, 'pid') and self.pid:
            try:
                os.kill(self.pid, signal.SIGKILL)  # Using SIGKILL instead of SIGTERM
                os.waitpid(self.pid, 0)
            except OSError as e:
                print(f"[Warning] Failed to kill process {self.pid}: {e}")
            except Exception as e:
                print(f"[Warning] Error during process cleanup: {e}")

        if hasattr(self, 'master_fd') and self.master_fd is not None:
            try:
                os.close(self.master_fd)
                self.master_fd = None
            except OSError as e:
                print(f"[Warning] Failed to close master_fd: {e}")
            except Exception as e:
                print(f"[Warning] Error during file descriptor cleanup: {e}")


class WindowsShell(BaseShell):
    """Windows-specific shell implementation using subprocess"""
    def __init__(self, secure_mode=False):
        super().__init__(secure_mode)
        self.process = None
        self.output_thread = None
        self.output_buffer = StringIO()
        self.output_lock = threading.Lock()
        self.process_lock = threading.Lock()
        self.process_running = False
        self.marker_prefix = "CMD_MARKER_"  # Prefix for command completion markers
        
        try:
            # Start cmd.exe process
            self.process = subprocess.Popen(
                ['cmd.exe'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,  # Unbuffered
                shell=False,
                universal_newlines=True,  # Text mode
                creationflags=subprocess.CREATE_NO_WINDOW,  # Don't show a window
                env=os.environ.copy()  # Use parent environment
            )
            self.process_running = True
            
            # Start output reader thread
            self.output_thread = threading.Thread(
                target=self._output_reader,
                daemon=True
            )
            self.output_thread.start()
            
            # Wait for initial prompt
            time.sleep(0.5)
            self._clear_output_buffer()
        except Exception as e:
            print(f"[Error] Windows shell initialization failed: {str(e)}")
            self.cleanup()
            raise

    def _output_reader(self):
        """Thread function to continuously read process output"""
        while self.process_running and self.process and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                    
                with self.output_lock:
                    self.output_buffer.write(line)
            except Exception as e:
                print(f"[Warning] Error reading from Windows shell: {str(e)}")
                time.sleep(0.1)

    def _clear_output_buffer(self):
        """Clear the output buffer and return its contents"""
        with self.output_lock:
            content = self.output_buffer.getvalue()
            self.output_buffer = StringIO()
            return content

    def _update_cwd(self):
        """Update the current working directory by running 'cd' command"""
        try:
            with self.process_lock:
                if not self.process_running or self.process.poll() is not None:
                    return
                    
                self._clear_output_buffer()  # Clear any pending output
                self.process.stdin.write("cd\n")
                self.process.stdin.flush()
                
                # Wait for output
                time.sleep(0.5)
                output = self._clear_output_buffer()
                
                # Parse the output to find the current directory
                lines = output.splitlines()
                for line in lines:
                    # Windows 'cd' without arguments shows the current directory
                    # Format is typically: "<drive>:\<path>"
                    if re.match(r'^[A-Za-z]:\\', line.strip()):
                        self.cwd = line.strip()
                        print(f"[Debug] Updated Windows CWD: {self.cwd}")
                        return
        except Exception as e:
            print(f"[Warning] Failed to update Windows CWD: {str(e)}")

    def execute(self, cmd):
        self.last_used = time.time()  # Update last used timestamp

        # --- Interaction Handling: Check for and clear pending interactive command ---
        if self.pending_interactive_context:
            print(f"[Info] New command received while interactive command was pending.")
            # In secure mode, confirm cancellation of previous command
            if self.secure_mode:
                print(f'{COLOR_RED}[Secure Mode] Cancel previous interactive command and run: {cmd}{COLOR_RESET}')
                print(f'{COLOR_RED}[Secure Mode] Press ENTER to continue or ESC to abort{COLOR_RESET}')
                key = read_single_keypress()
                if key == '\x1b':  # ESC key
                    print(f'{COLOR_RED}[Secure Mode] Command aborted by user{COLOR_RESET}')
                    # Return JSON error for consistency
                    return json.dumps({'status': 'error', 'message': 'New command aborted by user in secure mode, previous interactive command still running'})
                elif key != '\r':  # Not ENTER key
                    print(f'{COLOR_RED}[Secure Mode] Invalid key. Command aborted{COLOR_RESET}')
                    return json.dumps({'status': 'error', 'message': 'Command aborted: Invalid key press in secure mode, previous interactive command still running'})
            print("Cancelling previous command.")
            # Clear the pending state
            self.pending_interactive_context = None
            # Send Ctrl+C to interrupt any running command
            try:
                self.process.stdin.write("\x03\n")
                self.process.stdin.flush()
                time.sleep(0.1)  # Give it a moment to process the interrupt
                self._clear_output_buffer()  # Clear any output from the interrupt
            except Exception as e:
                print(f"[Warning] Failed to send interrupt: {str(e)}")
        # --- End Interaction Handling ---

        # Secure mode confirmation
        if self.secure_mode:
            print(f'{COLOR_RED}[Secure Mode] Execute command: {cmd}{COLOR_RESET}')
            print(f'{COLOR_RED}[Secure Mode] Press ENTER to continue or ESC to abort{COLOR_RESET}')
            key = read_single_keypress()
            if key == '\x1b':  # ESC key
                print(f'{COLOR_RED}[Secure Mode] Command aborted by user{COLOR_RESET}')
                # Return JSON error for consistency
                return json.dumps({'status': 'error', 'message': 'Command aborted by user in secure mode'})
            elif key != '\r':  # Not ENTER key
                print(f'{COLOR_RED}[Secure Mode] Invalid key. Command aborted{COLOR_RESET}')
                return json.dumps({'status': 'error', 'message': 'Command aborted: Invalid key press in secure mode'})

        print(f"[Debug] Executing Windows command: {cmd}")
        
        with self.process_lock:
            if not self.process_running or self.process.poll() is not None:
                # Process has died, restart it
                print(f"[Warning] Windows shell process has died, restarting...")
                self.cleanup()
                self.__init__(secure_mode=self.secure_mode)
            
            # Clear any pending output
            self._clear_output_buffer()
            
            # Generate a unique marker for this command
            marker_id = f"{self.marker_prefix}{time.time()}"
            
            try:
                # Send the command
                self.process.stdin.write(f"{cmd}\n")
                self.process.stdin.flush()
            except Exception as e:
                print(f"[Error] Failed to write command to Windows shell: {str(e)}")
                # Try to recover by restarting the shell
                self.cleanup()
                self.__init__(secure_mode=self.secure_mode)
                # Try again with the new shell
                self.process.stdin.write(f"{cmd}\n")
                self.process.stdin.flush()

        # Wait for initial output
        time.sleep(0.5)
        output = self._clear_output_buffer()
        
        # Try to detect if command has completed by checking for prompt
        prompt_detected = self._is_prompt(output)
        
        # If no prompt detected, wait longer for more output
        if not prompt_detected:
            # Wait up to 3 seconds (30 * 0.1) for more output
            for i in range(30):
                time.sleep(0.1)
                new_output = self._clear_output_buffer()
                if new_output:
                    output += new_output
                    # Check if we got a prompt now
                    if self._is_prompt(output):
                        prompt_detected = True
                        break
                elif i >= 15:  # No output for 1.5+ seconds
                    # If the process is running but no output for a while,
                    # it's likely waiting for interactive input
                    print(f"[Debug] No output for 1.5+ seconds, assuming interactive command")
                    break
        
        # If we still don't have a prompt, the command is likely interactive
        if not prompt_detected:
            # Command is likely waiting for input
            self.pending_interactive_context = {'cmd': cmd}
            
            # Clean the output
            lines = output.splitlines()
            # Remove command echo if present
            if lines and cmd in lines[0]:
                lines = lines[1:]
            cleaned_output = "\n".join(line for line in lines if line.strip())
            
            # Return JSON response for interaction
            response_data = {
                'status': 'requires_interaction',
                'output': self._strip_control_sequences(cleaned_output),
                'message': 'Command is waiting. Use /cmd with "input_str" to view output or send input. Use /cmd with a new "cmd" to cancel and run a new command.'
            }
            return json.dumps(response_data)
        
        # If we got here, the command either completed or returned to prompt
        self.pending_interactive_context = None  # Ensure no pending state
        
        # Update CWD after command execution
        self._update_cwd()
        
        # Clean output: remove command echo and trailing prompt
        lines = output.splitlines()
        # Remove command echo if present
        if lines and cmd in lines[0]:
            lines = lines[1:]
            
        # Remove prompt from the last line if present
        if lines and self._is_prompt(lines[-1]):
            lines.pop()
            
        final_output = "\n".join(line for line in lines if line.strip())  # Filter empty lines
        
        # Return JSON response for completion
        response_data = {
            'status': 'completed',
            'output': self._strip_control_sequences(final_output)
        }
        return json.dumps(response_data)

    def cleanup(self):
        self.pending_interactive_context = None  # Clear any pending state on cleanup
        self.process_running = False
        
        if self.process:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            except Exception as e:
                print(f"[Warning] Error terminating Windows shell process: {str(e)}")
            self.process = None
            
        if self.output_thread and self.output_thread.is_alive():
            # Thread is daemon, so it will terminate when the program exits
            # Just wait a moment for it to clean up
            try:
                self.output_thread.join(timeout=1)
            except Exception:
                pass
            self.output_thread = None


class ShellHandler(BaseHTTPRequestHandler):
    shell = None
    backup_dir = ".edits_backup"
    MAX_RESPONSE_LENGTH = 50000  # characters
    SHELL_IDLE_TIMEOUT = 300  # 5 minutes
    secure_mode = False

    @classmethod
    def get_shell(cls):
        current_time = time.time()
        try:
            if (
                cls.shell is None or 
                (current_time - cls.shell.last_used) > cls.SHELL_IDLE_TIMEOUT
            ):
                if cls.shell is not None:
                    print("[Info] Cleaning up idle shell")
                    cls.shell.cleanup()
                
                # Create the appropriate shell based on platform
                if IS_WINDOWS:
                    cls.shell = WindowsShell(secure_mode=cls.secure_mode)
                else:
                    cls.shell = UnixShell(secure_mode=cls.secure_mode)
                    
            return cls.shell
        except Exception as e:
            print(f"[Error] Failed to get shell: {e}")
            # If there was an error, try to clean up and create a new shell
            if cls.shell is not None:
                try:
                    cls.shell.cleanup()
                except:
                    pass
                    
            # Create the appropriate shell based on platform
            if IS_WINDOWS:
                cls.shell = WindowsShell(secure_mode=cls.secure_mode)
            else:
                cls.shell = UnixShell(secure_mode=cls.secure_mode)
                
            return cls.shell

    @classmethod
    def confirm_destructive_operation(cls, operation_desc):
        """Ask for confirmation before performing destructive operations in secure mode"""
        if cls.secure_mode:
            print(f'{COLOR_RED}[Secure Mode] {operation_desc}{COLOR_RESET}')
            print(f'{COLOR_RED}[Secure Mode] Press ENTER to continue or ESC to abort{COLOR_RESET}')
            key = read_single_keypress()
            if key == '\x1b':  # ESC key
                print(f'{COLOR_RED}[Secure Mode] Operation aborted by user{COLOR_RESET}')
                return False
            elif key != '\r':  # Not ENTER key
                print(f'{COLOR_RED}[Secure Mode] Invalid key. Operation aborted{COLOR_RESET}')
                return False
            return True
        return True  # Always allow in non-secure mode

    @classmethod
    def is_git_repo(cls, path):
        """Check if a path is inside a git repository"""
        try:
            # Direct subprocess call to check if git repo
            dir_path = os.path.dirname(path) if os.path.isfile(path) else path
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=dir_path,
                text=True,
                timeout=1  # Short timeout to avoid hanging
            )
            return result.returncode == 0 and "true" in result.stdout
        except Exception as e:
            print(f"[Warning] Failed to check if path is in git repo: {str(e)}")
            return False

    @classmethod
    def git_commit_file(cls, file_path, operation_type):
        """Commit a file to git after it has been modified"""
        try:
            dir_path = os.path.dirname(file_path)
            file_name = os.path.basename(file_path)
            commit_message = f"{operation_type} file {file_name}"
            
            # Add file to git staging
            add_result = subprocess.run(
                ["git", "add", file_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=dir_path,
                text=True,
                timeout=2
            )
            
            if add_result.returncode != 0:
                print(f"[Warning] Git add failed: {add_result.stderr}")
                return False
                
            # Commit file
            commit_result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=dir_path,
                text=True,
                timeout=3
            )
            
            if commit_result.returncode == 0:
                print(f"[Info] Git commit successful: {commit_message}")
                return True
            else:
                print(f"[Warning] Git commit failed: {commit_result.stderr}")
                return False
        except Exception as e:
            print(f"[Warning] Failed to commit file to git: {str(e)}")
            return False

    @classmethod
    def cleanup_backups(cls):
        """Clean up all backup files"""
        backup_path = os.path.join(os.getcwd(), cls.backup_dir)
        if os.path.exists(backup_path):
            try:
                import shutil
                shutil.rmtree(backup_path)
            except Exception as e:
                print(f"[Error] Failed to cleanup backups: {str(e)}")

    def __init__(self, *args, **kwargs):
        # Create backup directory if it doesn't exist
        os.makedirs(os.path.join(os.getcwd(), self.backup_dir), exist_ok=True)
        super().__init__(*args, **kwargs)

    def _get_backup_path(self, file_path):
        """Generate a backup file path for a given file"""
        # Use a hash of the original path to create a unique backup filename
        file_hash = str(hash(file_path))
        return os.path.join(self.backup_dir, f"{file_hash}.bak")

    def _create_backup(self, abs_path):
        """Create a backup of the file if it exists"""
        if os.path.exists(abs_path):
            try:
                backup_path = self._get_backup_path(abs_path)
                with open(abs_path, "r", encoding="utf-8") as src:
                    with open(backup_path, "w", encoding="utf-8") as dst:
                        dst.write(src.read())
            except Exception as e:
                print(f"[Warning] Failed to create backup for {abs_path}: {str(e)}")
                # Continue without backup rather than failing the operation

    def log_message(self, format, *args):
        # Override to print to stdout instead of stderr
        print("[Server] %s - %s" % (self.address_string(), format % args))

    def do_POST(self):
        if self.path == "/text_editor":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data)
                command = data.get("command")
                path = data.get("path")
                if not command or not path:
                    raise ValueError("Missing required parameters: command and path")
                response = self.handle_text_editor(data)
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(response.encode())
            except Exception as e:
                print(f"[Error] Text editor operation failed: {str(e)}")
                import traceback
                print(f"[Error] Traceback: {traceback.format_exc()}")
                self.send_response(500)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(str(e).encode())
        elif self.path == "/cmd":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data)
                shell = self.get_shell()  # Get or create shell

                # Check if this is an interaction request or a command request
                if "input_str" in data:
                    # This is an interaction request (formerly /interact)
                    input_str = data.get("input_str", "")

                    # Check if there is a pending interactive context
                    if not shell.pending_interactive_context:
                        raise ValueError("No interactive command pending")

                    # Check if we need confirmation in secure mode
                    if self.secure_mode:
                        print(f'{COLOR_RED}[Secure Mode] Send input to interactive process: {input_str[:50]}...{COLOR_RESET}')
                        print(f'{COLOR_RED}[Secure Mode] Press ENTER to continue or ESC to abort{COLOR_RESET}')
                        key = read_single_keypress()
                        if key == '\x1b':  # ESC key
                            print(f'{COLOR_RED}[Secure Mode] Input aborted by user{COLOR_RESET}')
                            self.send_response(403)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            error_response = json.dumps({'status': 'error', 'message': 'Input aborted by user in secure mode'})
                            self.wfile.write(error_response.encode())
                            return
                        elif key != '\r':  # Not ENTER key
                            print(f'{COLOR_RED}[Secure Mode] Invalid key. Input aborted{COLOR_RESET}')
                            self.send_response(403)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            error_response = json.dumps({'status': 'error', 'message': 'Input aborted: Invalid key press in secure mode'})
                            self.wfile.write(error_response.encode())
                            return

                    # Send input if provided
                    if input_str:
                        print(f"[Debug] Sending input to interactive command: {input_str[:50]}...")
                        try:
                            if IS_WINDOWS:
                                shell.process.stdin.write(f"{input_str}\n")
                                shell.process.stdin.flush()
                            else:
                                os.write(shell.master_fd, (input_str + '\n').encode())
                        except Exception as e:
                            # Handle cases where the process might have died unexpectedly
                            print(f"[Warning] Failed to write input: {e}")
                            shell.pending_interactive_context = None
                            raise ValueError(f"Process seems to have terminated or I/O error occurred.")

                    # Wait for output
                    time.sleep(0.5)
                    
                    # Read output
                    if IS_WINDOWS:
                        output = shell._clear_output_buffer()
                    else:
                        # For Unix, read output with a slightly longer timeout
                        output_buffer = []
                        for _ in range(10):
                            try:
                                chunk = shell._read_output(0.1)
                                if chunk:
                                    output_buffer.append(chunk)
                            except Exception as e:
                                print(f"[Warning] Error reading output: {e}")
                                break
                            # Small delay if no output
                            if not chunk:
                                time.sleep(0.1)
                        output = "".join(output_buffer)

                    # Check for prompt in the output
                    prompt_detected = shell._is_prompt(output)
                    
                    # Clean the output
                    lines = output.splitlines()
                    if prompt_detected and lines:
                        # Remove the prompt line
                        lines.pop()
                    cleaned_output = shell._strip_control_sequences("\n".join(lines))

                    # Decide response based on state
                    if prompt_detected:
                        print(f"[Info] Interactive session completed.")
                        shell.pending_interactive_context = None  # Clear the pending state
                        response_data = {
                            'status': 'completed',
                            'output': self._truncate_response(cleaned_output)  # Truncate here
                        }
                    else:
                        # Still running, waiting for more input or processing
                        response_data = {
                            'status': 'pending_output',
                            'output': self._truncate_response(cleaned_output),  # Truncate here
                            'message': 'Command still running. Use /cmd with "input_str" to view more output or send input.'
                        }
                else:
                    # This is a regular command request
                    cmd = data.get("cmd", "")
                    if not cmd:
                        raise ValueError("Missing required parameter: cmd")

                    # shell.execute now returns a JSON string
                    json_response_str = shell.execute(cmd)
                    response_data = json.loads(json_response_str)

                    # Truncate the 'output' field if it exists
                    if 'output' in response_data:
                        response_data['output'] = self._truncate_response(response_data['output'])

                # Re-serialize the potentially modified data
                response = json.dumps(response_data)
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(response.encode())
            except Exception as e:
                print(f"[Error] /cmd failed: {str(e)}")
                import traceback
                print(f"[Error] Traceback: {traceback.format_exc()}")
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                error_response = json.dumps({'status': 'error', 'message': str(e)})
                self.wfile.write(error_response.encode())
        elif self.path == "/write_file":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data)
                filepath = data["path"]
                content = data["content"]
                print(f"[Debug] Current working directory: {self.shell.cwd}")
                print(f"[Debug] Requested file path: {filepath}")

                # Expand tilde in filepath
                if filepath.startswith("~/"):
                    filepath = os.path.expanduser(filepath)
                    abs_filepath = filepath
                else:
                    # Make path relative to shell's current working directory
                    abs_filepath = os.path.join(self.shell.cwd, filepath)

                print(f"[Debug] Absolute file path: {abs_filepath}")

                # Check if we need confirmation in secure mode
                if not self.confirm_destructive_operation(f"Write file: {abs_filepath}"):
                    self.send_response(403)
                    self.send_header("Content-type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"Operation aborted by user")
                    return

                # Create backup before modification if file exists
                self._create_backup(abs_filepath)

                # create directories if they don't exist
                dir_path = os.path.dirname(abs_filepath)
                if dir_path:
                    print(f"[Debug] Creating directory: {dir_path}")
                    os.makedirs(dir_path, exist_ok=True)

                print(f"[Debug] Writing content: {content[:50]}...")
                with open(abs_filepath, "w", encoding="utf-8") as f:
                    f.write(content)

                print(
                    f"[Debug] File write complete. Checking if file exists: {os.path.exists(abs_filepath)}"
                )
                if os.path.exists(abs_filepath):
                    print(f"[Debug] File size: {os.path.getsize(abs_filepath)} bytes")
                    
                    # Check if file is in a git repo and commit if it is
                    if self.is_git_repo(abs_filepath):
                        print(f"[Info] File is in a git repo, committing changes")
                        self.git_commit_file(abs_filepath, "Writing")

                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"File written successfully")
            except Exception as e:
                print(f"[Error] Failed to write file: {str(e)}")
                import traceback
                print(f"[Error] Traceback: {traceback.format_exc()}")
                self.send_response(500)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(str(e).encode())
        elif self.path == "/repo-map":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                repo_path = None
                
                if content_length > 0:
                    post_data = self.rfile.read(content_length)
                    try:
                        data = json.loads(post_data)
                        repo_path = data.get("path")
                    except json.JSONDecodeError:
                        # If it's not JSON, treat it as plain text path
                        repo_path = post_data.decode('utf-8').strip()
                
                # Default to shell's current working directory if no path provided
                if not repo_path:
                    shell = self.get_shell()
                    repo_path = shell.cwd
                
                # Expand tilde and make absolute path
                if repo_path.startswith("~/"):
                    repo_path = os.path.expanduser(repo_path)
                elif not os.path.isabs(repo_path):
                    shell = self.get_shell()
                    repo_path = os.path.join(shell.cwd, repo_path)
                
                print(f"[Debug] repo-map using path: {repo_path}")
                
                repo_mapper = RepoMapper(repo_path)
                result = repo_mapper.generate_repo_map()
                
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(result.encode())
            except Exception as e:
                print(f"[Error] repo-map operation failed: {str(e)}")
                import traceback
                print(f"[Error] Traceback: {traceback.format_exc()}")
                self.send_response(500)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                error_msg = f"repo-map failed: {str(e)}"
                self.wfile.write(error_msg.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def _truncate_response(self, response):
        """Truncate response if too long and add <response clipped> marker"""
        if len(response) > self.MAX_RESPONSE_LENGTH:
            truncated = response[: self.MAX_RESPONSE_LENGTH]
            # Try to truncate at the last newline to keep lines intact
            last_newline = truncated.rfind("\n")
            if last_newline > 0:
                truncated = truncated[:last_newline]
            return truncated + "\n<response clipped>"
        return response

    def handle_text_editor(self, data):
        command = data["command"]
        path = data["path"]
        shell = self.get_shell()  # Get or create shell instance

        # Expand tilde in path
        if path.startswith("~/"):
            path = os.path.expanduser(path)
            abs_path = path
        else:
            abs_path = os.path.join(shell.cwd, path)

        print(f"[Debug] Text editor: {command} operation on file: {abs_path}")

        if command == "count":
            old_str = data.get("old_str")
            if not old_str:
                raise ValueError("old_str parameter is required for count command")

            if os.path.isfile(abs_path):
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
                count = content.count(old_str)
                return f"String '{old_str}' appears {count} times in the file"
            else:
                raise FileNotFoundError(f"File not found: {path}")
        elif command == "view":
            if os.path.isfile(abs_path):
                # Handle view_range if specified
                view_range = data.get("view_range")
                if view_range:
                    # Validate view_range is an array of 2 integers
                    if (
                        not isinstance(view_range, list) or 
                        len(view_range) != 2 or 
                        not all(isinstance(x, int) for x in view_range)
                    ):
                        raise ValueError("view_range must be an array of 2 integers")

                    # Validate start line is positive
                    if view_range[0] < 1:
                        raise ValueError("view_range start line must be >= 1")

                    # Validate end line is >= start line or -1 (indicating end of file)
                    if view_range[1] != -1 and view_range[1] < view_range[0]:
                        raise ValueError("view_range end line must be >= start line or -1 for end of file")

                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if view_range:
                    lines = content.splitlines()
                    start = max(0, view_range[0] - 1)  # Convert to 0-based index
                    # When end is -1, show all lines from start to the end of file
                    end = len(lines) if view_range[1] == -1 else min(len(lines), view_range[1])
                    content = "\n".join(lines[start:end])

                # Add line numbers
                numbered_lines = []
                if view_range:
                    # Use absolute line numbers when view_range is specified
                    for i, line in enumerate(content.splitlines(), view_range[0]):
                        numbered_lines.append(f"{i:6d}\t{line}")
                else:
                    # Regular numbering when showing the whole file
                    for i, line in enumerate(content.splitlines(), 1):
                        numbered_lines.append(f"{i:6d}\t{line}")

                response = "\n".join(numbered_lines)
                return self._truncate_response(response)
            elif os.path.isdir(abs_path):
                # List files and directories up to 2 levels deep
                result = []
                for root, dirs, files in os.walk(abs_path):
                    depth = root[len(abs_path) :].count(os.sep)
                    if depth <= 1:  # Only process up to 2 levels
                        # Skip hidden files/directories
                        dirs[:] = [d for d in dirs if not d.startswith(".")]
                        files = [f for f in files if not f.startswith(".")]
                        path_prefix = root[len(abs_path) :].lstrip(os.sep)
                        for name in files:
                            if path_prefix:
                                result.append(os.path.join(path_prefix, name))
                            else:
                                result.append(name)
                response = "\n".join(sorted(result))
                return self._truncate_response(response)
            else:
                raise FileNotFoundError(f"Path not found: {path}")
        elif command == "create":
            file_text = data.get("file_text")
            if not file_text:
                raise ValueError("file_text parameter is required for create command")

            # Check if we need confirmation in secure mode
            if not self.confirm_destructive_operation(f"Create file: {abs_path}"):
                return "Operation aborted by user"

            # Create backup if file exists
            if os.path.exists(abs_path):
                self._create_backup(abs_path)

            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(file_text)
                
            # Check if file is in a git repo and commit if it is
            if self.is_git_repo(abs_path):
                print(f"[Info] File is in a git repo, committing changes")
                self.git_commit_file(abs_path, "Creating")

            return "File created successfully"
        elif command == "str_replace":
            old_str = data.get("old_str")
            new_str = data.get("new_str", "")
            if not old_str:
                raise ValueError(
                    "old_str parameter is required for str_replace command"
                )

            # Check if we need confirmation in secure mode
            if not self.confirm_destructive_operation(f"Replace text in file: {abs_path}"):
                return "Operation aborted by user"

            # Create backup before modification
            self._create_backup(abs_path)

            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Verify old_str exists exactly once
            if content.count(old_str) != 1:
                raise ValueError("old_str must match exactly one location in the file")

            # Perform the replacement
            new_content = content.replace(old_str, new_str)

            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)
                
            # Check if file is in a git repo and commit if it is
            if self.is_git_repo(abs_path):
                print(f"[Info] File is in a git repo, committing changes")
                self.git_commit_file(abs_path, "Editing")

            return "String replaced successfully"
        elif command == "insert":
            insert_line = data.get("insert_line")
            new_str = data.get("new_str")
            if insert_line is None or new_str is None:
                raise ValueError(
                    "insert_line and new_str parameters are required for insert command"
                )

            # Check if we need confirmation in secure mode
            if not self.confirm_destructive_operation(f"Insert text in file: {abs_path}"):
                return "Operation aborted by user"

            # Create backup before modification
            self._create_backup(abs_path)

            with open(abs_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if not (1 <= insert_line <= len(lines) + 1):
                raise ValueError(f"Invalid insert_line: {insert_line}")

            lines.insert(insert_line, new_str + "\n")

            with open(abs_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
                
            # Check if file is in a git repo and commit if it is
            if self.is_git_repo(abs_path):
                print(f"[Info] File is in a git repo, committing changes")
                self.git_commit_file(abs_path, "Inserting into")

            return "Text inserted successfully"
        elif command == "replace_first":
            old_str = data.get("old_str")
            new_str = data.get("new_str", "")
            if not old_str:
                raise ValueError(
                    "old_str parameter is required for replace_first command"
                )

            # Check if we need confirmation in secure mode
            if not self.confirm_destructive_operation(f"Replace first occurrence in file: {abs_path}"):
                return "Operation aborted by user"

            # Create backup before modification
            self._create_backup(abs_path)

            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Count occurrences for informational purposes
            match_count = content.count(old_str)

            if match_count == 0:
                raise ValueError("old_str not found in the file")

            # Replace only the first occurrence
            new_content = content.replace(old_str, new_str, 1)

            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)
                
            # Check if file is in a git repo and commit if it is
            if self.is_git_repo(abs_path):
                print(f"[Info] File is in a git repo, committing changes")
                self.git_commit_file(abs_path, "Editing")

            return f"First occurrence replaced successfully. {match_count} total matches found."
        else:
            raise ValueError(f"Invalid command: {command}")

    def do_GET(self):
        if self.path.startswith("/read_file"):
            try:
                from urllib.parse import urlparse, parse_qs
                query = parse_qs(urlparse(self.path).query)
                filepath = query.get("path", [""])[0]

                print(f"[Debug] Current working directory: {self.shell.cwd}")
                print(f"[Debug] Requested file path: {filepath}")

                # Only check for directory traversal attempts
                if ".." in filepath:
                    raise ValueError("Invalid file path")

                # Expand tilde in filepath
                if filepath.startswith("~/"):
                    filepath = os.path.expanduser(filepath)
                    abs_filepat
                else:
                    # Make path relative to shell's current working directory
                    abs_filepath = os.path.join(self.shell.cwd, filepath)

                print(f"[Debug] Absolute file path: {abs_filepath}")
                print(
                    f"[Debug] Checking if file exists: {os.path.exists(abs_filepath)}"
                )

                with open(abs_filepath, "r", encoding="utf-8") as f:
                    content = f.read()

                print(f"[Debug] Read content length: {len(content)} bytes")
                response = self._truncate_response(content)

                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(response.encode())
            except Exception as e:
                print(f"[Error] Failed to read file: {str(e)}")
                import traceback
                print(f"[Error] Traceback: {traceback.format_exc()}")
                self.send_response(500)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            self.send_response(404)
            self.end_headers()


def signal_handler(signum, frame):
    print("\nForce quitting...")
    os._exit(0)  # Force quit


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Start shell server')
    parser.add_argument('--port', type=int, default=6666, help='Port to run the server on')
    parser.add_argument('--secure', action='store_true', help='Enable secure mode with command confirmation')
    parser.add_argument('--generate-repo-map', action='store_true', help='Generate .repo-map file in current directory and exit')
    args = parser.parse_args()

    # Handle repo-map generation if requested
    if args.generate_repo_map:
        print("Generating .repo-map file...")
        try:
            repo_mapper = RepoMapper(os.getcwd())
            repo_map_content = repo_mapper.generate_repo_map()
            
            # Write to .repo-map file in current directory
            repo_map_file = os.path.join(os.getcwd(), '.repo-map')
            with open(repo_map_file, 'w', encoding='utf-8') as f:
                f.write(repo_map_content)
            
            print(f"✅ Repository map generated successfully: {repo_map_file}")
            print(f"📊 File size: {os.path.getsize(repo_map_file)} bytes")
            
            # Show a preview of the content
            lines = repo_map_content.split('\n')
            if len(lines) > 10:
                print("\n📋 Preview (first 10 lines):")
                for i, line in enumerate(lines[:10], 1):
                    print(f"  {i:2d}: {line}")
                print(f"  ... ({len(lines) - 10} more lines)")
            else:
                print(f"\n📋 Content ({len(lines)} lines):")
                for i, line in enumerate(lines, 1):
                    print(f"  {i:2d}: {line}")
                    
        except Exception as e:
            print(f"❌ Error generating repo-map: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            sys.exit(1)
        
        sys.exit(0)

    # Set secure mode based on command line argument
    ShellHandler.secure_mode = args.secure
    if args.secure:
        print(f'{COLOR_RED}Starting server in SECURE MODE - commands will require confirmation{COLOR_RESET}')

    # Set up signal handlers based on platform
    if not IS_WINDOWS:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def cleanup_and_exit(signum=None, frame=None):
        print("\nCleaning up...")
        ShellHandler.cleanup_backups()
        print("Force quitting...")
        os._exit(0)
    
    # Replace the old signal_handler with our new cleanup_and_exit
    if not IS_WINDOWS:
        signal.signal(signal.SIGINT, cleanup_and_exit)
        signal.signal(signal.SIGTERM, cleanup_and_exit)
    
    server_address = ("", args.port)
    httpd = HTTPServer(server_address, ShellHandler)
    print(f"Starting cross-platform shell server on port {args.port}...")
    print(f"Running on {platform.system()} ({platform.release()})")
    
    try:
        httpd.serve_forever()
    except:
        cleanup_and_exit()
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import pty
import os
import select
import fcntl
import termios
import struct
import json
import signal
import sys
import time
import tty
import re

# ANSI Color Codes
COLOR_RED = '\033[91m'
COLOR_RESET = '\033[0m'

# Add a regex pattern to detect shell prompts
PROMPT_PATTERN = re.compile(r'[^>\n]*[$#>]\s*$')

def read_single_keypress():
    """Read a single keypress from stdin in a cross-platform way"""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


class Shell:
    def __init__(self, secure_mode=False):
        self.secure_mode = secure_mode
        self.master_fd = None
        self.pid = None
        self.cwd = os.getcwd()  # Track initial working directory
        self.last_used = time.time()  # Track when the shell was last used
        self.pending_interactive_context = None # Clear any pending state on initialization
        
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

                    env = {
                        "TERM": "xterm",
                        "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                        "PS1": "$ ",
                        "LANG": "en_US.UTF-8",
                        # Prevent paging in various tools
                        "PAGER": "cat",
                        "GIT_PAGER": "cat",
                        "LESS": "-FRX",
                        "MORE": "-FX",
                        # Disable interactive prompting in common utilities
                        "GIT_CONFIG_PARAMETERS": "'core.pager=cat' 'color.ui=never'",
                        # No fancy prompts
                        "PROMPT_COMMAND": "",
                    }
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
        
    def _strip_control_sequences(self, text):
        """Strip common terminal control sequences from the output"""
        # Pattern to match common terminal control sequences
        # This includes color codes, cursor movement, and other control characters
        control_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][0-9;]*[a-zA-Z]|\r|\x1b\(B')
        
        # Remove the control sequences
        return control_pattern.sub('', text)
        
    def _is_prompt(self, text):
        """Check if the text ends with a shell prompt"""
        return bool(PROMPT_PATTERN.search(text.rstrip()))

    def _update_cwd(self):
        """Ask the shell for its current working directory and update self.cwd."""
        marker = "---CWD_MARKER---"
        try:
            os.write(self.master_fd, (f'pwd && echo "{marker}"\n').encode())
            pwd_output = ""
            # Read output specifically for pwd, longer timeout might be needed if shell is slow
            for _ in range(15): # Read for up to ~3 seconds
                chunk = self._read_output(0.2)
                if chunk:
                    pwd_output += chunk
                if marker in pwd_output: # Check accumulated output
                    break
                if not chunk: # Stop if no output for a while
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
            print(f"[Info] New command received while interactive command (PID: {self.pid}) was pending. Cancelling previous command.")
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
        for i in range(30): # Check for ~3 seconds total (30 * 0.1s)
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
                elif i > 5: # Require at least a few checks before declaring timeout
                    # Check if process is still running before declaring timeout
                    try:
                        pid, status = os.waitpid(self.pid, os.WNOHANG)
                        if pid == 0: # Process is still running, likely waiting
                            timed_out_waiting = True
                            break
                        else: # Process ended without prompt
                            command_completed = True
                            break
                    except OSError: # Process already reaped or invalid
                        command_completed = True
                        break
            except Exception as e:
                print(f"[Warning] Error during output reading: {e}")
                break

        # --- Interaction Handling: Check for Hang ---
        if timed_out_waiting and not prompt_detected:
            print(f"[Info] Command '{cmd}' timed out waiting for output/prompt. Process {self.pid} still running. Entering interactive mode.")
            self.pending_interactive_context = { 'cmd': cmd }
            # Return minimal output collected so far, plus the interaction signal
            initial_output = "".join(output_buffer)
            # Clean the initial output
            lines = initial_output.split("\n")
            if lines and lines[0].strip() == cmd: lines = lines[1:] # Remove command echo
            cleaned_output = "\n".join(line for line in lines if line.strip()) # Remove empty lines

            # Return JSON response for interaction
            response_data = {
                'status': 'requires_interaction', 
                'output': self._strip_control_sequences(cleaned_output), # Return stripped initial output
                'message': 'Command is waiting. Use /cmd with "input_str" to view output or send input. Use /cmd with a new "cmd" to cancel and run a new command.'
            }
            return json.dumps(response_data) # Return JSON string directly
        # --- End Interaction Handling ---

        # If we got here, the command either completed or returned to prompt quickly
        self.pending_interactive_context = None # Ensure no pending state

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
        
        final_output = "\n".join(line for line in lines if line.strip()) # Filter empty lines
        
        # Return JSON response for completion
        response_data = {
            'status': 'completed', 
            'output': self._strip_control_sequences(final_output)
        }
        return json.dumps(response_data) # Return JSON string directly
        # --- EXECUTE LOGIC END ---


    def cleanup(self):
        self.pending_interactive_context = None # Clear any pending state on cleanup
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
                cls.shell is None
                or (current_time - cls.shell.last_used) > cls.SHELL_IDLE_TIMEOUT
            ):
                if cls.shell is not None:
                    print("[Info] Cleaning up idle shell")
                    cls.shell.cleanup()
                cls.shell = Shell(secure_mode=cls.secure_mode)
            return cls.shell
        except Exception as e:
            print(f"[Error] Failed to get shell: {e}")
            # If there was an error, try to clean up and create a new shell
            if cls.shell is not None:
                try:
                    cls.shell.cleanup()
                except:
                    pass
            cls.shell = Shell(secure_mode=cls.secure_mode)
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
    
                    # Send input if provided
                    if input_str:
                        print(f"[Debug] Sending input to interactive command: {input_str[:50]}...")
                        try:
                            os.write(shell.master_fd, (input_str + '\n').encode())
                        except OSError as e:
                            # Handle cases where the process might have died unexpectedly
                            print(f"[Warning] Failed to write input: {e}")
                            # Try to recover by checking process status
                            try:
                                pid, _ = os.waitpid(shell.pid, os.WNOHANG)
                                if pid == shell.pid:
                                    shell.pending_interactive_context = None
                                    raise ValueError(f"Process terminated unexpectedly before input could be sent.")
                            except OSError:
                                shell.pending_interactive_context = None
                                raise ValueError(f"Process seems to have terminated.")
                            # If we get here, the process is still alive but write failed
                            # Try to recover by sending a Ctrl+C and clearing the interactive state
                            try:
                                os.write(shell.master_fd, "\x03".encode()) # Send Ctrl+C
                                shell.pending_interactive_context = None
                                raise ValueError("Interactive session reset due to I/O error")
                            except:
                                # If that also fails, we're in trouble
                                shell.pending_interactive_context = None
                                raise ValueError("Interactive session terminated due to unrecoverable I/O error")
    
                    # Read output (use a slightly longer timeout than execute loop)
                    output_buffer = []
                    prompt_detected = False
                    process_terminated = False
                    
                    # Try to read output for up to 1 second
                    for _ in range(10): 
                        try:
                            chunk = shell._read_output(0.1)
                            if chunk:
                                output_buffer.append(chunk)
                                # Check for prompt in the accumulated output
                                current_output = "".join(output_buffer)
                                if shell._is_prompt(current_output):
                                    prompt_detected = True
                                    print(f"[Debug] Interactive prompt detected: {current_output[-30:].strip()}")
                                    break # Stop reading if prompt is seen
                        except Exception as e:
                            print(f"[Warning] Error reading output: {e}")
                            break
                            
                        # Check if the process is still running
                        try:
                            pid, status = os.waitpid(shell.pid, os.WNOHANG)
                            if pid == shell.pid:
                                process_terminated = True
                                print(f"[Info] Shell process {shell.pid} terminated.")
                                break
                        except OSError:
                            # Process already reaped or gone
                            process_terminated = True
                            print(f"[Info] Shell process {shell.pid} already terminated.")
                            break
                        
                        # If no output and process not terminated, wait a bit more
                        if not chunk:
                            time.sleep(0.1) # Small delay before next check
    
                    result = "".join(output_buffer)
                    
                    # Clean the result by removing the prompt if present
                    lines = result.split("\n")
                    if lines and shell._is_prompt(lines[-1]):
                        lines.pop()  # Remove the prompt line
                        
                    cleaned_output = shell._strip_control_sequences("\n".join(lines))
    
                    # Decide response based on state
                    if process_terminated or prompt_detected:
                        print(f"[Info] Interactive session completed.")
                        shell.pending_interactive_context = None # Clear the pending state
                        response_data = {
                            'status': 'completed',
                            'output': self._truncate_response(cleaned_output) # Truncate here
                        }
                    else:
                        # Still running, waiting for more input or processing
                        response_data = {
                            'status': 'pending_output',
                            'output': self._truncate_response(cleaned_output), # Truncate here
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

        if command == "view":
            if os.path.isfile(abs_path):
                # Handle view_range if specified
                view_range = data.get("view_range")
                if view_range:
                    # Validate view_range is an array of 2 integers
                    if (
                        not isinstance(view_range, list)
                        or len(view_range) != 2
                        or not all(isinstance(x, int) for x in view_range)
                    ):
                        raise ValueError("view_range must be an array of 2 integers")

                    # Validate start line is positive
                    if view_range[0] < 1:
                        raise ValueError("view_range start line must be >= 1")

                    # Validate end line is >= start line
                    if view_range[1] < view_range[0]:
                        raise ValueError("view_range end line must be >= start line")

                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if view_range:
                    lines = content.splitlines()
                    start = max(0, view_range[0] - 1)  # Convert to 0-based index
                    end = min(len(lines), view_range[1])
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
            return "Text inserted successfully"

        elif command == "undo_edit":
            if not os.path.exists(abs_path):
                raise FileNotFoundError(f"File not found: {path}")
                
            # Check if we need confirmation in secure mode
            if not self.confirm_destructive_operation(f"Undo edit to file: {abs_path}"):
                return "Operation aborted by user"

            backup_path = self._get_backup_path(abs_path)
            if not os.path.exists(backup_path):
                raise ValueError("No previous version available to undo")

            # Restore the backup
            with open(backup_path, "r", encoding="utf-8") as src:
                with open(abs_path, "w", encoding="utf-8") as dst:
                    dst.write(src.read())

            # Remove the backup after restoring
            os.remove(backup_path)
            return "Successfully reverted to previous version"

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
                    abs_filepath = filepath
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
    args = parser.parse_args()
    
    # Set secure mode based on command line argument
    ShellHandler.secure_mode = args.secure
    
    if args.secure:
        print(f'{COLOR_RED}Starting server in SECURE MODE - commands will require confirmation{COLOR_RESET}')
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    def cleanup_and_exit(signum, frame):
        print("\nCleaning up...")
        ShellHandler.cleanup_backups()
        print("Force quitting...")
        os._exit(0)

    # Replace the old signal_handler with our new cleanup_and_exit
    signal.signal(signal.SIGINT, cleanup_and_exit)
    signal.signal(signal.SIGTERM, cleanup_and_exit)

    server_address = ("", args.port)
    httpd = HTTPServer(server_address, ShellHandler)
    print(f"Starting server on port {args.port}...")

    try:
        httpd.serve_forever()
    except:
        cleanup_and_exit(None, None)  # Clean up on any exception

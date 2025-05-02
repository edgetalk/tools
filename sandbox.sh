#!/bin/bash

# Detect platform
platform=$(uname -s)

if [ "$platform" = "Darwin" ]; then
    # macOS - use sandbox-exec
    
    # Capture TMPDIR value for sandbox config
    TMPDIR=${TMPDIR:-/var/folders}
    
    cat > config.sb << EOF
(version 1)
(allow default)

;; Deny all file write operations by default
(deny file-write*)

;; Allow write access to the current directory and all its subdirectories
(allow file-write* (regex #"^$(pwd)(/|$)"))
(allow file-write* (regex #"^$(pwd)/.edits_backup(/|$)"))

;; Allow PTY operations
(allow file-write* (regex #"^/dev/ptmx(/|$)"))
(allow file-write* (regex #"^/dev/pts(/|$)"))
(allow file-write* (regex #"^/dev/pty(/|$)"))
(allow file-write* (regex #"^/dev/ttys(/|$)"))

;; Allow write access to temporary locations that many programs require
(allow file-write* (literal "/dev/null"))
(allow file-write* (literal "/dev/dtracehelper"))
(allow file-write* (regex #"^/dev/tty"))
(allow file-write* (subpath "/private/var/tmp"))
(allow file-write* (subpath "/private/tmp"))
(allow file-write* (subpath "/tmp"))
(allow file-write* (subpath "/private/var/folders"))
(allow file-write* (subpath "/var/folders"))
EOF

    sandbox-exec -f config.sb "$@"
    rm -f config.sb

elif [ "$platform" = "Linux" ]; then
    # Linux - use firejail
    
    # Capture TMPDIR value for firejail config
    TMPDIR=${TMPDIR:-/tmp}
    
    firejail --noprofile \
         --read-only=/ \
         --read-write="$(pwd)" \
         --read-write="$(pwd)/.edits_backup" \
         --read-write=/dev \
         --read-write=/tmp \
         --read-write=/var/tmp \
         --read-write="$TMPDIR" \
         --seccomp \
         "$@"
else
    echo "Unsupported platform: $platform"
    exit 1
fi

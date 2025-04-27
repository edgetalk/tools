#!/bin/bash

# Detect platform
platform=$(uname -s)

if [ "$platform" = "Darwin" ]; then
    # macOS - use sandbox-exec
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
(allow file-write*
    (literal "/dev/null")
    (literal "/dev/dtracehelper")
    (regex #"^/dev/tty")
    (regex #"^/private/var/tmp(/|$)")
    (regex #"^/var/folders/.*")
    (regex #"^/var/folders/_0/.*(/|$)")
    (regex #"^/var/folders/_0/.*T/rust.*"))
EOF

    sandbox-exec -f config.sb "$@"
    rm -f config.sb

elif [ "$platform" = "Linux" ]; then
    # Linux - use firejail
    firejail --noprofile \
         --read-only=/ \
         --read-write="$(pwd)" \
         --read-write="$(pwd)/.edits_backup" \
         --read-write=/dev \
         --read-write=/tmp \
         --read-write=/var/tmp \
         --whitelist=/var/folders \
         --seccomp \
         "$@"
else
    echo "Unsupported platform: $platform"
    exit 1
fi

# shell_server.py docker image
# build like: docker build -t shell-server .
# run like: docker run -p 6666:6666 -v /path/to/your/local/folder:/data shell-server
# For building with Shards: docker build --build-arg BUILD_SHARDS=true -t shell-server .

# Use slim Python image for smaller footprint while maintaining functionality
FROM python:3.12-slim AS base

# Set up Rust environment variables
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH

# ARG for optional Shards building
ARG BUILD_SHARDS=false

# Install essential tools and development utilities (non-interactive)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    bash \
    git \
    curl \
    wget \
    procps \
    net-tools \
    iputils-ping \
    nmap \
    traceroute \
    dnsutils \
    iproute2 \
    netcat-openbsd \
    gcc \
    g++ \
    clang \
    ninja-build \
    cmake \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path \
    && chmod -R a+w $RUSTUP_HOME $CARGO_HOME \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# just a way to invalidate the cache
RUN echo "7"

# Optional Shards build process
RUN if [ "$BUILD_SHARDS" = "true" ] ; then \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    build-essential \
    libclang-dev \
    protobuf-compiler \
    xorg-dev \
    libdbus-1-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean; \
    fi

# Setup Rust toolchain for Shards
RUN if [ "$BUILD_SHARDS" = "true" ] ; then \
    rustup default nightly && \
    rustup update nightly && \
    rustup target add wasm32-unknown-unknown --toolchain nightly; \
    fi

# Clone and prepare Shards
RUN if [ "$BUILD_SHARDS" = "true" ] ; then \
    git clone --depth 1 --shallow-submodules https://github.com/fragcolor-xyz/shards.git /shards && \
    cd /shards && \
    sh update.sh && \
    ./bootstrap; \
    fi

# Build and install Shards
RUN if [ "$BUILD_SHARDS" = "true" ] ; then \
    cd /shards && \
    mkdir -p build && \
    cd build && \
    cmake -GNinja -DCMAKE_BUILD_TYPE=Release .. && \
    ninja shards && \
    cp shards /usr/local/bin/ && \
    cd /; \
    fi

# Set working directory
WORKDIR /app

# Copy only the required script
COPY shell_server.py .

# Create volume mountpoint
VOLUME ["/data"]

# Setup git configuration to use token from environment
ENV GITHUB_TOKEN=""
ENV GITHUB_USER=""
# Configure git to use the token for HTTPS (if GITHUB_USER is empty, it still works fine)
RUN git config --global url."https://\${GITHUB_USER:+\${GITHUB_USER}:}\${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/" && \
    git config --global user.name "Kaz" && \
    git config --global user.email "kaz@fragcolor.xyz"

# Expose the port used by the server
EXPOSE 6666

# Run the server
CMD ["python", "shell_server.py"]

# Child Image 1: Stripped down image for running python script
FROM python:3.12-slim AS stripped

# Install only essential runtime packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    bash \
    git \
    curl \
    procps \
    net-tools \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set working directory
WORKDIR /app

# Copy only the required script and shards binary from the base image
COPY --from=base /app/shell_server.py .
COPY --from=base /usr/local/bin/shards /usr/local/bin/shards

# Create volume mountpoint
VOLUME ["/data"]

# Setup git configuration to use token from environment
ENV GITHUB_TOKEN=""
ENV GITHUB_USER=""
# Configure git to use the token for HTTPS
RUN git config --global url."https://\${GITHUB_USER:+\${GITHUB_USER}:}\${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/" && \
    git config --global user.name "Kaz" && \
    git config --global user.email "kaz@fragcolor.xyz"

# Expose the port used by the server
EXPOSE 6666

# Run the server
CMD ["python", "shell_server.py"]

# Child Image 2: Shards backup with cargo cache and shards folder
FROM base AS shards-backup
ARG BUILD_SHARDS=true

# This stage assumes Shards was built in the base image
# Create archives of cargo cache and shards folder
RUN mkdir -p /backup && \
    # Archive cargo cache
    if [ -d "/usr/local/cargo" ]; then \
        tar -czf /backup/cargo-cache.tar.gz -C /usr/local cargo; \
    fi && \
    # Modify the base image's cleanup to preserve the shards folder for this stage only
    if [ "$BUILD_SHARDS" = "true" ] && [ ! -d "/shards" ]; then \
        echo "Error: Shards directory not found. Make sure BUILD_SHARDS=true in the base image and the directory isn't removed." >&2; \
        exit 1; \
    fi && \
    # Archive shards folder without build files if it exists
    if [ -d "/shards" ]; then \
        find /shards -type d -name "build" -exec rm -rf {} + 2>/dev/null || true && \
        find /shards -type d -name "target" -exec rm -rf {} + 2>/dev/null || true && \
        tar -czf /backup/shards-repo.tar.gz -C / shards; \
    fi && \
    # Download LibreSSL and Boost archives
    wget -q https://develop.fragcolor.com/libressl-3.9.2.tar.gz -O /backup/libressl-3.9.2.tar.gz && \
    wget -q https://develop.fragcolor.com/boost-1.87.0.7z -O /backup/boost-1.87.0.7z

VOLUME ["/backup"]
CMD ["sh", "-c", "echo 'Shards backup image created with archives in /backup' && tail -f /dev/null"]

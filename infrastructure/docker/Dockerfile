# shell_server.py docker image
# build like: docker build -t shell-server .
# run like: docker run -p 6666:6666 -v /path/to/your/local/folder:/data shell-server
# For building with Shards: docker build --build-arg BUILD_SHARDS=true -t shell-server .

# Use slim Python image for smaller footprint while maintaining functionality
FROM python:3.12-slim

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
RUN echo "2"

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
    cd / && \
    rm -rf /shards; \
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

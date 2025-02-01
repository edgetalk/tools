# shell_server.py docker image
# build like: docker build -t shell-server .
# run like: docker run -p 6666:6666 -v /path/to/your/local/folder:/data shell-server

# Use slim Python image for smaller footprint while maintaining functionality
FROM python:3.12-slim

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
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

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

FROM ubuntu:22.04

ARG AGENTSH_REPO=canyonroad/agentsh
ARG AGENTSH_TAG=v0.9.8
ARG DEB_ARCH=amd64

# Install base dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        bash \
        git \
        sudo \
        libseccomp2 \
        fuse3 \
    && rm -rf /var/lib/apt/lists/*

# Download and install agentsh
RUN set -eux; \
    version="${AGENTSH_TAG#v}"; \
    deb="agentsh_${version}_linux_${DEB_ARCH}.deb"; \
    url="https://github.com/${AGENTSH_REPO}/releases/download/${AGENTSH_TAG}/${deb}"; \
    echo "Downloading: ${url}"; \
    curl -fsSL -L "${url}" -o /tmp/agentsh.deb; \
    dpkg -i /tmp/agentsh.deb; \
    rm -f /tmp/agentsh.deb; \
    agentsh --version

# Create agentsh directories
RUN mkdir -p /etc/agentsh/policies \
    /var/lib/agentsh/quarantine \
    /var/lib/agentsh/sessions \
    /var/log/agentsh && \
    chmod 755 /etc/agentsh /etc/agentsh/policies && \
    chmod 755 /var/lib/agentsh /var/lib/agentsh/quarantine /var/lib/agentsh/sessions && \
    chmod 755 /var/log/agentsh

# Copy the agent sandbox policy as the default policy
COPY default.yaml /etc/agentsh/policies/default.yaml

# Copy custom config with seccomp enabled for command interception
COPY config.yaml /etc/agentsh/config.yaml

# Create a non-root user for Daytona (BEFORE shim install to avoid agentsh interception)
RUN useradd -m -s /bin/bash daytona && \
    echo "daytona ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers && \
    chown -R daytona:daytona /var/lib/agentsh /var/log/agentsh

# Install the shell shim LAST - replaces /bin/bash with agentsh interceptor
# All RUN commands after this will go through agentsh
RUN agentsh shim install-shell \
    --root / \
    --shim /usr/bin/agentsh-shell-shim \
    --bash \
    --i-understand-this-modifies-the-host

# Configure agentsh for runtime
ENV AGENTSH_SERVER=http://127.0.0.1:18080

USER daytona
WORKDIR /home/daytona

# Daytona expects a long-running process; it will add sleep infinity if needed
CMD ["/bin/bash"]

# Claude-in-a-Box: Sandboxed Claude Code with task server
FROM node:20-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    python3 \
    python3-pip \
    python3-venv \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code
RUN npm install -g @anthropic-ai/claude-code

# Create non-root user for safety
RUN useradd -m -s /bin/bash claude
WORKDIR /home/claude

# Copy protocol files
COPY --chown=claude:claude *.py ./
COPY --chown=claude:claude requirements.txt ./

# Install Python dependencies
RUN pip3 install --break-system-packages -r requirements.txt

# Create workspace directory (will be mounted)
RUN mkdir -p /workspace && chown claude:claude /workspace

# Switch to non-root user
USER claude

# Environment
ENV ANTHROPIC_API_KEY=""
ENV LINEAR_API_KEY=""
ENV WORKSPACE_DIR=/workspace
ENV AGENT_PORT=8080

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python3", "server.py"]

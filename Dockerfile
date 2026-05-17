FROM python:3.12-slim

ARG INSTALL_LATEX=true

WORKDIR /app

# Install system dependencies — pdflatex and required LaTeX packages
# Skip if INSTALL_LATEX=false for faster dev builds
RUN if [ "$INSTALL_LATEX" = "true" ]; then \
        apt-get update && \
        apt-get install -y --no-install-recommends \
            texlive-latex-base \
            texlive-fonts-recommended \
            texlive-fonts-extra \
            texlive-latex-extra \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# Install Python dependencies
COPY requirements.txt requirements-optional.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-optional.txt

# Copy server entrypoint and pipeline scripts
COPY server.py ./
COPY .claude/skills/tailor-resume/scripts/ ./.claude/skills/tailor-resume/scripts/
COPY .claude/skills/tailor-resume/templates/ ./.claude/skills/tailor-resume/templates/

EXPOSE 8080
# Healthcheck: verify the MCP server is bound and accepting connections.
# Uses a plain TCP connect instead of an HTTP request because the
# streamable-http MCP transport at /mcp may respond with non-2xx codes to
# bare GET requests (it expects session-aware POST/SSE clients). On Fly.io
# the platform-level healthcheck in fly.toml is what actually gates traffic.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(3); s.connect(('localhost', 8080)); s.close()" || exit 1

CMD ["python", "server.py"]

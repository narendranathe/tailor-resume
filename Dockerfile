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
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "server.py"]

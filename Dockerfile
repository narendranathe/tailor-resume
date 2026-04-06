FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt requirements-optional.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-optional.txt

# Copy server entrypoint and pipeline scripts
COPY server.py ./
COPY .claude/skills/tailor-resume/scripts/ ./.claude/skills/tailor-resume/scripts/
COPY .claude/skills/tailor-resume/templates/ ./.claude/skills/tailor-resume/templates/

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "server.py"]

PYTHON      := python
PYTEST      := $(PYTHON) -m pytest
RUFF        := $(PYTHON) -m ruff
SCRIPTS     := .claude/skills/tailor-resume/scripts
TEMPLATES   := .claude/skills/tailor-resume/templates
FIXTURES    := fixtures
OUT         := out

MCP_SERVER  := $(SCRIPTS)/mcp_server.py
MCP_GLOBAL  := $(HOME)/.claude/.mcp.json

.PHONY: setup setup-all install-global demo test test-cov lint render mcp-serve mcp-install-global sync-global serve clean help

help:
	@echo "Available targets:"
	@echo "  install-global       Copy skill + register MCP + install optional deps (run once after clone)"
	@echo "  setup                Install core dev dependencies (pytest, ruff)"
	@echo "  setup-all            Install core + optional deps (pinecone, openai, mcp)"
	@echo "  demo                 Run the full pipeline on sample fixtures -> $(OUT)/resume.tex"
	@echo "  test                 Run the test suite"
	@echo "  test-cov             Run tests with coverage report"
	@echo "  lint                 Run ruff on scripts and tests"
	@echo "  render               Compile $(OUT)/resume.tex to PDF (requires pdflatex)"
	@echo "  mcp-serve            Start the MCP server over stdio (for manual testing)"
	@echo "  mcp-install-global   Register MCP server in ~/.claude/.mcp.json"
	@echo "  clean                Remove generated output files"

setup:
	$(PYTHON) -m pip install -r requirements.txt

setup-all:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-optional.txt

demo: $(OUT)
	$(PYTHON) $(SCRIPTS)/profile_extractor.py \
		--input $(FIXTURES)/sample_blob.txt \
		--format blob \
		--output $(OUT)/profile.json
	$(PYTHON) $(SCRIPTS)/jd_gap_analyzer.py \
		--jd $(FIXTURES)/sample_jd.txt \
		--profile $(OUT)/profile.json
	$(PYTHON) $(SCRIPTS)/latex_renderer.py \
		--profile $(OUT)/profile.json \
		--template $(TEMPLATES)/resume_template.tex \
		--output $(OUT)/resume.tex \
		--name "Jane Smith" \
		--email "jane@example.com" \
		--linkedin "https://linkedin.com/in/jane-smith" \
		--portfolio "https://janesmith.dev"
	@echo ""
	@echo "Resume written to $(OUT)/resume.tex"
	@echo "Run 'make render' to compile to PDF (requires pdflatex), or upload to Overleaf."

test:
	$(PYTEST) tests/ -v

test-cov:
	$(PYTEST) tests/ --cov=$(SCRIPTS) --cov-report=term-missing

lint:
	$(RUFF) check $(SCRIPTS)/ tests/

$(OUT):
	mkdir -p $(OUT)

render: $(OUT)/resume.tex
	pdflatex -output-directory $(OUT) $(OUT)/resume.tex
	@echo "PDF written to $(OUT)/resume.pdf"

mcp-serve:
	@echo "Starting tailor-resume MCP server (stdio). Press Ctrl+C to stop."
	$(PYTHON) $(MCP_SERVER)

install-global: mcp-install-global
	@echo "Copying skill to $(HOME)/.claude/skills/ ..."
	mkdir -p $(HOME)/.claude/skills
	cp -r .claude/skills/tailor-resume $(HOME)/.claude/skills/tailor-resume
	@echo "Installing optional deps (pinecone, openai, mcp) ..."
	$(PYTHON) -m pip install -r requirements-optional.txt
	@echo ""
	@echo "[OK] tailor-resume is now available globally."
	@echo "     Restart Claude Code to activate /tailor-resume and the MCP tools."

mcp-install-global:
	$(PYTHON) scripts/install_mcp_global.py

sync-global:
	$(PYTHON) scripts/sync_global.py

serve:
	$(PYTHON) $(SCRIPTS)/api_server.py

clean:
	rm -rf $(OUT)/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true

PYTHON      := python
PYTEST      := $(PYTHON) -m pytest
RUFF        := $(PYTHON) -m ruff
SCRIPTS     := .claude/skills/tailor-resume/scripts
TEMPLATES   := .claude/skills/tailor-resume/templates
FIXTURES    := fixtures
OUT         := out

.PHONY: setup setup-all demo test lint render clean help

help:
	@echo "Available targets:"
	@echo "  setup      Install core dev dependencies (pytest, ruff)"
	@echo "  setup-all  Install core + optional deps (pinecone, openai)"
	@echo "  demo       Run the full pipeline on sample fixtures -> $(OUT)/resume.tex"
	@echo "  test       Run the test suite"
	@echo "  lint       Run ruff on scripts and tests"
	@echo "  render     Compile $(OUT)/resume.tex to PDF (requires pdflatex)"
	@echo "  clean      Remove generated output files"

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

clean:
	rm -rf $(OUT)/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true

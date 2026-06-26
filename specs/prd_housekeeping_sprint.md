## Problem

`_YEAR_FIRST_RE` and `_BARE_DATE_RE` are compiled with `re.compile()` inside `_parse_education_oneliner` in `plain_parser.py` (lines 161 and 183). Every invocation of that function allocates two fresh compiled regex objects, burning CPU on each education line parsed — particularly costly in batch runs (e.g., 50+ candidate profiles processed by the pipeline in a single session). Although CPython's `re` module caches up to 512 patterns, the cache is keyed on the raw pattern string plus flags and is a simple LRU; under load the cache can evict entries, making the cost unpredictable. Moving these constants to module level eliminates the allocation entirely, aligns with the codebase's existing convention (all other regexes in the file are module-level constants), and makes it trivial to audit which patterns the module owns.

## Users

| Persona | Resume source / entry point | Impact |
|---|---|---|
| Job seeker (CLI) | Runs `python scripts/cli.py --artifact resume.pdf:pdf` | Education block parsed on every run; redundant compiles add latency invisibly |
| Developer / contributor | Reads `plain_parser.py` to understand parsing logic | Inline compiles obscure which regexes are module-owned constants vs. local temporaries |
| CI / test runner | Executes `pytest tests/test_plain_parser_jake_template.py` in a loop | 100+ test invocations call the function; constant re-allocation inflates wall time |

## User Stories

- As a **job seeker running the CLI**, I want education parsing to be fast and deterministic so that the pipeline completes quickly and I can iterate on my resume without waiting.
- As a **contributor reading `plain_parser.py`**, I want all module-owned regex constants declared at the top of the file so that I can understand the full set of patterns without hunting inside function bodies.
- As a **CI engineer**, I want no redundant `re.compile()` calls inside hot-path functions so that test suite wall time is minimized and profiling results are clean.

## Flow

```
BEFORE
──────
_parse_education_oneliner(line) called
  │
  ├─ re.compile(_YEAR_FIRST_RE pattern, re.IGNORECASE)   ← allocates new object
  │
  ├─ [use _YEAR_FIRST_RE.match(s)]
  │
  └─ re.compile(_BARE_DATE_RE pattern, re.IGNORECASE)    ← allocates new object
       └─ [use _BARE_DATE_RE.match(s)]

AFTER
─────
Module load (once)
  ├─ _YEAR_FIRST_RE = re.compile(...)   ← compiled once, module-level constant
  └─ _BARE_DATE_RE  = re.compile(...)   ← compiled once, module-level constant

_parse_education_oneliner(line) called
  ├─ [use _YEAR_FIRST_RE.match(s)]      ← references module constant, zero allocation
  └─ [use _BARE_DATE_RE.match(s)]       ← references module constant, zero allocation
```

## Modules

| File | Line range | Exact change description |
|---|---|---|
| `.claude/skills/tailor-resume/scripts/parsers/plain_parser.py` | 127–138 (after `_INST_KEYWORD_RE`) | Add two new module-level constants: `_YEAR_FIRST_RE` and `_BARE_DATE_RE` |
| `.claude/skills/tailor-resume/scripts/parsers/plain_parser.py` | 161–164 (inside `_parse_education_oneliner`) | Remove the `_YEAR_FIRST_RE = re.compile(...)` assignment; leave the `.match(s)` call referencing the module constant |
| `.claude/skills/tailor-resume/scripts/parsers/plain_parser.py` | 183–188 (inside `_parse_education_oneliner`) | Remove the `_BARE_DATE_RE = re.compile(...)` assignment; leave the `.match(s)` call referencing the module constant |

## Acceptance Criteria

- [ ] `_YEAR_FIRST_RE` is declared at module level (before any function definition) in `plain_parser.py`
- [ ] `_BARE_DATE_RE` is declared at module level (before any function definition) in `plain_parser.py`
- [ ] Neither constant is re-assigned or re-compiled inside `_parse_education_oneliner`
- [ ] `python -m pytest tests/test_plain_parser_jake_template.py -q` exits with 0 failures
- [ ] `python -c "from parsers.plain_parser import _YEAR_FIRST_RE, _BARE_DATE_RE; print('OK')"` succeeds (constants are importable)

## Metrics

| Metric | Before | After |
|---|---|---|
| `re.compile()` calls per education line parse | 2 | 0 |
| Module-level regex constants in `plain_parser.py` | 9 | 11 |
| Inline `re.compile()` calls inside functions | 2 | 0 |
| `test_plain_parser_jake_template.py` pass count | all pass | all pass (no regression) |
| Risk of pattern cache eviction under load | non-zero | eliminated |

# Resume Reference (Tech / Data Engineering 2026)

## What recruiters want in the first scan
1. Role-fit evidence in the top 1/3 of page
2. Quantified outcomes and clear ownership scope
3. Reliability and delivery signals (tests, CI/CD, incident reduction)
4. Architecture judgment (cost/perf trade-offs, open standards)
5. Career progression and increasing scope

---

## STAR Method — Hard Requirement on Every Bullet

Every bullet must satisfy ALL of:
1. **Action** — begins with or contains a strong action verb (built, reduced, migrated, architected…)
2. **Result** — contains at least one measurable outcome (%, $, time, count, before/after)
3. **≤20 words** — the 2-line limit; bullets over this are truncated automatically at render time

Situation and Task context is embedded in the role header above the bullet (resume compression).
The renderer enforces ≤20 words via `truncate_to_limit()` — but write compliant bullets before render.

## Compressed STAR form (≤20 words)
`[Action verb] [system/what] by [method], [metric result].`

**Compliant (≤20 words):**
- Reduced batch runtime 73% (30 min → 8 min) by migrating to CDC upserts, cutting costs 67%. *(17 words)*
- Built Pytest suite for 12 pipelines via GitHub Actions, reducing defects 40%. *(13 words)*

**Non-compliant (fix before render):**
- Optimized pipelines for better performance. *(no result metric)*
- Worked on improving data quality across the enterprise data team over multiple quarters. *(no action verb, no metric, >20 words)*

---

## 2026 Signal Framework: 4 Phases

### Phase 1 — Software Craftsmanship
A 2026 data engineer is a **software engineer for data**. The bar is robust, modular, testable code.

**Show on resume:**
- Modular Python packages with clear interfaces
- Unit/integration tests that prevented regressions (quantify)
- CI/CD pipelines for data code (GitHub Actions, Azure DevOps)
- Containerized pipeline runtime for dev-to-prod consistency
- Resilience for schema drift and API failures

**Power keywords:** unit tests, integration tests, CI/CD, Docker, idempotency, retries, dead-letter queues, incident reduction, audit readiness

### Phase 2 — AI Infrastructure & Semantic Layers
AI projects fail mostly due to **data engineering**, not math. Show you build the plumbing:

**Show on resume:**
- Governed semantic layer / metrics definitions (single source of truth)
- Business logic standardized in warehouse/lakehouse
- Workload isolation (training vs. BI) to protect production
- Schemas and datasets that are LLM-ready and retrieval-ready

**Power keywords:** semantic layer, governed metrics, workload isolation, schema drift, backward compatibility, LLM-ready, RAG, data contracts

### Phase 3 — Architecture & FinOps
Storage is cheap; **compute is expensive**. Defend your trade-offs.

**Show on resume:**
- Architecture decisions tied to latency, freshness, and cost
- Concrete cost wins ($X/month saved, X% compute reduction)
- Open table formats (Delta Lake, Iceberg) over lock-in choices
- Governance: access controls, lineage, documentation

**Power keywords:** FinOps, TCO, partitioning, pruning, compaction, Delta Lake, Iceberg, RBAC, lineage, shuffle reduction, broadcast joins

### Phase 4 — Orchestration & Data Quality
Cron jobs are not acceptable. Bad data triggers automated AI actions with real consequences.

**Show on resume:**
- Production orchestration ownership (Airflow/Dagster/Databricks Jobs), not hobby DAGs
- Backfill strategy, idempotency, and defined SLAs
- Data quality checks and incident prevention metrics
- Observability: freshness, volume, null rates, anomaly detection

**Power keywords:** DAGs, dependency management, backfills, SLAs/SLOs, data contracts, schema enforcement, Great Expectations, Monte Carlo, observability, anomaly detection

---

## Bullet scoring rubric (score 0–2 each)
| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Action clarity | Vague verb | Generic verb | Strong specific verb |
| Business impact | None | Implied | Explicit outcome |
| Metric specificity | No numbers | 1 number | Before/after or % + abs |
| Technical depth | Tool name only | Method described | Trade-off explained |
| JD relevance | Off-topic | Tangential | Direct MQ match |
| Concision (hard limit) | >20 words — truncated at render | 16–20 words | ≤15 words |

**Target: 9+ / 12** for the 3–5 most important bullets.

**ATS score formula (4-component):**
```
40% keyword overlap  +  30% category coverage  +  20% bullet quality (STAR + metrics)  +  10% seniority signal
```

---

## ATS guidance
- Use standard section headings: Summary, Experience, Projects, Skills, Education, Certifications
- Avoid: tables for core content, text boxes, headers/footers with key info, images
- Keywords appear naturally in bullets — never as comma-separated lists in the skills section alone
- Consistent date formatting: `Mon. YYYY – Mon. YYYY`
- Standard/recognized job titles — align internal titles to market equivalents

---

## Resume philosophy
> "Your ability to get a job should be based on your experiences and capabilities, not your resume writing skills."

- **Single page always** — forces prioritization; recruiters don't read page 2
- **Evidence reframing, not understatement** — never fabricate, but always push real evidence to its strongest defensible angle. Saying "improved performance" when you can confirm "~40% reduction" is an ATS penalty, not integrity. Use confirmed ranges; claim ownership where accurate; convert passive participation into active impact where true.
- **Tailor per application** — keywords, summary, and bullet order change per JD
- **Progression matters** — show increasing scope, not just changing companies
- **Quantify everything possible** — if a range is defensible, use it. If no metric exists, ask: "what was the baseline and the end state?" Every bullet without a number is a missed ATS signal.

---

## Follow-up metric prompts (use when numbers are missing)
- "What was the baseline and the end state?" (e.g., 30 min → 8 min)
- "What was the scale?" (rows/day, users, dollars, latency, incidents)
- "What was your ownership scope?" (solo, team lead, cross-functional)
- "Was there a measured business outcome?" (support tickets, revenue, uptime)
- "Over what time period?"

---

## Red flags to remove
- Vague claims without metrics: "optimized pipelines", "improved performance"
- Tool lists masquerading as achievements: "Used Airflow, Spark, and Kafka"
- AI buzzwords without platform fundamentals: "built AI solution" with no data quality/governance context
- Employment gaps left unexplained
- Internal jargon that recruiters won't recognize

---

## Resume checklist
- [ ] 2–4 bullets demonstrating testing + CI/CD
- [ ] 2+ bullets showing reliability (schema drift, incident reduction, SLAs)
- [ ] 1–2 bullets with architecture trade-off + cost reasoning
- [ ] Spark claims backed by performance concept examples (if Spark listed)
- [ ] Orchestration ownership in production context (not just "used Airflow")
- [ ] Data quality and observability implementation shown
- [ ] Semantic layer / metrics consistency evidence (for AI-adjacent roles)
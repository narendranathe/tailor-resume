# Resume Reference (Tech / Data Engineering 2026)

## What recruiters want in the first scan
1. Role-fit evidence in the top 1/3 of page
2. Quantified outcomes and clear ownership scope
3. Reliability and delivery signals (tests, CI/CD, incident reduction)
4. Architecture judgment (cost/perf trade-offs, open standards)
5. Career progression and increasing scope

---

## High-value bullet pattern
`Accomplished X as measured by Y by doing Z`

**Good:**
- Reduced batch runtime by 73% (30 min → 8 min) by migrating full-table reloads to CDC merge upserts, cutting compute costs by ~67%.
- Built Pytest suite + GitHub Actions CI for 12 pipelines, reducing production data defects by 40% and eliminating recurring on-call pages.

**Weak (remove):**
- Optimized pipelines for better performance.
- Worked on improving data quality.

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
| Concision | >25 words | 20–25 words | <20 words |

**Target: 9+ / 12** for the 3–5 most important bullets.

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
- **Factual integrity** — never fabricate; reframe real evidence with stronger framing
- **Tailor per application** — keywords, summary, and bullet order change per JD
- **Progression matters** — show increasing scope, not just changing companies
- **Quantify everything possible** — if you can't measure it, question whether it belongs

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
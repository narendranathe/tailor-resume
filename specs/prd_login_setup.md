# PRD: Login + First-Run Setup Wizard

> Product-Driven Development pipeline: **Problem → Users → Stories → Flow → Modules → Acceptance → Metrics**.
> All architectural decisions made here will be appended to `specs/README.md` upon implementation.

---

## Overview

The current web app (`web_app/frontend/src/App.jsx`) drops a freshly signed-in user straight onto the tailoring form (`TailorForm.jsx`) with no orientation, no stored profile, and no target context. Every tailor run starts from a blank slate — the user must re-paste a JD, re-upload a resume, and re-type contact info on every visit.

This PRD specifies a **first-run setup wizard** that runs once after sign-up. It collects the three pieces of state that unlock fast subsequent runs:

1. **Target Roles** — what jobs the user is applying for (drives JD-matching heuristics and Signal Category weighting).
2. **Target Companies** — a tracked watchlist (drives vault organisation, future job-board ingestion, and analytics).
3. **Resume Vault** — the base Profile uploaded once and reused across every tailor run.

The wizard is gated on a `setup_completed_at` flag in `user_profiles`. Returning users skip it. Users who quit mid-wizard resume where they left off.

## Problem Statement

Three concrete friction points exist today:

1. **Cold-start every visit.** The tailoring form (`TailorForm.jsx`) has no concept of a stored Profile. Users re-upload their resume on every single tailor. The `/api/v1/profile` endpoint already exists (`web_app/backend/app/routes/profile.py:35`) but is never invoked from the UI.
2. **No targeting context.** The pipeline scores every JD identically — there is no notion of "the kind of role I want" or "the companies I care about." Power users (Narendra's own use case) cycle through 3-5 target roles and 20-30 companies. Without persistent targeting, they retype the same context on every run.
3. **No onboarding.** A new user lands on the tailor form with no idea what an Artifact, a Profile, or a JD even means in this product. Drop-off in the first 60 seconds is the highest-cost failure mode.

Cost of inaction: every returning user repeats 90 seconds of paste-and-upload work; new users churn before producing their first tailored resume.

## Target Users (Primary)

| Persona | Description | Setup Priority |
|---|---|---|
| **First-time job seeker (Narendra dog-fooding)** | Has a base resume, knows their target role, has a shortlist of 10-30 companies. | High — designs the wizard. |
| **Career switcher** | Multiple base resumes (old role + new role). Wants to track which version is "the EM resume" vs "the senior IC resume." | Medium — wizard supports multiple roles. |
| **Casual returner** | Signed up 3 months ago, forgot the product exists, signs in expecting their setup to still be there. | Medium — must be resumable + editable. |

## User Stories

1. **As a brand-new user**, when I sign up, I see a one-page welcome explaining what the product does and what I'll set up next, so I don't bounce on confusion.
2. **As a brand-new user**, after the welcome, I'm walked through 3 setup steps (Roles → Companies → Resume Vault) with a clear progress indicator, so I know how much is left.
3. **As a user selecting target roles**, I can pick from a curated list (Software Engineer, Senior Software Engineer, Staff SWE, Data Engineer, ML Engineer, Product Manager, etc.) OR type a free-form role, so I'm not blocked by an incomplete picklist.
4. **As a user selecting target companies**, I can pick from a curated list of the top ~200 tech companies, OR type/paste any company name, with autocomplete from my prior entries, so I can build a 20-company watchlist in under 60 seconds.
5. **As a user setting up my resume vault**, I can upload one base resume (PDF, DOCX, LaTeX, Markdown, or plain text), preview the parsed Profile, edit any field that looks wrong, and confirm — so the parsed Profile becomes the source of truth for all future tailor runs.
6. **As a user who quit mid-wizard**, when I sign back in, I land on the step I last completed, not the welcome page, so I don't redo finished work.
7. **As a returning user with setup done**, signing in takes me straight to the tailor form (current behaviour), so the wizard adds zero friction after first run.
8. **As a returning user**, I can re-enter the wizard from the user menu ("Edit setup") to change my target roles, add companies, or replace my base resume.

## Detailed Flow

### Step 0 — Welcome / Instruction Page (`/setup/welcome`)

Shown immediately after first Clerk sign-up (detected by absence of `setup_completed_at` on the user_profiles row).

**Content:**
- Headline: "Let's get you set up — takes about 2 minutes."
- Three numbered cards explaining what each step collects and why:
  1. **Target roles** → so we know which JD signals matter most to you.
  2. **Companies to track** → your watchlist; lets us organise saved resumes by employer.
  3. **Resume vault** → upload once, reuse forever. Powers every tailor run.
- A single primary CTA: **"Start setup"** → navigates to `/setup/roles`.
- Secondary text-link: **"Skip for now"** → navigates to the tailor form; sets `setup_skipped_at` but not `setup_completed_at`. The wizard remains reachable from the user menu.

### Step 1 — Target Roles (`/setup/roles`)

**UI:**
- Multi-select chip grid of ~20 canonical role titles (`CANONICAL_ROLES` constant — see Module 2 below).
- A "+ Add custom role" affordance that opens a small inline text input.
- Minimum 1 role required to advance. Maximum 5 (prevents noise; covers the career-switcher case).
- Selected roles render as removable chips.
- Progress bar: **Step 1 of 3**.
- Buttons: **Back** (to welcome), **Continue** (disabled until ≥1 role selected).

**Data shape persisted:**
```json
{ "target_roles": ["Senior Data Engineer", "Staff Data Engineer", "ML Platform Engineer"] }
```

### Step 2 — Target Companies (`/setup/companies`)

**UI:**
- Hybrid picker + free-text entry.
- Searchable typeahead input — types match against the canonical list (`CANONICAL_COMPANIES`) AND any previously-entered custom companies.
- Below the input: chips for already-added companies. Click chip ✕ to remove.
- Quick-add presets: **"FAANG"**, **"Top fintech"**, **"AI labs"** — clicking adds a curated bundle (user can edit after).
- Limits: ≥1 company required to advance. Soft warning above 50 ("That's a lot — usually 10–25 yields better focus") but not blocking.
- Progress bar: **Step 2 of 3**.

**Data shape persisted:**
```json
{
  "target_companies": [
    {"name": "Stripe", "source": "canonical"},
    {"name": "Plaid", "source": "canonical"},
    {"name": "Acme Robotics", "source": "custom"}
  ]
}
```

The `source` field is metadata only; both types behave identically in the watchlist. It exists so we can later improve the canonical list based on what users actually type.

### Step 3 — Resume Vault Setup (`/setup/resume`)

**UI flow:**

1. **Upload zone** — drag-drop or click. Accepts `.pdf`, `.docx`, `.tex`, `.md`, `.txt`. Single file (the base resume).
   - Alternative: **"Paste resume text instead"** opens a textarea for blob input.
2. **Parsing feedback** — spinner with "Parsing your resume…" while `POST /api/v1/profile` runs.
3. **Parsed Profile preview** — read-only collapsible card showing:
   - Header (name, email, phone, links) — flagged if any field is missing.
   - Roles (count + first 2 collapsed)
   - Projects (count)
   - Skills (top 10)
   - Education (count)
   - **Parse quality indicator**: green check if all sections found and Header complete; amber warning if any Header field is missing or roles = 0.
4. **Edit mode** — clicking any section opens an inline editor. Edits persist via `PATCH /api/v1/profile` (new endpoint — see Module 4).
5. **Confirmation** — **"This looks right, finish setup"** button finalises:
   - Sets `setup_completed_at = now()` on `user_profiles`.
   - Optionally pushes the base resume to the Vault as `is_base_template = true` (gated on `GITHUB_VAULT_TOKEN`).
   - Redirects to the tailor form with a one-time toast: "Setup complete — your resume vault is ready."

**Progress bar:** **Step 3 of 3**.

### Returning User Flow

- If `setup_completed_at IS NOT NULL` → skip wizard entirely; route directly to tailor form.
- If `setup_completed_at IS NULL AND setup_skipped_at IS NOT NULL` → still skip wizard; show a dismissible banner at the top of the tailor form: "Finish your setup to enable one-click tailoring → [Resume setup]".
- If `setup_completed_at IS NULL AND setup_skipped_at IS NULL` → enter wizard at the step indicated by `setup_progress_step` (defaults to `welcome`).

### Edit Setup (Post-First-Run)

User menu adds an **"Edit setup"** item that re-opens the wizard at Step 1 with all current values pre-populated. Each step gets a **"Save & exit"** button so users can update only one section without re-walking the entire flow.

## Acceptance Criteria

### MVP (must ship together)

- [ ] Migration `003_user_setup.sql` adds columns to `user_profiles`: `target_roles JSONB`, `target_companies JSONB`, `setup_completed_at TIMESTAMPTZ`, `setup_skipped_at TIMESTAMPTZ`, `setup_progress_step TEXT`. RLS policies extended to cover new columns.
- [ ] Backend route `web_app/backend/app/routes/setup.py` exposes:
  - `GET /api/v1/setup/state` → returns `{ target_roles, target_companies, setup_completed_at, setup_skipped_at, setup_progress_step }`.
  - `PUT /api/v1/setup/roles` → upsert roles list (max 5).
  - `PUT /api/v1/setup/companies` → upsert companies list (max 100, soft-warned above 50).
  - `POST /api/v1/setup/complete` → sets `setup_completed_at = now()`.
  - `POST /api/v1/setup/skip` → sets `setup_skipped_at = now()` (no completion).
- [ ] Profile endpoint extended: `PATCH /api/v1/profile` accepts partial JSON edits to the stored Profile (used by Step 3 inline editor).
- [ ] Frontend route guard in `App.jsx`: signed-in users land on `/setup/welcome` if `setup_completed_at` is null AND `setup_skipped_at` is null. Otherwise current tailor form.
- [ ] React components added under `web_app/frontend/src/components/setup/`:
  - `WelcomePage.jsx`
  - `RolesStep.jsx`
  - `CompaniesStep.jsx`
  - `ResumeStep.jsx`
  - `SetupShell.jsx` — wrapper with progress bar + back/continue logic.
- [ ] Canonical role + company lists committed at `web_app/frontend/src/constants/setupCatalog.js`. Lists are static JS arrays for MVP (no backend lookup).
- [ ] User menu has an **"Edit setup"** action that re-enters the wizard with current state.
- [ ] Resume Step "skip-after-upload" path: if the user uploads but doesn't edit, the parsed Profile is stored as-is and `setup_completed_at` is still written (no forced editing).
- [ ] All five new components have unit tests with React Testing Library; backend `setup.py` has pytest coverage ≥80%.
- [ ] No PII in any committed file. Canonical company list contains only well-known public company names.

### Non-MVP (deferred, listed for traceability)

- [ ] Multi-resume vault (multiple base templates tagged by target role). Currently single base resume only.
- [ ] Company autocomplete backed by an external API (e.g., Crunchbase). MVP uses static list.
- [ ] Role recommendations based on parsed Profile (e.g., infer "Data Engineer" from skills). MVP requires explicit user pick.
- [ ] LinkedIn import as an alternative to file upload in Step 3.

## Non-Functional Requirements

- **Performance:**
  - Welcome page TTI ≤ 500ms (no API calls).
  - Roles/Companies step responses ≤ 200ms (writes to Supabase only).
  - Resume Step parsing ≤ 5s for typical PDFs (Tier 0 with `ANTHROPIC_API_KEY`); ≤ 2s for DOCX/LaTeX/plain.
- **Resumability:** Closing the browser mid-wizard never loses progress. `setup_progress_step` is updated on every `Continue` click.
- **Accessibility:** All form controls keyboard-navigable. Progress bar has `aria-valuenow`. Step headings are `<h1>` for screen-reader landmarks.
- **Privacy:** Target roles + companies are user-private (RLS-protected). Never logged. Never sent to Claude or any third party in MVP scope.
- **Compatibility:** The wizard does not break existing users who already have a Profile row but no setup fields — they're treated as "setup_skipped" (banner shown, full app functional).

## Technical Context

### Existing code touched

- `web_app/frontend/src/App.jsx:24` — add route guard before rendering `TailorForm`.
- `web_app/backend/app/routes/profile.py` — add `PATCH /profile` for inline edits.
- `web_app/backend/app/db/supabase.py` — extend `SupabaseProfileStore` with `get_setup_state()`, `update_setup_state()`, plus the SQLite-fallback equivalents per the storage fallback pattern documented in `CLAUDE.md`.
- `web_app/backend/app/main.py` — register `setup` router.

### New files

```
web_app/backend/app/routes/setup.py
migrations/003_user_setup.sql
web_app/frontend/src/components/setup/SetupShell.jsx
web_app/frontend/src/components/setup/WelcomePage.jsx
web_app/frontend/src/components/setup/RolesStep.jsx
web_app/frontend/src/components/setup/CompaniesStep.jsx
web_app/frontend/src/components/setup/ResumeStep.jsx
web_app/frontend/src/constants/setupCatalog.js
tests/test_setup_routes.py
web_app/frontend/src/components/setup/__tests__/*.test.jsx
```

### Patterns to follow

- **Clerk auth via `get_current_user`** dependency on every new route (mirrors `profile.py:36`).
- **Supabase + SQLite fallback** in the store layer (per `CLAUDE.md` "Storage fallback pattern"). Setup state lives on the same `user_profiles` row, not a new table — keeps the fallback trivial.
- **React state shape** mirrors the API: a single `useSetupState()` hook calls `GET /api/v1/setup/state` once on mount and exposes `{ state, updateRoles, updateCompanies, complete, skip }`.
- **Step progression** is data-driven by `setup_progress_step` — frontend never trusts client-side step state alone.

## Module Breakdown

### Module 1 — `migrations/003_user_setup.sql`
- **Responsibility:** Extend `user_profiles` with setup columns + RLS.
- **Interface:** SQL applied manually (per migration convention in `migrations/`).
- **Complexity:** S.

### Module 2 — `web_app/frontend/src/constants/setupCatalog.js`
- **Responsibility:** Export `CANONICAL_ROLES` (~20 entries) and `CANONICAL_COMPANIES` (~200 entries) + `COMPANY_BUNDLES` (`FAANG`, `Top fintech`, `AI labs`).
- **Interface:** Static JS module; no I/O.
- **Complexity:** S.

### Module 3 — `web_app/backend/app/routes/setup.py`
- **Responsibility:** REST endpoints listed in MVP acceptance criteria above.
- **Interface:** FastAPI router mounted at `/api/v1/setup`.
- **Dependencies:** `app.auth.get_current_user`, `app.db.supabase.get_profile_store` (extended).
- **Complexity:** M.

### Module 4 — `PATCH /api/v1/profile`
- **Responsibility:** Apply a partial Profile patch (deep-merge into stored JSONB).
- **Interface:** Adds one handler in `profile.py`; accepts `{ patch: <partial Profile dict> }`.
- **Dependencies:** Same store as existing `POST /profile`.
- **Complexity:** S.

### Module 5 — `SetupShell.jsx` + 4 step components
- **Responsibility:** Render the 4-step wizard with progress bar, route guards, and per-step persistence.
- **Interface:** Mounted by `App.jsx` route guard; reads/writes via `useSetupState()` hook.
- **Dependencies:** Clerk `useUser`, the new `/setup/*` endpoints, the existing `/profile` upload endpoint.
- **Complexity:** L.

### Module 6 — `useSetupState()` hook
- **Responsibility:** Single source of truth for setup state on the client.
- **Interface:** `const { state, updateRoles, updateCompanies, uploadResume, patchProfile, complete, skip, loading, error } = useSetupState()`.
- **Dependencies:** `fetch` + Clerk token.
- **Complexity:** M.

## Dependency Graph

```
003_user_setup.sql
        │
        ▼
db/supabase.py (extended)
        │
        ▼
routes/setup.py ──────► routes/profile.py (PATCH added)
        │                       │
        └───────────┬───────────┘
                    ▼
            useSetupState() hook
                    │
   ┌────────────────┼────────────────┐
   ▼                ▼                ▼
RolesStep      CompaniesStep    ResumeStep
   │                │                │
   └─── SetupShell ◄┴────────────────┘
                    │
                    ▼
              App.jsx guard
```

Build order: migration → backend store extension → backend routes → frontend hook → step components → shell → App.jsx integration → tests.

## Out of Scope

- Multiple base resumes per user (one-resume-per-user MVP only).
- LinkedIn OAuth import in Step 3.
- Company logos in the picker (cost: licensing + asset CDN).
- Role-specific JD-matching weights wired into the gap analyzer. The wizard *collects* roles in MVP; using them to weight `Signal Categories` is a separate PRD.
- Email reminders to finish setup for skipped users.
- Server-rendered welcome page (SSR). MVP is client-rendered like the rest of the SPA.

## Open Questions

1. **Canonical company list source** — bootstrap from the Forbes 500 + YC top 100 lists, or hand-curate ~200 names? Recommend hand-curate for MVP to keep latency and licensing trivial.
2. **Skip vs Required** — should "Skip for now" be allowed at all? Strict argument: forcing setup raises completion to ~100%. Pragmatic argument: skipping reduces sign-up regret. Recommend allowing skip with a persistent banner.
3. **Edit-setup re-entry** — should it require typing the password again (Clerk re-auth)? MVP: no. Setup data is not sensitive enough to warrant re-auth friction.
4. **Vault push at end of Step 3** — auto-push as `is_base_template = true`, or wait until first tailor? Recommend auto-push: the vault is the persistent record, and the user has explicitly confirmed the parse.
5. **Inline edit fields in Step 3** — full Profile editor or just Header (name/contact)? Recommend Header-only for MVP; Profile section editing is a separate (larger) feature.
6. **Bundles** — should `FAANG`, `Top fintech`, `AI labs` be hard-coded in the JS catalog or fetched from the backend? Hard-coded is simpler for MVP and lets product iterate on the lists without a deploy gate.

## Success Metrics (post-launch, week 1)

| Metric | Target |
|---|---|
| % of new sign-ups that finish all 3 steps | ≥ 70% |
| Median time to complete the wizard | ≤ 3 minutes |
| % of returning users (week 2+) who use stored Profile vs. re-uploading | ≥ 80% |
| Drop-off rate on the welcome page | ≤ 10% |
| Drop-off rate on the resume upload step | ≤ 20% |
| Tickets/support requests related to "where do I edit my setup" | ≤ 2 in week 1 |

## Definition of Done

- [ ] All MVP acceptance criteria checked.
- [ ] `migrations/003_user_setup.sql` applied successfully in Supabase staging.
- [ ] Backend tests pass: `python -m pytest tests/test_setup_routes.py -v` ≥ 80% coverage.
- [ ] Frontend tests pass: `npm test` in `web_app/frontend` for all new components.
- [ ] Manual smoke test: sign up as a brand-new Clerk user, complete the wizard end-to-end, verify the next sign-in skips the wizard and the stored Profile auto-populates the tailor form.
- [ ] `specs/README.md` updated with an entry under a new date heading documenting the final decisions on the open questions above.
- [ ] `UBIQUITOUS_LANGUAGE.md` extended with the new terms: **Setup Wizard**, **Target Role**, **Target Company**, **Resume Vault Setup**, **setup_completed_at**, **setup_progress_step**.
- [ ] No PII committed. RLS verified by attempting cross-user reads in staging.
- [ ] CI green on Python 3.11 + 3.12.

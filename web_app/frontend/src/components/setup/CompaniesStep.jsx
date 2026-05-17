// web_app/frontend/src/components/setup/CompaniesStep.jsx
// Step 2 — target companies (picker + free-text + bundles) — Epic #91 (M5).

import React from 'react'
import { CANONICAL_COMPANIES, COMPANY_BUNDLES } from '../../constants/setupCatalog.js'

const MAX_COMPANIES = 100
const SOFT_WARN = 50

export default function CompaniesStep({ initialCompanies = [], onBack, onContinue }) {
  const [companies, setCompanies] = React.useState(() =>
    (initialCompanies || []).map((c) => (typeof c === 'string' ? { name: c, source: 'custom' } : c)),
  )
  const [query, setQuery] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)

  const names = new Set(companies.map((c) => c.name.toLowerCase()))

  const suggestions = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    return CANONICAL_COMPANIES.filter(
      (c) => c.toLowerCase().includes(q) && !names.has(c.toLowerCase()),
    ).slice(0, 8)
  }, [query, companies])

  const add = (name, source) => {
    const cleaned = name.trim()
    if (!cleaned) return
    if (names.has(cleaned.toLowerCase())) return
    if (companies.length >= MAX_COMPANIES) return
    setCompanies((prev) => [...prev, { name: cleaned, source }])
    setQuery('')
  }

  const addCustomFromInput = () => {
    if (!query.trim()) return
    const canonical = CANONICAL_COMPANIES.find(
      (c) => c.toLowerCase() === query.trim().toLowerCase(),
    )
    add(query, canonical ? 'canonical' : 'custom')
  }

  const remove = (name) =>
    setCompanies((prev) => prev.filter((c) => c.name !== name))

  const addBundle = (bundleName) => {
    const bundle = COMPANY_BUNDLES[bundleName] || []
    bundle.forEach((name) => add(name, 'canonical'))
  }

  const canContinue = companies.length >= 1 && !submitting
  const softWarning =
    companies.length >= SOFT_WARN
      ? `That's a lot — usually 10–25 yields better focus.`
      : null

  const submit = async () => {
    setSubmitting(true)
    try {
      await onContinue(companies)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="setup-step setup-companies">
      <h2>Which companies are you tracking?</h2>
      <p>Pick from the list, paste in your own, or load a bundle.</p>

      <div className="bundle-row">
        {Object.keys(COMPANY_BUNDLES).map((b) => (
          <button key={b} type="button" className="btn-ghost" onClick={() => addBundle(b)}>
            + {b}
          </button>
        ))}
      </div>

      <div className="company-search">
        <input
          type="text"
          placeholder="Type a company name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && addCustomFromInput()}
        />
        <button type="button" disabled={!query.trim()} onClick={addCustomFromInput}>
          + Add
        </button>
      </div>

      {suggestions.length > 0 && (
        <ul className="company-suggestions">
          {suggestions.map((s) => (
            <li key={s}>
              <button type="button" onClick={() => add(s, 'canonical')}>{s}</button>
            </li>
          ))}
        </ul>
      )}

      <div className="selected-chips">
        {companies.map((c) => (
          <span key={c.name} className={`chip chip-removable chip-${c.source}`}>
            {c.name}
            <button onClick={() => remove(c.name)} aria-label={`Remove ${c.name}`}>×</button>
          </span>
        ))}
      </div>

      {softWarning && <div className="soft-warning">{softWarning}</div>}

      <footer className="setup-actions">
        <button className="btn-ghost" onClick={onBack}>Back</button>
        <button className="btn-primary" disabled={!canContinue} onClick={submit}>
          Continue
        </button>
      </footer>
    </section>
  )
}

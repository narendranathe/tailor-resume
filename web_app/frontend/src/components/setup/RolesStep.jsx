// web_app/frontend/src/components/setup/RolesStep.jsx
// Step 1 — target roles (chips + custom add) — Epic #91 (M5).

import React from 'react'
import { CANONICAL_ROLES } from '../../constants/setupCatalog.js'

const MAX_ROLES = 5

export default function RolesStep({ initialRoles = [], onBack, onContinue }) {
  const [selected, setSelected] = React.useState(initialRoles)
  const [customRole, setCustomRole] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)

  const toggle = (role) => {
    setSelected((prev) =>
      prev.includes(role)
        ? prev.filter((r) => r !== role)
        : prev.length < MAX_ROLES
          ? [...prev, role]
          : prev,
    )
  }

  const addCustom = () => {
    const cleaned = customRole.trim()
    if (!cleaned || selected.includes(cleaned) || selected.length >= MAX_ROLES) return
    setSelected((prev) => [...prev, cleaned])
    setCustomRole('')
  }

  const canContinue = selected.length >= 1 && !submitting

  const submit = async () => {
    setSubmitting(true)
    try {
      await onContinue(selected)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="setup-step setup-roles">
      <h2>Which roles are you targeting?</h2>
      <p>Pick up to {MAX_ROLES}. We'll weight matching signals accordingly.</p>

      <div className="chip-grid">
        {CANONICAL_ROLES.map((role) => (
          <button
            key={role}
            type="button"
            className={`chip ${selected.includes(role) ? 'chip-selected' : ''}`}
            onClick={() => toggle(role)}
            aria-pressed={selected.includes(role)}
          >
            {role}
          </button>
        ))}
      </div>

      <div className="custom-row">
        <input
          type="text"
          placeholder="Add a custom role…"
          value={customRole}
          onChange={(e) => setCustomRole(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && addCustom()}
        />
        <button type="button" onClick={addCustom} disabled={!customRole.trim()}>
          + Add
        </button>
      </div>

      {selected.length > 0 && (
        <div className="selected-chips">
          <span className="selected-label">Selected:</span>
          {selected.map((r) => (
            <span key={r} className="chip chip-removable">
              {r}
              <button onClick={() => toggle(r)} aria-label={`Remove ${r}`}>×</button>
            </span>
          ))}
        </div>
      )}

      <footer className="setup-actions">
        <button className="btn-ghost" onClick={onBack}>Back</button>
        <button className="btn-primary" disabled={!canContinue} onClick={submit}>
          Continue
        </button>
      </footer>
    </section>
  )
}

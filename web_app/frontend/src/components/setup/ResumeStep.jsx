// web_app/frontend/src/components/setup/ResumeStep.jsx
// Step 3 — base resume upload + parse preview + confirm — Epic #91 (M5).

import React from 'react'

export default function ResumeStep({ onBack, onUpload, onPatch, onFinish }) {
  const [file, setFile] = React.useState(null)
  const [profile, setProfile] = React.useState(null)
  const [editingHeader, setEditingHeader] = React.useState(false)
  const [headerDraft, setHeaderDraft] = React.useState({})
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState(null)

  const upload = async () => {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const data = await onUpload(file)
      setProfile(data.profile)
      setHeaderDraft(data.profile.header || {})
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  const saveHeader = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await onPatch({ header: headerDraft })
      setProfile(data.profile)
      setEditingHeader(false)
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  const finish = async () => {
    setBusy(true)
    setError(null)
    try {
      await onFinish()
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="setup-step setup-resume">
      <h2>Upload your base resume</h2>
      <p>PDF, DOCX, LaTeX, Markdown, or plain text. We'll parse it once; you reuse it forever.</p>

      <div className="upload-zone">
        <input
          type="file"
          accept=".pdf,.docx,.tex,.md,.txt"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        <button className="btn-primary" disabled={!file || busy} onClick={upload}>
          {busy ? 'Parsing…' : 'Upload & parse'}
        </button>
      </div>

      {error && <div className="setup-error">{error}</div>}

      {profile && (
        <div className="profile-preview">
          <PreviewHeader
            header={profile.header}
            editing={editingHeader}
            draft={headerDraft}
            onDraftChange={setHeaderDraft}
            onEdit={() => setEditingHeader(true)}
            onCancel={() => {
              setHeaderDraft(profile.header || {})
              setEditingHeader(false)
            }}
            onSave={saveHeader}
            busy={busy}
          />
          <PreviewStats profile={profile} />
        </div>
      )}

      <footer className="setup-actions">
        <button className="btn-ghost" onClick={onBack}>Back</button>
        <button className="btn-primary" disabled={!profile || busy} onClick={finish}>
          This looks right — finish setup
        </button>
      </footer>
    </section>
  )
}

function PreviewHeader({ header = {}, editing, draft, onDraftChange, onEdit, onCancel, onSave, busy }) {
  if (!editing) {
    const missing = !header.name || !header.email
    return (
      <div className="preview-card">
        <header>
          <strong>Header</strong>
          <button className="btn-link" onClick={onEdit}>Edit</button>
        </header>
        <ul>
          <li>Name: {header.name || <em>missing</em>}</li>
          <li>Email: {header.email || <em>missing</em>}</li>
          <li>Phone: {header.phone || <em>—</em>}</li>
          <li>LinkedIn: {header.linkedin || <em>—</em>}</li>
        </ul>
        <span className={`quality-badge ${missing ? 'amber' : 'green'}`}>
          {missing ? 'Some fields missing' : 'Looks good'}
        </span>
      </div>
    )
  }
  return (
    <div className="preview-card preview-editing">
      <header><strong>Edit header</strong></header>
      <label>Name <input value={draft.name || ''} onChange={(e) => onDraftChange({ ...draft, name: e.target.value })} /></label>
      <label>Email <input value={draft.email || ''} onChange={(e) => onDraftChange({ ...draft, email: e.target.value })} /></label>
      <label>Phone <input value={draft.phone || ''} onChange={(e) => onDraftChange({ ...draft, phone: e.target.value })} /></label>
      <label>LinkedIn <input value={draft.linkedin || ''} onChange={(e) => onDraftChange({ ...draft, linkedin: e.target.value })} /></label>
      <div className="setup-actions">
        <button className="btn-ghost" onClick={onCancel} disabled={busy}>Cancel</button>
        <button className="btn-primary" onClick={onSave} disabled={busy}>Save header</button>
      </div>
    </div>
  )
}

function PreviewStats({ profile }) {
  const counts = {
    Roles: (profile.experience || []).length,
    Projects: (profile.projects || []).length,
    Skills: (profile.skills || []).length,
    Education: (profile.education || []).length,
  }
  return (
    <div className="preview-card preview-stats">
      <header><strong>Parsed sections</strong></header>
      <ul>
        {Object.entries(counts).map(([k, v]) => (
          <li key={k}>{k}: {v}</li>
        ))}
      </ul>
    </div>
  )
}

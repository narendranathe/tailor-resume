import React, { useState } from 'react'
import { useAuth } from '@clerk/clerk-react'

const API_URL = import.meta.env.VITE_API_URL || ''

const FORMAT_OPTIONS = [
  { value: 'blob', label: 'Plain text / blob' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'latex', label: 'LaTeX' },
  { value: 'linkedin', label: 'LinkedIn export' },
]

export default function TailorForm({ onResult, onLoading, onError, loading }) {
  const { getToken } = useAuth()
  const [jd, setJd] = useState('')
  const [resumeText, setResumeText] = useState('')
  const [format, setFormat] = useState('blob')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!jd.trim() || !resumeText.trim()) return

    onLoading(true)
    onError(null)
    onResult(null)

    try {
      const token = await getToken()

      // Determine file extension from format
      const extMap = { blob: 'txt', markdown: 'md', latex: 'tex', linkedin: 'txt' }
      const ext = extMap[format] || 'txt'
      const filename = `resume.${ext}`

      // Prepend name/email header if provided
      let artifact = resumeText
      if (name || email) {
        const header = [name && `Name: ${name}`, email && `Email: ${email}`]
          .filter(Boolean)
          .join('\n')
        artifact = `${header}\n\n${resumeText}`
      }

      const formData = new FormData()
      formData.append('jd_text', jd)
      formData.append(
        'artifact',
        new Blob([artifact], { type: 'text/plain' }),
        filename
      )

      const res = await fetch(`${API_URL}/api/v1/resume/tailor`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(detail.detail || `HTTP ${res.status}`)
      }

      const data = await res.json()
      onResult(data)
    } catch (err) {
      onError(err.message || 'Something went wrong')
    } finally {
      onLoading(false)
    }
  }

  return (
    <form className="tailor-form" onSubmit={handleSubmit}>
      <h2 className="pane-title">Your Inputs</h2>

      <div className="form-row">
        <div className="form-group half">
          <label htmlFor="name">Full Name</label>
          <input
            id="name"
            type="text"
            placeholder="Jane Smith"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="form-group half">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            placeholder="jane@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
      </div>

      <div className="form-group">
        <label htmlFor="format">Resume Format</label>
        <select
          id="format"
          value={format}
          onChange={(e) => setFormat(e.target.value)}
        >
          {FORMAT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label htmlFor="resume">
          Resume / Profile Blob
          <span className="label-hint">Paste your resume text, LinkedIn export, or LaTeX source</span>
        </label>
        <textarea
          id="resume"
          rows={12}
          placeholder="Paste your resume here..."
          value={resumeText}
          onChange={(e) => setResumeText(e.target.value)}
          required
        />
      </div>

      <div className="form-group">
        <label htmlFor="jd">
          Job Description
          <span className="label-hint">Paste the full job posting</span>
        </label>
        <textarea
          id="jd"
          rows={12}
          placeholder="Paste the job description here..."
          value={jd}
          onChange={(e) => setJd(e.target.value)}
          required
        />
      </div>

      <button
        type="submit"
        className="btn-primary"
        disabled={loading || !jd.trim() || !resumeText.trim()}
      >
        {loading ? (
          <>
            <span className="btn-spinner" /> Tailoring...
          </>
        ) : (
          'Tailor My Resume'
        )}
      </button>
    </form>
  )
}

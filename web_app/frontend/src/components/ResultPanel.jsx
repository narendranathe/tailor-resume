import React, { useMemo } from 'react'

// ATS color thresholds
function atsColor(score) {
  if (score >= 0.8) return '#22c55e'   // green
  if (score >= 0.6) return '#f59e0b'   // amber
  return '#ef4444'                      // red
}

function atsLabel(score) {
  if (score >= 0.8) return 'Strong Match'
  if (score >= 0.6) return 'Moderate Match'
  if (score >= 0.5) return 'Weak Match'
  return 'Poor Match'
}

/**
 * Parse gap_summary string into table rows.
 *
 * Expected format from pipeline:
 *   Missing: X, Y
 *   1. [HIGH] Category Name
 *      Missing: a, b, c
 *   2. [MEDIUM] Another Category
 *      Missing: d, e
 *
 * Returns: [{ priority, category, missing }]
 */
function parseGapSummary(raw) {
  if (!raw) return []
  const rows = []
  const lines = raw.split('\n')
  let current = null

  for (const line of lines) {
    // Match numbered category lines like: 1. [HIGH] Python Programming
    const categoryMatch = line.match(/^\s*\d+\.\s+\[(\w+)\]\s+(.+)/)
    if (categoryMatch) {
      if (current) rows.push(current)
      current = {
        priority: categoryMatch[1].toUpperCase(),
        category: categoryMatch[2].trim(),
        missing: '',
        coverage: null,
      }
      continue
    }

    // Match coverage lines like: Coverage: 40%
    const coverageMatch = line.match(/Coverage:\s*(\d+(?:\.\d+)?)\s*%/i)
    if (coverageMatch && current) {
      current.coverage = parseFloat(coverageMatch[1])
      continue
    }

    // Match missing skills lines like:   Missing: a, b, c
    const missingMatch = line.match(/^\s+Missing:\s+(.+)/i)
    if (missingMatch && current) {
      current.missing = missingMatch[1].trim()
      continue
    }
  }
  if (current) rows.push(current)
  return rows
}

function PriorityBadge({ priority }) {
  const colors = {
    HIGH: { bg: '#fef2f2', text: '#dc2626', border: '#fca5a5' },
    MEDIUM: { bg: '#fffbeb', text: '#d97706', border: '#fcd34d' },
    LOW: { bg: '#f0fdf4', text: '#16a34a', border: '#86efac' },
  }
  const style = colors[priority] || colors.LOW
  return (
    <span
      className="priority-badge"
      style={{ background: style.bg, color: style.text, borderColor: style.border }}
    >
      {priority}
    </span>
  )
}

function downloadBlob(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function handleDownloadTex(tex_b64) {
  const bytes = atob(tex_b64)
  downloadBlob(bytes, 'tailored_resume.tex', 'text/x-tex')
}

function handleDownloadReport(report) {
  downloadBlob(report, 'resume_report.txt', 'text/plain')
}

export default function ResultPanel({ result, loading, error }) {
  const gapRows = useMemo(() => parseGapSummary(result?.gap_summary), [result?.gap_summary])

  if (loading) {
    return (
      <div className="result-panel result-loading">
        <div className="spinner large" />
        <p>Analyzing your resume against the job description…</p>
        <p className="loading-hint">This usually takes 15–30 seconds.</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="result-panel result-error">
        <span className="error-icon">⚠</span>
        <h3>Something went wrong</h3>
        <p className="error-message">{error}</p>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="result-panel result-empty">
        <div className="empty-icon">📊</div>
        <h3>Results will appear here</h3>
        <p>Fill in the form on the left and click <strong>Tailor My Resume</strong>.</p>
      </div>
    )
  }

  const { ats_score, gap_summary, report, tex_b64 } = result
  const pct = Math.round(ats_score * 100)
  const color = atsColor(ats_score)
  const declined = ats_score < 0.5

  return (
    <div className="result-panel">
      <h2 className="pane-title">Results</h2>

      {/* ATS Score */}
      <div className="ats-card">
        <div className="ats-score" style={{ color }}>
          {pct}%
        </div>
        <div className="ats-label" style={{ color }}>{atsLabel(ats_score)}</div>
        <div className="ats-sublabel">ATS Match Score</div>
        <div
          className="ats-bar-track"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="ats-bar-fill"
            style={{ width: `${pct}%`, background: color }}
          />
        </div>
      </div>

      {/* Decline message */}
      {declined && (
        <div className="decline-banner">
          <strong>This role doesn't align with your profile.</strong>
          <p>
            Your resume scored below 50% against this job description. Consider
            targeting roles that better match your current skills, or invest time
            in building the missing competencies before applying.
          </p>
        </div>
      )}

      {/* Download buttons */}
      {!declined && (
        <div className="download-row">
          {tex_b64 ? (
            <button
              className="btn-download"
              onClick={() => handleDownloadTex(tex_b64)}
            >
              Download .tex
            </button>
          ) : (
            <button
              className="btn-download secondary"
              onClick={() => handleDownloadReport(report)}
            >
              Download Report
            </button>
          )}
        </div>
      )}

      {/* Gap Analysis Table */}
      {gapRows.length > 0 && (
        <div className="gap-section">
          <h3>Gap Analysis</h3>
          <table className="gap-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Coverage</th>
                <th>Priority</th>
                <th>Missing Skills</th>
              </tr>
            </thead>
            <tbody>
              {gapRows.map((row, i) => (
                <tr key={i} className={`gap-row priority-${row.priority.toLowerCase()}`}>
                  <td className="gap-category">{row.category}</td>
                  <td className="gap-coverage">
                    {row.coverage !== null ? (
                      <div className="mini-bar-wrap">
                        <div className="mini-bar-track">
                          <div
                            className="mini-bar-fill"
                            style={{
                              width: `${row.coverage}%`,
                              background: row.coverage >= 70 ? '#22c55e' : row.coverage >= 40 ? '#f59e0b' : '#ef4444',
                            }}
                          />
                        </div>
                        <span>{row.coverage}%</span>
                      </div>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    <PriorityBadge priority={row.priority} />
                  </td>
                  <td className="gap-missing">
                    {row.missing ? (
                      <span className="missing-tags">
                        {row.missing.split(',').map((s, j) => (
                          <span key={j} className="tag">{s.trim()}</span>
                        ))}
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Full report */}
      {report && (
        <div className="report-section">
          <h3>Full Report</h3>
          <pre className="report-text">{report}</pre>
        </div>
      )}
    </div>
  )
}

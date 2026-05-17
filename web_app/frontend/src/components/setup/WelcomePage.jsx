// web_app/frontend/src/components/setup/WelcomePage.jsx
// Step 0 — orientation and dual CTA (Start / Skip) — Epic #91 (M5).

import React from 'react'

export default function WelcomePage({ onStart, onSkip }) {
  return (
    <section className="setup-welcome">
      <h2>Let's get you set up — takes about 2 minutes.</h2>
      <p className="setup-lede">
        Three quick steps unlock one-click tailoring on every future visit.
      </p>

      <ol className="setup-cards">
        <li>
          <strong>1. Target roles</strong>
          <p>So we know which JD signals matter most to you.</p>
        </li>
        <li>
          <strong>2. Companies to track</strong>
          <p>Your watchlist. Saved resumes get organised by employer.</p>
        </li>
        <li>
          <strong>3. Resume vault</strong>
          <p>Upload once. Every tailor run reuses your base profile.</p>
        </li>
      </ol>

      <div className="setup-actions">
        <button className="btn-primary" onClick={onStart}>Start setup</button>
        <button className="btn-link" onClick={onSkip}>Skip for now</button>
      </div>
    </section>
  )
}

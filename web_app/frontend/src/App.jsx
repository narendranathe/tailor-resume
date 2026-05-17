import React, { useEffect, useState } from 'react'
import { useUser, useClerk, useAuth, SignIn } from '@clerk/clerk-react'
import TailorForm from './components/TailorForm.jsx'
import ResultPanel from './components/ResultPanel.jsx'
import SetupShell from './components/setup/SetupShell.jsx'
import './App.css'

const API_BASE = import.meta.env.VITE_API_URL || ''

function UserMenu({ onEditSetup }) {
  const { user } = useUser()
  const { signOut } = useClerk()
  return (
    <div className="user-menu">
      <span className="user-email">{user?.primaryEmailAddress?.emailAddress}</span>
      <button className="btn-ghost" onClick={onEditSetup}>Edit setup</button>
      <button className="btn-ghost" onClick={() => signOut()}>Sign out</button>
    </div>
  )
}

function SetupBanner({ onResume }) {
  return (
    <div className="setup-banner">
      <span>Finish your setup to enable one-click tailoring.</span>
      <button className="btn-link" onClick={onResume}>Resume setup</button>
    </div>
  )
}

export default function App() {
  const { isSignedIn, isLoaded } = useUser()
  const { getToken } = useAuth()

  const [setupState, setSetupState] = useState(null)
  const [setupLoading, setSetupLoading] = useState(true)
  const [forceWizard, setForceWizard] = useState(false)

  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Fetch wizard state on sign-in so we can decide the route.
  useEffect(() => {
    if (!isSignedIn) {
      setSetupLoading(false)
      return
    }
    let cancelled = false
    ;(async () => {
      setSetupLoading(true)
      try {
        const token = await getToken()
        const resp = await fetch(`${API_BASE}/api/v1/setup/state`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        const data = resp.ok ? await resp.json() : null
        if (!cancelled) setSetupState(data)
      } catch {
        if (!cancelled) setSetupState(null)
      } finally {
        if (!cancelled) setSetupLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isSignedIn, getToken, forceWizard])

  if (!isLoaded || (isSignedIn && setupLoading)) {
    return (
      <div className="app-loading">
        <div className="spinner" />
      </div>
    )
  }

  const setupCompleted = !!setupState?.setup_completed_at
  const setupSkipped = !!setupState?.setup_skipped_at
  const showWizard =
    isSignedIn && (forceWizard || (!setupCompleted && !setupSkipped))

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-brand">
          <span className="header-icon">✂</span>
          <h1>Tailor Resume</h1>
          <span className="header-tagline">AI-powered resume optimizer</span>
        </div>
        {isSignedIn && <UserMenu onEditSetup={() => setForceWizard(true)} />}
      </header>

      <main className="app-main">
        {!isSignedIn ? (
          <div className="auth-gate">
            <div className="auth-card">
              <h2>Sign in to get started</h2>
              <p>Tailor your resume to any job description in seconds.</p>
              <SignIn routing="hash" />
            </div>
          </div>
        ) : showWizard ? (
          <SetupShell
            onDone={() => {
              setForceWizard(false)
              setSetupState((prev) => ({
                ...(prev || {}),
                setup_completed_at: prev?.setup_completed_at || new Date().toISOString(),
              }))
            }}
          />
        ) : (
          <>
            {setupSkipped && !setupCompleted && (
              <SetupBanner onResume={() => setForceWizard(true)} />
            )}
            <div className="two-pane">
              <div className="pane pane-left">
                <TailorForm
                  onResult={setResult}
                  onLoading={setLoading}
                  onError={setError}
                  loading={loading}
                />
              </div>
              <div className="pane pane-right">
                <ResultPanel result={result} loading={loading} error={error} />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  )
}

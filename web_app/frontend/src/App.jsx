import React, { useState } from 'react'
import { useUser, useClerk, SignIn } from '@clerk/clerk-react'
import TailorForm from './components/TailorForm.jsx'
import ResultPanel from './components/ResultPanel.jsx'
import './App.css'

function UserMenu() {
  const { user } = useUser()
  const { signOut } = useClerk()
  return (
    <div className="user-menu">
      <span className="user-email">{user?.primaryEmailAddress?.emailAddress}</span>
      <button className="btn-ghost" onClick={() => signOut()}>Sign out</button>
    </div>
  )
}

export default function App() {
  const { isSignedIn, isLoaded } = useUser()
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  if (!isLoaded) {
    return (
      <div className="app-loading">
        <div className="spinner" />
      </div>
    )
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-brand">
          <span className="header-icon">✂</span>
          <h1>Tailor Resume</h1>
          <span className="header-tagline">AI-powered resume optimizer</span>
        </div>
        {isSignedIn && <UserMenu />}
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
        ) : (
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
        )}
      </main>
    </div>
  )
}

// web_app/frontend/src/components/setup/SetupShell.jsx
// Wizard shell with progress bar + step routing — Epic #91 (M5).

import React from 'react'
import { useSetupState } from './useSetupState.js'
import WelcomePage from './WelcomePage.jsx'
import RolesStep from './RolesStep.jsx'
import CompaniesStep from './CompaniesStep.jsx'
import ResumeStep from './ResumeStep.jsx'

const STEPS = ['welcome', 'roles', 'companies', 'resume']
const STEP_LABELS = {
  welcome: 'Welcome',
  roles: 'Target roles',
  companies: 'Companies',
  resume: 'Resume vault',
}

export default function SetupShell({ onDone }) {
  const setup = useSetupState()
  const [localStep, setLocalStep] = React.useState(null)

  if (setup.loading) {
    return (
      <div className="setup-shell setup-loading">
        <div className="spinner" />
      </div>
    )
  }

  const activeStep = localStep || setup.state.setup_progress_step || 'welcome'
  const stepIdx = Math.max(0, STEPS.indexOf(activeStep))

  function goTo(step) {
    setLocalStep(step)
  }

  return (
    <div className="setup-shell">
      <header className="setup-header">
        <h1>Set up your account</h1>
        <ProgressBar current={stepIdx} total={STEPS.length} />
      </header>

      {setup.error && <div className="setup-error">{setup.error}</div>}

      <main className="setup-body">
        {activeStep === 'welcome' && (
          <WelcomePage
            onStart={() => goTo('roles')}
            onSkip={async () => {
              await setup.skip()
              onDone?.()
            }}
          />
        )}
        {activeStep === 'roles' && (
          <RolesStep
            initialRoles={setup.state.target_roles}
            onBack={() => goTo('welcome')}
            onContinue={async (roles) => {
              await setup.updateRoles(roles)
              goTo('companies')
            }}
          />
        )}
        {activeStep === 'companies' && (
          <CompaniesStep
            initialCompanies={setup.state.target_companies}
            onBack={() => goTo('roles')}
            onContinue={async (companies) => {
              await setup.updateCompanies(companies)
              goTo('resume')
            }}
          />
        )}
        {activeStep === 'resume' && (
          <ResumeStep
            onBack={() => goTo('companies')}
            onUpload={setup.uploadResume}
            onPatch={setup.patchProfile}
            onFinish={async () => {
              await setup.complete()
              onDone?.()
            }}
          />
        )}
      </main>
    </div>
  )
}

function ProgressBar({ current, total }) {
  const pct = Math.min(100, Math.round(((current + 1) / total) * 100))
  return (
    <div className="setup-progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="setup-progress-bar" style={{ width: `${pct}%` }} />
      <span className="setup-progress-label">
        Step {current + 1} of {total} — {STEP_LABELS[STEPS[current]] || ''}
      </span>
    </div>
  )
}

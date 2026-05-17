// web_app/frontend/src/components/setup/useSetupState.js
// Single source of truth for the setup wizard on the client — Epic #91 (M6).

import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'

const API_BASE = import.meta.env.VITE_API_URL || ''

const DEFAULT_STATE = {
  user_id: '',
  target_roles: [],
  target_companies: [],
  setup_completed_at: null,
  setup_skipped_at: null,
  setup_progress_step: 'welcome',
}

export function useSetupState() {
  const { getToken } = useAuth()
  const [state, setState] = useState(DEFAULT_STATE)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const authedFetch = useCallback(
    async (path, opts = {}) => {
      const token = await getToken()
      const headers = { ...(opts.headers || {}) }
      if (token) headers['Authorization'] = `Bearer ${token}`
      if (opts.body && !(opts.body instanceof FormData)) {
        headers['Content-Type'] = headers['Content-Type'] || 'application/json'
      }
      const resp = await fetch(`${API_BASE}${path}`, { ...opts, headers })
      if (!resp.ok) {
        const detail = await resp.text().catch(() => resp.statusText)
        throw new Error(`${resp.status} ${detail}`)
      }
      if (resp.status === 204) return null
      return resp.json()
    },
    [getToken],
  )

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await authedFetch('/api/v1/setup/state')
      setState({ ...DEFAULT_STATE, ...data })
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setLoading(false)
    }
  }, [authedFetch])

  useEffect(() => {
    refresh()
  }, [refresh])

  const updateRoles = useCallback(
    async (roles) => {
      const data = await authedFetch('/api/v1/setup/roles', {
        method: 'PUT',
        body: JSON.stringify({ roles }),
      })
      await refresh()
      return data
    },
    [authedFetch, refresh],
  )

  const updateCompanies = useCallback(
    async (companies) => {
      const data = await authedFetch('/api/v1/setup/companies', {
        method: 'PUT',
        body: JSON.stringify({ companies }),
      })
      await refresh()
      return data
    },
    [authedFetch, refresh],
  )

  const uploadResume = useCallback(
    async (file) => {
      const fd = new FormData()
      fd.append('artifact', file)
      const data = await authedFetch('/api/v1/profile', { method: 'POST', body: fd })
      return data
    },
    [authedFetch],
  )

  const patchProfile = useCallback(
    async (patch) => {
      return authedFetch('/api/v1/profile', {
        method: 'PATCH',
        body: JSON.stringify({ patch }),
      })
    },
    [authedFetch],
  )

  const complete = useCallback(async () => {
    const data = await authedFetch('/api/v1/setup/complete', { method: 'POST' })
    await refresh()
    return data
  }, [authedFetch, refresh])

  const skip = useCallback(async () => {
    const data = await authedFetch('/api/v1/setup/skip', { method: 'POST' })
    await refresh()
    return data
  }, [authedFetch, refresh])

  return {
    state,
    loading,
    error,
    refresh,
    updateRoles,
    updateCompanies,
    uploadResume,
    patchProfile,
    complete,
    skip,
  }
}

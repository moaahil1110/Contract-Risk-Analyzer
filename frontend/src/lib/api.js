// API integration for Contract Risk Analyzer
import { getSession } from './supabase.js'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const REQUEST_TIMEOUT_MS = 30000

const fetchWithTimeout = async (url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) => {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    })
    return response
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('Request timed out. Check that the backend is running and try again.')
    }
    throw error
  } finally {
    clearTimeout(timeoutId)
  }
}

// Get auth token from Supabase session
const getAuthHeaders = async () => {
  const session = await getSession()
  return session?.access_token
    ? { 'Authorization': `Bearer ${session.access_token}` }
    : {}
}

export const uploadContract = async (file, contractType) => {
  const headers = await getAuthHeaders()
  const formData = new FormData()
  formData.append('file', file)
  formData.append('contract_type', contractType)

  const response = await fetchWithTimeout(`${API_URL}/api/v1/upload`, {
    method: 'POST',
    headers,
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    if (response.status === 401) {
      throw new Error('Your session has expired. Please log in again.')
    }
    if (response.status === 404) {
      throw new Error('Contract not found or you do not have access.')
    }
    throw new Error(error.detail || 'Failed to upload contract')
  }

  return response.json()
}

export const startAnalysis = async (contractId) => {
  const headers = await getAuthHeaders()
  const response = await fetchWithTimeout(`${API_URL}/api/v1/analyse/${contractId}`, {
    method: 'POST',
    headers: {
      ...headers,
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    if (response.status === 401) {
      throw new Error('Your session has expired. Please log in again.')
    }
    if (response.status === 404) {
      throw new Error('Contract not found or you do not have access.')
    }
    throw new Error(error.detail || 'Failed to start analysis')
  }

  return response.json()
}

export const rerunAnalysis = async (contractId) => {
  const headers = await getAuthHeaders()
  const response = await fetchWithTimeout(`${API_URL}/api/v1/analyse/${contractId}/rerun`, {
    method: 'POST',
    headers: {
      ...headers,
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    if (response.status === 401) {
      throw new Error('Your session has expired. Please log in again.')
    }
    if (response.status === 404) {
      throw new Error('Contract not found or you do not have access.')
    }
    throw new Error(error.detail || 'Failed to rerun analysis')
  }

  return response.json()
}

export const getAnalysis = async (contractId) => {
  const headers = await getAuthHeaders()
  const response = await fetchWithTimeout(`${API_URL}/api/v1/analyse/${contractId}`, {
    headers,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    if (response.status === 401) {
      throw new Error('Your session has expired. Please log in again.')
    }
    if (response.status === 404) {
      throw new Error('Contract not found or you do not have access.')
    }
    throw new Error(error.detail || 'Failed to fetch analysis')
  }

  return response.json()
}

export const getAnalysisStatus = async (contractId) => {
  const headers = await getAuthHeaders()
  const response = await fetchWithTimeout(`${API_URL}/api/v1/analyse/${contractId}/status`, {
    headers,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    if (response.status === 401) {
      throw new Error('Your session has expired. Please log in again.')
    }
    if (response.status === 404) {
      throw new Error('Contract not found or you do not have access.')
    }
    throw new Error(error.detail || 'Failed to fetch analysis status')
  }

  return response.json()
}

export const getHistory = async (params = {}) => {
  const headers = await getAuthHeaders()
  const query = new URLSearchParams()
  if (params.search) query.append('search', params.search)
  if (params.status) query.append('status', params.status)
  if (params.contract_type) query.append('contract_type', params.contract_type)
  if (params.grade) query.append('grade', params.grade)
  if (params.limit) query.append('limit', String(params.limit))
  if (params.offset !== undefined) query.append('offset', String(params.offset))

  const qs = query.toString()
  const url = `${API_URL}/api/v1/history${qs ? `?${qs}` : ''}`

  const response = await fetchWithTimeout(url, { headers })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    if (response.status === 401) {
      throw new Error('Your session has expired. Please log in again.')
    }
    throw new Error(error.detail || 'Failed to fetch history')
  }

  return response.json()
}

export const deleteContract = async (contractId) => {
  const headers = await getAuthHeaders()
  const response = await fetchWithTimeout(`${API_URL}/api/v1/history/${contractId}`, {
    method: 'DELETE',
    headers,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    if (response.status === 401) {
      throw new Error('Your session has expired. Please log in again.')
    }
    if (response.status === 404) {
      throw new Error('Contract not found or you do not have access.')
    }
    if (response.status === 409) {
      throw new Error(error.detail || 'Cannot delete while analysis is active.')
    }
    throw new Error(error.detail || 'Failed to delete contract')
  }

  return true
}

export const exportReport = async (contractId) => {
  const headers = await getAuthHeaders()
  const response = await fetchWithTimeout(`${API_URL}/api/v1/export/${contractId}`, {
    headers,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    if (response.status === 401) {
      throw new Error('Your session has expired. Please log in again.')
    }
    if (response.status === 404) {
      throw new Error('Contract not found or you do not have access.')
    }
    throw new Error(error.detail || 'Failed to export report')
  }

  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const filenameMatch = disposition.match(/filename="?([^"]+)"?/)

  return {
    blob,
    filename: filenameMatch?.[1],
  }
}

// Poll until analysis is complete
export const pollUntilComplete = async (contractId, onUpdate, onComplete, onError) => {
  const poll = async () => {
    try {
      const data = await getAnalysisStatus(contractId)

      if (onUpdate) {
        onUpdate(data)
      }

      if (data.has_results || data.status === 'complete') {
        if (onComplete) {
          onComplete(data)
        }
        return
      }

      if (data.status === 'failed') {
        throw new Error(data.error_message || data.error || data.message || 'Analysis failed')
      }

      // Continue polling every 3 seconds
      setTimeout(poll, 3000)
    } catch (error) {
      if (onError) {
        onError(error)
      } else {
        console.error('Polling error:', error)
      }
    }
  }

  poll()
}

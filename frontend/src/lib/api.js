// API integration for Contract Risk Analyzer

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Get auth token from Supabase session
const getAuthHeaders = async () => {
  const { getSession } = await import('./supabase.js')
  const session = await getSession()
  return {
    'Authorization': `Bearer ${session?.access_token || ''}`,
  }
}

export const uploadContract = async (file, contractType) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('contract_type', contractType)

  const response = await fetch(`${API_URL}/api/v1/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to upload contract')
  }

  return response.json()
}

export const startAnalysis = async (contractId) => {
  const headers = await getAuthHeaders()
  const response = await fetch(`${API_URL}/api/v1/analyse/${contractId}`, {
    method: 'POST',
    headers: {
      ...headers,
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to start analysis')
  }

  return response.json()
}

export const getAnalysis = async (contractId) => {
  const headers = await getAuthHeaders()
  const response = await fetch(`${API_URL}/api/v1/analyse/${contractId}`, {
    headers,
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to fetch analysis')
  }

  return response.json()
}

export const getHistory = async () => {
  const headers = await getAuthHeaders()
  const response = await fetch(`${API_URL}/api/v1/history`, {
    headers,
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to fetch history')
  }

  return response.json()
}

export const exportReport = async (contractId) => {
  const headers = await getAuthHeaders()
  const response = await fetch(`${API_URL}/api/v1/export/${contractId}`, {
    headers,
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to export report')
  }

  return response.blob()
}

// Poll until analysis is complete
export const pollUntilComplete = async (contractId, onUpdate, onComplete, onError) => {
  const poll = async () => {
    try {
      const data = await getAnalysis(contractId)
      
      if (onUpdate) {
        onUpdate(data)
      }

      if (data.status === 'complete') {
        if (onComplete) {
          onComplete(data)
        }
        return
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

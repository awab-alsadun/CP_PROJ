import { useState, useEffect, useCallback } from 'react'

export function useApi(fetchFn, deps = [], options = {}) {
  const { immediate = true, defaultData = null } = options
  const [data, setData] = useState(defaultData)
  const [loading, setLoading] = useState(immediate)
  const [error, setError] = useState(null)

  const execute = useCallback(async (...args) => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchFn(...args)
      setData(result)
      return result
    } catch (err) {
      setError(err.message || 'Something went wrong')
      return null
    } finally {
      setLoading(false)
    }
  }, deps) // eslint-disable-line

  useEffect(() => {
    if (immediate) execute()
  }, []) // eslint-disable-line

  return { data, loading, error, refetch: execute }
}
import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import api from '../api'

export default function Secret() {
  const { token } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get(`/secret/${token}`)
      .then(r => setData(r.data))
      .catch(e => setError(e.response?.data?.detail || 'Link invalid or expired'))
  }, [token])

  if (error) return (
    <div className="p-8 max-w-md mx-auto text-center">
      <p className="text-red-600 text-lg">{error}</p>
    </div>
  )

  if (!data) return <div className="p-8 text-center">Loading...</div>

  return (
    <div className="p-8 max-w-md mx-auto text-center">
      <h1 className="text-xl font-bold mb-4">PIN — {data.club}</h1>
      <div className="bg-gray-100 border-2 border-gray-300 rounded p-6 text-3xl font-mono tracking-widest">
        {data.pin}
      </div>
      <p className="mt-4 text-sm text-gray-500">
        Ce lien est à usage unique. / This link is one-time use.
      </p>
    </div>
  )
}

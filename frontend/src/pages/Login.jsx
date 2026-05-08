import { useState } from 'react'
import api from '../api'

export default function Login({ onLogin }) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    setError('')
    try {
      const r = await api.get(`/auth?pin=${pin}`)
      localStorage.setItem('pin', pin)
      localStorage.setItem('role', r.data.role)
      localStorage.setItem('club_id', r.data.club_id || '')
      localStorage.setItem('club_name', r.data.club_name)
      // Append to login log
      const logs = JSON.parse(localStorage.getItem('login_log') || '[]')
      logs.push({ time: new Date().toLocaleString(), role: r.data.role, club: r.data.club_name })
      localStorage.setItem('login_log', JSON.stringify(logs.slice(-50)))
      onLogin(r.data)
    } catch {
      setError('PIN invalide')
    }
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100">
      <form onSubmit={submit} className="bg-white p-8 rounded shadow-md w-80">
        <h1 className="text-xl font-bold mb-4 text-center">Meet Manager</h1>
        <p className="text-sm text-gray-600 mb-4 text-center">Entrez votre PIN de club</p>
        <input type="text" maxLength={6} value={pin} onChange={e => setPin(e.target.value)}
               className="border p-3 rounded w-full text-center text-2xl tracking-widest mb-4"
               placeholder="000000" autoFocus />
        {error && <p className="text-red-600 text-sm mb-2 text-center">{error}</p>}
        <button type="submit" className="bg-blue-600 text-white w-full py-2 rounded hover:bg-blue-700">
          Connexion
        </button>
      </form>
    </div>
  )
}

import { useState } from 'react'
import { useLang } from '../i18n'
import api from '../api'

export default function Login({ onLogin }) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const { t, lang, toggle } = useLang()

  async function submit(e) {
    e.preventDefault()
    setError('')
    try {
      const r = await api.post('/auth', { pin })
      localStorage.setItem('pin', pin)
      localStorage.setItem('role', r.data.role)
      localStorage.setItem('club_id', r.data.club_id || '')
      localStorage.setItem('club_name', r.data.club_name)
      const logs = JSON.parse(localStorage.getItem('login_log') || '[]')
      logs.push({ time: new Date().toLocaleString(), role: r.data.role, club: r.data.club_name })
      localStorage.setItem('login_log', JSON.stringify(logs.slice(-50)))
      onLogin(r.data)
    } catch {
      setError(t.invalid_pin)
    }
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100">
      <form onSubmit={submit} className="bg-white p-8 rounded shadow-md w-80">
        <div className="flex justify-end mb-2">
          <button type="button" onClick={toggle} className="text-xs bg-gray-200 px-2 py-1 rounded">
            {lang === 'fr' ? 'EN' : 'FR'}
          </button>
        </div>
        <h1 className="text-xl font-bold mb-4 text-center">{t.login_title}</h1>
        <p className="text-sm text-gray-600 mb-4 text-center">{t.login_prompt}</p>
        <input type="text" maxLength={6} value={pin} onChange={e => setPin(e.target.value)}
               className="border p-3 rounded w-full text-center text-2xl tracking-widest mb-4"
               placeholder="000000" autoFocus />
        {error && <p className="text-red-600 text-sm mb-2 text-center">{error}</p>}
        <button type="submit" className="bg-blue-600 text-white w-full py-2 rounded hover:bg-blue-700">
          {t.login_btn}
        </button>
      </form>
    </div>
  )
}

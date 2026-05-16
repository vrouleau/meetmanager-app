import { useState, useEffect } from 'react'
import { Link } from 'react-router'
import { useLang } from '../i18n'
import api from '../api'

export default function Login({ onLogin }) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [closed, setClosed] = useState(false)
  const { t, lang, toggle } = useLang()

  useEffect(() => {
    fetch('/api/meet-info')
      .then(r => r.json())
      .then(data => {
        if (data.closure_date && new Date(data.closure_date) < new Date()) setClosed(true)
      })
      .catch(() => {})
  }, [])

  async function submit(e) {
    e.preventDefault()
    setError('')
    try {
      const r = await api.post('/auth', { pin })
      localStorage.setItem('pin', pin)
      localStorage.setItem('role', r.data.role)
      localStorage.setItem('club_id', r.data.club_id || '')
      localStorage.setItem('club_name', r.data.club_name)
      onLogin(r.data)
    } catch {
      setError(t.invalid_pin)
    }
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100">
      <form onSubmit={submit} className="bg-white p-8 rounded shadow-md w-80 transition-all duration-300 starting:opacity-0 starting:scale-95">
        <div className="flex justify-end mb-2">
          <button type="button" onClick={toggle} className="text-xs bg-gray-200 px-2 py-1 rounded">
            {lang === 'fr' ? 'EN' : 'FR'}
          </button>
        </div>
        <h1 className="text-xl font-bold mb-4 text-center text-balance">{t.login_title}</h1>
        <p className="text-sm text-gray-600 mb-4 text-center text-pretty">{t.login_prompt}</p>
        <input type="text" maxLength={6} value={pin} onChange={e => setPin(e.target.value)}
               className="border p-3 rounded w-full text-center text-2xl tracking-widest mb-4"
               placeholder="000000" autoFocus />
        {error && <p className="text-red-600 text-sm mb-2 text-center">{error}</p>}
        <button type="submit" className="bg-blue-600 text-white w-full py-2 rounded hover:bg-blue-600/85">
          {t.login_btn}
        </button>
        {!closed && (
          <div className="mt-4 text-center">
            <Link to="/self-invite" className="text-xs text-gray-500 hover:underline">
              {t.self_invite_title}
            </Link>
            <span className="mx-2 text-gray-300">·</span>
            <a href="/best-times" target="_blank" rel="noopener noreferrer" className="text-xs text-gray-500 hover:underline">
              {t.best_times_link}
            </a>
          </div>
        )}
      </form>
    </div>
  )
}

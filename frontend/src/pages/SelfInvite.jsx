import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useLang } from '../i18n'

export default function SelfInvite() {
  const { t, lang, toggle } = useLang()
  const [clubs, setClubs] = useState([])
  const [meetName, setMeetName] = useState('')
  const [selectedClubId, setSelectedClubId] = useState('')
  const [email, setEmail] = useState('')
  const [sending, setSending] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/api/self-invite/clubs')
      .then(r => r.json())
      .then(data => setClubs(data))
      .catch(() => setError('Failed to load clubs'))
    fetch('/api/meet-info')
      .then(r => r.json())
      .then(data => setMeetName(data.meet_name || ''))
      .catch(() => {})
  }, [])

  function handleClubChange(e) {
    const id = e.target.value
    setSelectedClubId(id)
    setMsg('')
    setError('')
    const club = clubs.find(c => String(c.id) === id)
    setEmail(club?.admin_email || '')
  }

  async function handleSend() {
    if (!selectedClubId) return
    setSending(true)
    setMsg('')
    setError('')
    try {
      const res = await fetch('/api/self-invite', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ club_id: Number(selectedClubId), lang }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `Error ${res.status}`)
      }
      setMsg(t.self_invite_sent)
    } catch (e) {
      setError(e.message || 'Error')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow p-6 w-full max-w-sm">
        <div className="flex justify-between items-center mb-4">
          <h1 className="text-xl font-bold">{t.self_invite_title}</h1>
          <button onClick={toggle} className="text-xs bg-gray-200 px-2 py-1 rounded hover:bg-gray-300">
            {lang === 'fr' ? 'EN' : 'FR'}
          </button>
        </div>
        {meetName && <p className="text-sm text-gray-600 mb-4 font-medium">{meetName}</p>}

        {clubs.length === 0 && !error && (
          <p className="text-gray-500 text-sm">{t.self_invite_no_clubs}</p>
        )}

        {clubs.length > 0 && (
          <>
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t.self_invite_select_club}
              </label>
              <select
                value={selectedClubId}
                onChange={handleClubChange}
                className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              >
                <option value="">—</option>
                {clubs.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t.self_invite_email_label}
              </label>
              <input
                type="email"
                readOnly
                value={email}
                placeholder="—"
                className="w-full border rounded px-3 py-2 text-sm bg-gray-50 text-gray-600 cursor-default"
              />
            </div>

            <button
              onClick={handleSend}
              disabled={!selectedClubId || !email || sending}
              className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              {sending ? '…' : t.self_invite_send_btn}
            </button>
          </>
        )}

        {msg && <p className="mt-3 text-green-700 text-sm">{msg}</p>}
        {error && <p className="mt-3 text-red-600 text-sm">{error}</p>}

        <div className="mt-4 text-center">
          <Link to="/" className="text-xs text-gray-500 hover:underline">{t.self_invite_back}</Link>
        </div>
      </div>
    </div>
  )
}

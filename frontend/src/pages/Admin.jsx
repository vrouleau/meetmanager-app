import { useState, useEffect } from 'react'
import { useLang } from '../i18n'
import api from '../api'
import { BUILD_TIMESTAMP } from '../buildInfo'

export default function Admin() {
  const [status, setStatus] = useState(null)
  const [clubs, setClubs] = useState([])
  const [selectedClubId, setSelectedClubId] = useState('')
  const [organizer, setOrganizer] = useState(null)
  const [newClubName, setNewClubName] = useState('')
  const [newClubEmail, setNewClubEmail] = useState('')
  const [msg, setMsg] = useState('')
  const { t, lang } = useLang()

  useEffect(() => { loadStatus(); loadClubs(); loadOrganizer() }, [])

  async function loadStatus() {
    const r = await api.get('/status')
    setStatus(r.data)
  }

  async function loadClubs() {
    const r = await api.get('/clubs')
    setClubs(r.data)
  }

  async function loadOrganizer() {
    const r = await api.get('/admin/organizer')
    setOrganizer(r.data)
  }

  async function uploadEntries(e) {
    const file = e.target.files[0]
    if (!file) return
    const fdPreview = new FormData()
    fdPreview.append('file', file)
    let preview
    try {
      const r = await api.post('/upload/preview', fdPreview)
      preview = r.data
    } catch (err) {
      setMsg('Cannot read file: ' + (err.detail || err.message))
      e.target.value = ''
      return
    }
    const prompt = t.confirm_upload_lenex
      .replace('%clubs_total%', preview.clubs_in_file)
      .replace('%athletes_total%', preview.athletes_in_file)
      .replace('%clubs%', preview.clubs_new)
      .replace('%athletes%', preview.athletes_new)
    if (!confirm(prompt)) {
      e.target.value = ''
      return
    }
    const fd = new FormData()
    fd.append('file', file)
    setMsg('Uploading entries...')
    const r = await api.post('/upload/entries', fd)
    const d = r.data
    setMsg(`Done: ${d.clubs_added} clubs, ${d.athletes_added} athletes, ${d.athletes_created || 0} new from results, ${d.times_updated} best times`)
    e.target.value = ''
    loadStatus()
    loadClubs()
  }

  async function uploadResults(e) {
    const file = e.target.files[0]
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    setMsg('Uploading results...')
    const r = await api.post('/upload/results', fd)
    const d = r.data
    setMsg(`Done: ${d.clubs_added} clubs, ${d.athletes_added} athletes, ${d.athletes_created || 0} new from results, ${d.times_updated} best times`)
    loadStatus()
  }

  function exportLxf() {
    fetch('/api/export', { headers: { 'X-Club-Pin': localStorage.getItem('pin') || '' } })
      .then(r => { if (!r.ok) throw new Error(r.status); return r.blob() })
      .then(blob => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'inscriptions_bundle.zip'
        a.click()
        URL.revokeObjectURL(url)
      })
      .catch(e => setMsg('Export error: ' + e.message))
  }


  async function addClub() {
    if (!newClubName.trim()) return
    try {
      await api.post('/clubs', { name: newClubName.trim(), admin_email: newClubEmail.trim() || undefined })
      setNewClubName('')
      setNewClubEmail('')
      loadClubs()
      loadStatus()
      setMsg(lang === 'fr' ? 'Club ajouté' : 'Club added')
    } catch (e) { setMsg(e.detail || e.message || 'Error') }
  }

  async function deleteClub(club) {
    const message = club.athlete_count > 0
      ? t.confirm_delete_club_with_athletes.replace('%name%', club.name).replace('%n%', club.athlete_count)
      : t.confirm_delete_club.replace('%name%', club.name)
    if (!confirm(message)) return
    try {
      await api.delete(`/clubs/${club.id}`)
      loadClubs()
      loadStatus()
      setMsg(`${club.name} ${lang === 'fr' ? 'supprimé' : 'deleted'}`)
    } catch (e) { setMsg(e.detail || e.message || 'Error') }
  }

  async function updateEmail(club, email) {
    await api.put(`/clubs/${club.id}`, { admin_email: email })
    loadClubs()
  }

  return (
    <div className="p-4 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-4 text-balance">{t.admin}</h1>

      {status && (
        <div className="mb-4 p-3 bg-gray-100 rounded text-sm">
          <p>Clubs: {status.clubs} | Athletes: {status.athletes} | Events: {status.events}</p>
          <p>Registrations: {status.registrations} | Best Times: {status.best_times}</p>
        </div>
      )}

      <div className="space-y-4">
        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">{t.upload_lxf}</h2>
          <p className="text-sm text-gray-600 mb-2 text-pretty">{t.upload_lxf_desc}</p>
          <input type="file" accept=".lxf" onChange={uploadEntries} />
        </div>

        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">{t.change_admin_pin}</h2>
          <form onSubmit={async e => {
            e.preventDefault()
            const newPin = e.target.pin.value
            if (newPin.length < 4) { setMsg('PIN must be at least 4 characters'); return }
            await api.post('/admin/change-pin', { pin: newPin })
            localStorage.setItem('pin', newPin)
            setMsg('Admin PIN changed. Use new PIN next login.')
            e.target.reset()
          }} className="flex gap-2">
            <input name="pin" type="text" placeholder="New PIN" className="border p-2 rounded w-32" required />
            <button type="submit" className="bg-gray-700 text-white px-4 py-2 rounded">Change</button>
          </form>
        </div>

        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">{t.regen_pins}</h2>
          <p className="text-sm text-gray-600 mb-2 text-pretty">{t.regen_pins_desc}</p>
          <button onClick={async () => {
            if (!confirm('Regenerate ALL club PINs? Coaches will need new PINs.')) return
            const r = await api.post('/clubs/regenerate-pins', {})
            setMsg(`Regenerated PINs for ${r.data.regenerated} clubs`)
            loadStatus()
          }} className="bg-orange-600 text-white px-4 py-2 rounded hover:bg-orange-600/85">
            Regenerate PINs
          </button>
        </div>

        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">{t.flush_meet}</h2>
          <p className="text-sm text-gray-600 mb-2 text-pretty">{t.flush_meet_desc}</p>
          <button onClick={async () => {
            if (!confirm(t.confirm_flush_meet)) return
            const r = await api.delete('/registrations')
            setMsg(`${t.flush_meet}: ${r.data.deleted} registrations deleted`)
            loadStatus()
            loadOrganizer()
          }} className="bg-red-600 text-white px-4 py-2 rounded hover:bg-red-600/85">
            {t.flush_meet}
          </button>
        </div>

        {/* Set Meet Organizer */}
        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">{t.set_organizer_title}</h2>
          {organizer?.club_name && (
            <p className="text-sm mb-2 text-purple-700 font-medium">
              {t.currently_organized_by} <strong>{organizer.club_name}</strong>
            </p>
          )}
          {clubs.length > 0 && (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <select
                className="border p-2 rounded sm:w-64"
                value={selectedClubId}
                onChange={e => setSelectedClubId(e.target.value)}>
                <option value="">{lang === 'fr' ? '— Choisir un club —' : '— Select a club —'}</option>
                {clubs.map(club => (
                  <option key={club.id} value={club.id}>{club.name}</option>
                ))}
              </select>
              {selectedClubId && (
                <button className="bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-600/85"
                  onClick={async () => {
                    const club = clubs.find(c => String(c.id) === String(selectedClubId))
                    try {
                      await api.post('/admin/set-organizer', { club_id: Number(selectedClubId) })
                      setMsg(`${club?.name} ${t.set_as_organizer_done}`)
                      loadOrganizer()
                    } catch (e) { setMsg(e.detail || e.message || 'Error') }
                  }}>
                  {t.set_as_organizer}
                </button>
              )}
            </div>
          )}
        </div>

        {/* Club Manager */}
        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">{t.club_manager}</h2>
          <div className="max-h-72 overflow-y-auto border rounded mb-3">
            <table className="w-full text-sm">
              <thead><tr className="border-b bg-gray-50">
                <th className="p-2 text-left">{t.club}</th>
                <th className="p-2 text-left">Email</th>
                <th className="p-2 w-20"></th>
              </tr></thead>
              <tbody>
                {clubs.map(c => (
                  <tr key={c.id} className="border-b hover:bg-gray-50">
                    <td className="p-2">{c.name} <span className="text-xs text-gray-400">({c.athlete_count}, PIN: {c.pin || '—'})</span></td>
                    <td className="p-2">
                      <input type="email" className="border p-1 rounded w-full text-sm"
                        defaultValue={c.admin_email}
                        onKeyDown={e => { if (e.key === 'Enter') e.target.blur() }}
                        onBlur={e => { if (e.target.value !== c.admin_email) updateEmail(c, e.target.value) }}
                        placeholder="email@example.com" />
                    </td>
                    <td className="p-2 text-center">
                      <button onClick={() => deleteClub(c)}
                        className="text-red-600 hover:text-red-800 text-xs font-medium">
                        {t.delete}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex gap-2">
            <input type="text" className="border p-2 rounded flex-1" placeholder={t.club_name_placeholder}
              value={newClubName} onChange={e => setNewClubName(e.target.value)} />
            <input type="email" className="border p-2 rounded flex-1" placeholder="Email"
              value={newClubEmail} onChange={e => setNewClubEmail(e.target.value)} />
            <button onClick={addClub} className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-600/85">
              {t.add}
            </button>
          </div>
        </div>
      </div>

      {msg && <p className="mt-4 text-green-700">{msg}</p>}

      <footer className="mt-8 pt-4 border-t text-xs text-gray-400 text-center">
        Source : <a href="https://github.com/vrouleau/meetmanager-app" target="_blank" rel="noopener" className="underline">github.com/vrouleau/meetmanager-app</a>
        {' '}— build : {BUILD_TIMESTAMP}
      </footer>
    </div>
  )
}

import { useState, useEffect } from 'react'
import { useLang } from '../i18n'
import api from '../api'
import { BUILD_TIMESTAMP } from '../buildInfo'

export default function Admin() {
  const [status, setStatus] = useState(null)
  const [meetInfo, setMeetInfo] = useState(null)
  const [clubs, setClubs] = useState([])
  const [selectedClubId, setSelectedClubId] = useState('')
  const [emailDraft, setEmailDraft] = useState('')
  const [msg, setMsg] = useState('')
  const { t, lang } = useLang()

  const selectedClub = clubs.find(c => String(c.id) === String(selectedClubId)) || null

  useEffect(() => { loadStatus(); loadMeetInfo(); loadClubs() }, [])

  async function loadStatus() {
    const r = await api.get('/status')
    setStatus(r.data)
  }

  async function loadMeetInfo() {
    const r = await api.get('/meet-info')
    setMeetInfo(r.data)
  }

  async function loadClubs() {
    const r = await api.get('/clubs')
    setClubs(r.data)
    setEmailDraft(prev => {
      const sel = r.data.find(c => String(c.id) === String(selectedClubId))
      return sel ? (sel.admin_email || '') : prev
    })
  }

  async function uploadMeet(e) {
    const file = e.target.files[0]
    if (!file) return
    if (meetInfo?.filename && !confirm(t.confirm_replace_meet)) {
      e.target.value = ''
      return
    }
    const fd = new FormData()
    fd.append('file', file)
    setMsg('Uploading meet structure...')
    const r = await api.post('/upload/meet', fd)
    setMsg(`Done: ${r.data.events_loaded} events loaded from ${r.data.filename}`)
    e.target.value = ''
    loadStatus()
    loadMeetInfo()
    loadClubs()
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
    window.open('/api/export', '_blank')
  }

  async function exportInvoices() {
    setMsg('Creating Stripe draft invoices...')
    try {
      const r = await api.post('/invoices', {})
      const d = r.data
      let m = `Created ${d.created.length} draft invoice(s) in Stripe`
      if (d.skipped.length) m += `, skipped ${d.skipped.length} (no billable items)`
      if (d.errors.length) m += `, ${d.errors.length} error(s): ${d.errors.map(e => e.club).join(', ')}`
      setMsg(m)
    } catch (e) {
      setMsg(e.detail || e.message || 'Error creating invoices')
    }
  }

  return (
    <div className="p-4 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">{t.admin}</h1>

      {status && (
        <div className="mb-4 p-3 bg-gray-100 rounded text-sm">
          <p>Clubs: {status.clubs} | Athletes: {status.athletes} | Events: {status.events}</p>
          <p>Registrations: {status.registrations} | Best Times: {status.best_times}</p>
        </div>
      )}

      {meetInfo && (
        <div className="mb-4 p-3 bg-blue-50 rounded text-sm">
          <strong>{t.meet}:</strong>{' '}
          {meetInfo.filename
            ? <>
                <strong>{meetInfo.meet_name || meetInfo.filename}</strong>
                {' '}— {({'LCM':'50m','SCM':'25m'})[meetInfo.course] || meetInfo.course || '?'} — {meetInfo.masters ? 'Masters' : 'No Masters'}
                {' '}— {meetInfo.events} {t.events}
                <br/><span className="text-gray-500">({meetInfo.filename}, {t.uploaded} {new Date(meetInfo.uploaded_at + 'Z').toLocaleString()})</span>
              </>
            : <span className="text-red-600">{t.no_meet}</span>}
        </div>
      )}

      {/* Closure date */}
      <div className="mb-4 p-3 bg-yellow-50 rounded text-sm flex items-center gap-3">
        <label className="font-semibold whitespace-nowrap">{lang === 'fr' ? 'Date limite d\'inscription' : 'Entry closure date'}:</label>
        <input type="date" className="border p-1 rounded"
          defaultValue={meetInfo?.closure_date || ''}
          onBlur={async e => {
            await api.put('/closure-date', { closure_date: e.target.value })
            loadMeetInfo()
            setMsg(lang === 'fr' ? 'Date limite enregistrée' : 'Closure date saved')
          }} />
        {meetInfo?.closure_date && <span className="text-gray-600">{new Date(meetInfo.closure_date + 'T00:00:00').toLocaleDateString()}</span>}
      </div>

      <div className="space-y-4">
        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">{t.upload_meet}</h2>
          <p className="text-sm text-gray-600 mb-2">{t.upload_meet_desc}</p>
          <input type="file" accept=".lxf" onChange={uploadMeet} />
        </div>

        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">{t.upload_lxf}</h2>
          <p className="text-sm text-gray-600 mb-2">{t.upload_lxf_desc}</p>
          <input type="file" accept=".lxf" onChange={uploadEntries} />
        </div>

        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">{t.export}</h2>
          <p className="text-sm text-gray-600 mb-2">{t.export_desc}</p>
          <button onClick={exportLxf}
                  className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
            {t.download_lxf}
          </button>
        </div>

        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">{t.invoices}</h2>
          <p className="text-sm text-gray-600 mb-2">{t.invoices_desc}</p>
          <button onClick={exportInvoices}
                  className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
            {t.download_invoices}
          </button>
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
          <p className="text-sm text-gray-600 mb-2">{t.regen_pins_desc}</p>
          <button onClick={async () => {
            if (!confirm('Regenerate ALL club PINs? Coaches will need new PINs.')) return
            const r = await api.post('/clubs/regenerate-pins', {})
            setMsg(`Regenerated PINs for ${r.data.regenerated} clubs`)
            loadStatus()
          }} className="bg-orange-600 text-white px-4 py-2 rounded hover:bg-orange-700">
            Regenerate PINs
          </button>
        </div>

        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">{t.flush_reg}</h2>
          <p className="text-sm text-gray-600 mb-2">{t.flush_reg_desc}</p>
          <button onClick={async () => {
            if (!confirm('Delete ALL registrations? This cannot be undone.')) return
            const r = await api.delete('/registrations')
            setMsg(`Flushed ${r.data.deleted} registrations`)
            loadStatus()
          }} className="bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700">
            Flush Registrations
          </button>
        </div>
      </div>

      {msg && <p className="mt-4 text-green-700">{msg}</p>}

      {/* Club email + Send PIN */}
      {clubs.length > 0 && (
        <div className="border p-4 rounded mt-4">
          <h2 className="font-semibold mb-2">{t.team_invites || 'Team Invites'}</h2>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <select
              className="border p-2 rounded sm:w-64"
              value={selectedClubId}
              onChange={e => {
                const id = e.target.value
                setSelectedClubId(id)
                const club = clubs.find(c => String(c.id) === String(id))
                setEmailDraft(club?.admin_email || '')
              }}>
              <option value="">{lang === 'fr' ? '— Choisir un club —' : '— Select a club —'}</option>
              {clubs.map(club => (
                <option key={club.id} value={club.id}>{club.name}</option>
              ))}
            </select>
            {selectedClub && (
              <>
                <input
                  className="border p-2 rounded flex-1"
                  type="email"
                  value={emailDraft}
                  onChange={e => setEmailDraft(e.target.value)}
                  onBlur={async () => {
                    if (emailDraft !== (selectedClub.admin_email || '')) {
                      await api.put(`/clubs/${selectedClub.id}`, { admin_email: emailDraft })
                      loadClubs()
                    }
                  }}
                  placeholder="coach@example.com" />
                <button className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700"
                  onClick={async () => {
                    if (emailDraft !== (selectedClub.admin_email || '')) {
                      await api.put(`/clubs/${selectedClub.id}`, { admin_email: emailDraft })
                    }
                    if (!emailDraft) { setMsg('Set email first'); return }
                    try {
                      const r = await api.post(`/clubs/${selectedClub.id}/send-pin`, { lang })
                      setMsg(r.data.message || 'Email sent!')
                    } catch (e) {
                      setMsg(e.detail || e.message || 'Error sending email')
                    }
                    loadClubs()
                  }}>
                  Send PIN
                </button>
                <button className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
                  onClick={async () => {
                    setMsg('Creating Stripe draft invoice...')
                    try {
                      const r = await api.post(`/clubs/${selectedClub.id}/create-invoice`, {})
                      setMsg(`Draft invoice created: ${r.data.invoice_id}`)
                    } catch (e) {
                      setMsg(e.detail || e.message || 'Error creating invoice')
                    }
                  }}>
                  {t.create_invoice || 'Create Invoice'}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      <footer className="mt-8 pt-4 border-t text-xs text-gray-400 text-center">
        Source : <a href="https://github.com/vrouleau/meetmanager-app" target="_blank" rel="noopener" className="underline">github.com/vrouleau/meetmanager-app</a>
        {' '}— build : {BUILD_TIMESTAMP}
      </footer>
    </div>
  )
}

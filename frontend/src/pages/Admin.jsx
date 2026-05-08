import { useState, useEffect } from 'react'
import api from '../api'

export default function Admin() {
  const [status, setStatus] = useState(null)
  const [meetInfo, setMeetInfo] = useState(null)
  const [msg, setMsg] = useState('')

  useEffect(() => { loadStatus(); loadMeetInfo() }, [])

  async function loadStatus() {
    const r = await api.get('/status')
    setStatus(r.data)
  }

  async function loadMeetInfo() {
    const r = await api.get('/meet-info')
    setMeetInfo(r.data)
  }

  async function uploadMeet(e) {
    const file = e.target.files[0]
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    setMsg('Uploading meet structure...')
    const r = await api.post('/upload/meet', fd)
    setMsg(`Done: ${r.data.events_loaded} events loaded from ${r.data.filename}`)
    loadStatus()
    loadMeetInfo()
  }

  async function uploadEntries(e) {
    const file = e.target.files[0]
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    setMsg('Uploading entries...')
    const r = await api.post('/upload/entries', fd)
    setMsg(`Done: ${r.data.clubs_added} clubs, ${r.data.athletes_added} athletes added`)
    loadStatus()
  }

  async function uploadResults(e) {
    const file = e.target.files[0]
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    setMsg('Uploading results...')
    const r = await api.post('/upload/results', fd)
    setMsg(`Done: ${r.data.times_updated} best times updated, ${r.data.athletes_skipped} skipped`)
    loadStatus()
  }

  function exportLxf() {
    window.open('/api/export', '_blank')
  }

  return (
    <div className="p-4 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Admin / Export</h1>

      {status && (
        <div className="mb-4 p-3 bg-gray-100 rounded text-sm">
          <p>Clubs: {status.clubs} | Athletes: {status.athletes} | Events: {status.events}</p>
          <p>Registrations: {status.registrations} | Best Times: {status.best_times}</p>
        </div>
      )}

      {meetInfo && (
        <div className="mb-4 p-3 bg-blue-50 rounded text-sm">
          <strong>Meet:</strong>{' '}
          {meetInfo.filename
            ? <>{meetInfo.filename} (uploaded {new Date(meetInfo.uploaded_at + 'Z').toLocaleString()}) — {meetInfo.events} events</>
            : <span className="text-red-600">No meet uploaded yet</span>}
        </div>
      )}

      <div className="space-y-4">
        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">Upload Meet Structure (.lxf)</h2>
          <p className="text-sm text-gray-600 mb-2">Import event structure from a SPLASH meet export. Required before registering athletes.</p>
          <input type="file" accept=".lxf" onChange={uploadMeet} />
        </div>

        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">Upload Entries (.lxf)</h2>
          <p className="text-sm text-gray-600 mb-2">Import clubs and athletes from a SPLASH entries export.</p>
          <input type="file" accept=".lxf" onChange={uploadEntries} />
        </div>

        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">Upload Results (.lxf)</h2>
          <p className="text-sm text-gray-600 mb-2">Import best times from a SPLASH results export.</p>
          <input type="file" accept=".lxf" onChange={uploadResults} />
        </div>

        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">Change Admin PIN</h2>
          <p className="text-sm text-gray-600 mb-2">Change your admin login PIN.</p>
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
          <h2 className="font-semibold mb-2">Regenerate All Club PINs</h2>
          <p className="text-sm text-gray-600 mb-2">Generate new PINs for all clubs. Old PINs will stop working.</p>
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
          <h2 className="font-semibold mb-2">Flush All Registrations</h2>
          <p className="text-sm text-gray-600 mb-2">Remove all event registrations (keeps athletes and best times).</p>
          <button onClick={async () => {
            if (!confirm('Delete ALL registrations? This cannot be undone.')) return
            const r = await api.delete('/registrations')
            setMsg(`Flushed ${r.data.deleted} registrations`)
            loadStatus()
          }} className="bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700">
            Flush Registrations
          </button>
        </div>

        <div className="border p-4 rounded">
          <h2 className="font-semibold mb-2">Export Registrations</h2>
          <p className="text-sm text-gray-600 mb-2">Download Lenex .lxf with all current registrations.</p>
          <button onClick={exportLxf}
                  className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
            Download .lxf
          </button>
        </div>
      </div>

      {msg && <p className="mt-4 text-green-700">{msg}</p>}
    </div>
  )
}

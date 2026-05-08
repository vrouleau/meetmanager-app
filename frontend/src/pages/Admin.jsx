import { useState } from 'react'
import api from '../api'

export default function Admin() {
  const [status, setStatus] = useState(null)
  const [msg, setMsg] = useState('')

  async function loadStatus() {
    const r = await api.get('/status')
    setStatus(r.data)
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

  useState(() => { loadStatus() }, [])

  return (
    <div className="p-4 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Admin / Export</h1>

      {status && (
        <div className="mb-4 p-3 bg-gray-100 rounded text-sm">
          <p>Clubs: {status.clubs} | Athletes: {status.athletes} | Events: {status.events}</p>
          <p>Registrations: {status.registrations} | Best Times: {status.best_times}</p>
        </div>
      )}

      <div className="space-y-4">
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

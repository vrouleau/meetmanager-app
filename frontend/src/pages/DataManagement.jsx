import { useState, useEffect } from 'react'
import { useLang } from '../i18n'
import api from '../api'

export default function DataManagement() {
  const { t, lang } = useLang()
  const [clubs, setClubs] = useState([])
  const [styles, setStyles] = useState([])
  const [clubMap, setClubMap] = useState({})   // { from_id: to_id }
  const [styleMap, setStyleMap] = useState({}) // { from_uid: to_uid }
  const [msg, setMsg] = useState('')

  useEffect(() => { loadClubs(); loadStyles() }, [])

  async function loadClubs() {
    const r = await api.get('/clubs')
    setClubs(r.data)
    setClubMap(Object.fromEntries(r.data.map(c => [c.id, c.id])))
  }

  async function loadStyles() {
    const r = await api.get('/data-management/styles')
    setStyles(r.data)
    setStyleMap(Object.fromEntries(r.data.map(s => [s.uid, s.uid])))
  }

  const pendingClubs = Object.entries(clubMap).filter(([f, t]) => Number(f) !== Number(t))
  const pendingStyles = Object.entries(styleMap).filter(([f, t]) => Number(f) !== Number(t))

  async function resolveClubs() {
    if (!pendingClubs.length) return
    const label = lang === 'fr'
      ? `Fusionner ${pendingClubs.length} club(s) ? Cette action est irréversible.`
      : `Merge ${pendingClubs.length} club(s)? This cannot be undone.`
    if (!confirm(label)) return
    try {
      const merges = pendingClubs.map(([f, to]) => ({ from_id: Number(f), to_id: Number(to) }))
      const r = await api.post('/data-management/merge-clubs', { merges })
      setMsg(lang === 'fr' ? `${r.data.merged} club(s) fusionné(s)` : `${r.data.merged} club(s) merged`)
      loadClubs()
    } catch (e) { setMsg(e.response?.data?.detail || e.message || 'Error') }
  }

  async function resolveStyles() {
    if (!pendingStyles.length) return
    const label = lang === 'fr'
      ? `Fusionner ${pendingStyles.length} style(s) ? Cette action est irréversible.`
      : `Merge ${pendingStyles.length} style(s)? This cannot be undone.`
    if (!confirm(label)) return
    try {
      const merges = pendingStyles.map(([f, to]) => ({ from_uid: Number(f), to_uid: Number(to) }))
      const r = await api.post('/data-management/merge-styles', { merges })
      setMsg(lang === 'fr' ? `${r.data.merged_rows} ligne(s) de meilleurs temps fusionnée(s)` : `${r.data.merged_rows} best time row(s) merged`)
      loadStyles()
    } catch (e) { setMsg(e.response?.data?.detail || e.message || 'Error') }
  }

  function exportEntries() {
    fetch('/api/export/entries', { headers: { 'X-Club-Pin': localStorage.getItem('pin') || '' } })
      .then(r => {
        if (!r.ok) throw new Error(r.status)
        return r.blob()
      })
      .then(blob => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'entries.lxf'
        a.click()
        URL.revokeObjectURL(url)
      })
      .catch(e => setMsg(e.message || 'Error'))
  }

  return (
    <div className="p-4 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">{t.data_management}</h1>

      {/* Club merging */}
      <div className="border p-4 rounded mb-6">
        <h2 className="font-semibold mb-1">{t.merge_clubs}</h2>
        <p className="text-sm text-gray-600 mb-3">{t.merge_clubs_desc}</p>
        <div className="max-h-72 overflow-y-auto border rounded mb-3">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b sticky top-0">
                <th className="p-2 text-left w-1/2">{t.from_col}</th>
                <th className="p-2 text-left w-1/2">{t.to_col}</th>
              </tr>
            </thead>
            <tbody>
              {clubs.map(c => {
                const toId = clubMap[c.id] ?? c.id
                const changed = Number(toId) !== c.id
                return (
                  <tr key={c.id} className={`border-b ${changed ? 'bg-yellow-50' : 'hover:bg-gray-50'}`}>
                    <td className="p-2">{c.name}</td>
                    <td className="p-2">
                      <select
                        className="border rounded px-1 py-0.5 w-full"
                        value={toId}
                        onChange={e => setClubMap(prev => ({ ...prev, [c.id]: Number(e.target.value) }))}
                      >
                        {clubs.map(target => (
                          <option key={target.id} value={target.id}>{target.name}</option>
                        ))}
                      </select>
                    </td>
                  </tr>
                )
              })}
              {clubs.length === 0 && (
                <tr><td colSpan={2} className="p-4 text-center text-gray-500">
                  {lang === 'fr' ? 'Aucun club' : 'No clubs'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
        <button
          onClick={resolveClubs}
          disabled={!pendingClubs.length}
          className="bg-orange-600 text-white px-4 py-2 rounded hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {t.resolve}{pendingClubs.length > 0 ? ` (${pendingClubs.length})` : ''}
        </button>
      </div>

      {/* Style merging */}
      <div className="border p-4 rounded mb-6">
        <h2 className="font-semibold mb-1">{t.merge_styles}</h2>
        <p className="text-sm text-gray-600 mb-3">{t.merge_styles_desc}</p>
        <div className="max-h-72 overflow-y-auto border rounded mb-3">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b sticky top-0">
                <th className="p-2 text-left w-1/2">{t.from_col}</th>
                <th className="p-2 text-left w-1/2">{t.to_col}</th>
              </tr>
            </thead>
            <tbody>
              {styles.map(s => {
                const toUid = styleMap[s.uid] ?? s.uid
                const changed = Number(toUid) !== s.uid
                return (
                  <tr key={s.uid} className={`border-b ${changed ? 'bg-yellow-50' : 'hover:bg-gray-50'}`}>
                    <td className="p-2 font-mono text-xs">ID{s.uid}{s.name ? ` — ${s.name}` : ''}</td>
                    <td className="p-2">
                      <select
                        className="border rounded px-1 py-0.5 w-full text-xs font-mono"
                        value={toUid}
                        onChange={e => setStyleMap(prev => ({ ...prev, [s.uid]: Number(e.target.value) }))}
                      >
                        {styles.map(target => (
                          <option key={target.uid} value={target.uid}>
                            ID{target.uid}{target.name ? ` — ${target.name}` : ''}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                )
              })}
              {styles.length === 0 && (
                <tr><td colSpan={2} className="p-4 text-center text-gray-500">
                  {lang === 'fr' ? 'Aucun style disponible (aucun meilleur temps importé)' : 'No styles available (no best times imported)'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
        <button
          onClick={resolveStyles}
          disabled={!pendingStyles.length}
          className="bg-orange-600 text-white px-4 py-2 rounded hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {t.resolve}{pendingStyles.length > 0 ? ` (${pendingStyles.length})` : ''}
        </button>
      </div>

      {/* Export all data */}
      <div className="border p-4 rounded mb-4">
        <h2 className="font-semibold mb-1">{t.export_entries}</h2>
        <p className="text-sm text-gray-600 mb-3">{t.export_entries_desc}</p>
        <button
          onClick={exportEntries}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          {t.download_entries_lxf}
        </button>
      </div>

      {msg && <p className="mt-4 text-green-700 font-medium">{msg}</p>}
    </div>
  )
}

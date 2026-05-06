import { useState, useEffect } from 'react'
import { useParams, useLocation } from 'react-router-dom'
import { fetchJson } from '../api'

function msToTime(ms) {
  if (!ms) return ''
  const m = Math.floor(ms / 60000)
  const s = ((ms % 60000) / 1000).toFixed(2).padStart(5, '0')
  return `${m}:${s}`
}

function parseTime(str) {
  if (!str || str.trim().toLowerCase() === 'nt') return null
  const s = str.trim()
  let m = s.match(/^(\d+):(\d+)\.(\d+)$/)
  if (m) return parseInt(m[1])*60000 + parseInt(m[2])*1000 + parseInt(m[3])*10
  m = s.match(/^(\d+)\.(\d+)$/)
  if (m) return parseInt(m[1])*1000 + parseInt(m[2])*10
  return undefined
}

export default function Register() {
  const { meetId } = useParams()
  const location = useLocation()
  const [athletes, setAthletes] = useState([])
  const [clubs, setClubs] = useState([])
  const [selectedClub, setSelectedClub] = useState('')
  const [selectedAthlete, setSelectedAthlete] = useState(null)
  const [regData, setRegData] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchJson('/clubs').then(setClubs)
    fetchJson('/athletes').then(async (aths) => {
      setAthletes(aths)
      // Pre-select athlete if passed from meet detail
      const preselect = location.state?.athleteId
      if (preselect) {
        setSelectedAthlete(preselect)
        const data = await fetchJson(`/meets/${meetId}/register/${preselect}`)
        setRegData(data)
      }
    })
  }, [])

  const filteredAthletes = selectedClub
    ? athletes.filter(a => a.club_id === parseInt(selectedClub))
    : athletes

  const selectAthlete = async (id) => {
    setSelectedAthlete(id)
    const data = await fetchJson(`/meets/${meetId}/register/${id}`)
    setRegData(data)
  }

  const refresh = async () => {
    const data = await fetchJson(`/meets/${meetId}/register/${selectedAthlete}`)
    setRegData(data)
  }

  const registerEvent = async (eventId, timeMs) => {
    setSaving(true)
    await fetchJson('/registrations', {
      method: 'POST',
      body: JSON.stringify({ athlete_id: selectedAthlete, event_id: eventId, best_time_ms: timeMs })
    })
    await refresh()
    setSaving(false)
  }

  const unregisterEvent = async (registrationId) => {
    setSaving(true)
    await fetchJson(`/registrations/${registrationId}`, { method: 'DELETE' })
    await refresh()
    setSaving(false)
  }

  const updateTime = async (registrationId, value) => {
    const ms = parseTime(value)
    if (ms === undefined) {
      alert("Format invalide. Utilisez M:SS.hh (ex: 1:23.45) ou vide pour NT")
      return
    }
    await fetchJson(`/registrations/${registrationId}`, {
      method: 'PUT',
      body: JSON.stringify({ athlete_id: selectedAthlete, event_id: 0, best_time_ms: ms })
    })
    await refresh()
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Inscription</h1>

      <div className="flex gap-4 mb-6">
        <select className="border p-2 rounded" value={selectedClub}
          onChange={e => setSelectedClub(e.target.value)}>
          <option value="">Tous les clubs</option>
          {clubs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="border p-2 rounded w-64" value={selectedAthlete || ''}
          onChange={e => selectAthlete(parseInt(e.target.value))}>
          <option value="">Sélectionner un athlète...</option>
          {filteredAthletes.map(a => (
            <option key={a.id} value={a.id}>{a.last_name}, {a.first_name}</option>
          ))}
        </select>
      </div>

      {regData && (
        <div>
          <h2 className="text-lg font-semibold mb-3">
            {regData.athlete.name} — Épreuves individuelles
          </h2>
          <table className="w-full border-collapse text-sm mb-6">
            <thead><tr className="bg-gray-100">
              <th className="border p-2 w-10">✓</th>
              <th className="border p-2 text-left">Épreuve</th>
              <th className="border p-2 text-left">Catégorie</th>
              <th className="border p-2 text-left">Temps suggéré</th>
              <th className="border p-2 text-left">Temps inscrit</th>
            </tr></thead>
            <tbody>
              {regData.individual_events.map(style => {
                const registered = style.categories.find(c => c.registered)
                return (
                  <tr key={style.style_uid} className={registered ? 'bg-green-50' : ''}>
                    <td className="border p-2 text-center">
                      <input type="checkbox" checked={!!registered} disabled={saving}
                        onChange={() => {
                          if (registered) {
                            unregisterEvent(registered.registration_id)
                          } else {
                            // Register to first available category
                            const cat = style.categories[0]
                            registerEvent(cat.event_id, cat.suggested_time_ms)
                          }
                        }} />
                    </td>
                    <td className="border p-2 font-medium">{style.style_name}</td>
                    <td className="border p-2">
                      <select className="border p-1 rounded"
                        value={registered ? registered.event_id : ''}
                        onChange={async (e) => {
                          const newEventId = parseInt(e.target.value)
                          if (registered) await unregisterEvent(registered.registration_id)
                          const cat = style.categories.find(c => c.event_id === newEventId)
                          await registerEvent(newEventId, cat?.suggested_time_ms)
                        }}>
                        {!registered && <option value="">—</option>}
                        {style.categories.map(c => (
                          <option key={c.event_id} value={c.event_id}>{c.age_code}</option>
                        ))}
                      </select>
                    </td>
                    <td className="border p-2 text-gray-500">
                      {registered?.suggested_time_ms ? msToTime(registered.suggested_time_ms) : '—'}
                    </td>
                    <td className="border p-2">
                      {registered && (
                        <input className="border p-1 rounded w-24" placeholder="NT"
                          defaultValue={registered.entered_time_ms ? msToTime(registered.entered_time_ms) : ''}
                          key={`${registered.event_id}-${registered.entered_time_ms}`}
                          onBlur={e => updateTime(registered.registration_id, e.target.value)} />
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {regData.relay_events.length > 0 && (
            <>
              <h2 className="text-lg font-semibold mb-3">Relais</h2>
              <table className="w-full border-collapse text-sm">
                <thead><tr className="bg-gray-100">
                  <th className="border p-2 w-10">✓</th>
                  <th className="border p-2 text-left">Épreuve</th>
                  <th className="border p-2 text-left">Catégorie</th>
                  <th className="border p-2 text-left">Équipiers</th>
                </tr></thead>
                <tbody>
                  {regData.relay_events.map(style => {
                    const registered = style.categories.find(c => c.registered)
                    const teammateCount = style.relay_count - 1
                    return (
                      <tr key={style.style_uid} className={registered ? 'bg-green-50' : ''}>
                        <td className="border p-2 text-center">
                          <input type="checkbox" checked={!!registered} disabled={saving}
                            onChange={() => {
                              if (registered) unregisterEvent(registered.registration_id)
                              else registerEvent(style.categories[0].event_id, null)
                            }} />
                        </td>
                        <td className="border p-2 font-medium">{style.style_name}</td>
                        <td className="border p-2">
                          <select className="border p-1 rounded"
                            value={registered ? registered.event_id : ''}
                            onChange={async (e) => {
                              const newEventId = parseInt(e.target.value)
                              if (registered) await unregisterEvent(registered.registration_id)
                              await registerEvent(newEventId, null)
                            }}>
                            {!registered && <option value="">—</option>}
                            {style.categories.map(c => (
                              <option key={c.event_id} value={c.event_id}>{c.age_code}</option>
                            ))}
                          </select>
                        </td>
                        <td className="border p-2">
                          {registered && (
                            <div className="flex flex-wrap gap-1">
                              {Array.from({length: teammateCount}, (_, i) => (
                                <select key={i} className="border p-1 rounded text-xs">
                                  <option value="">Membre {i+2}...</option>
                                  {regData.club_athletes.map(a => (
                                    <option key={a.id} value={a.id}>{a.name}</option>
                                  ))}
                                </select>
                              ))}
                            </div>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </div>
  )
}

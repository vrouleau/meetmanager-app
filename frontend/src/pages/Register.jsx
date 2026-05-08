import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../api'

function msToTime(ms) {
  if (!ms) return ''
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  const cs = Math.floor((ms % 1000) / 10)
  return `${m}:${s.toString().padStart(2, '0')}.${cs.toString().padStart(2, '0')}`
}

function parseTime(str) {
  if (!str || str.trim().toLowerCase() === 'nt') return null
  const s = str.trim()
  let m = s.match(/^(\d+):(\d+)\.(\d+)$/)
  if (m) return parseInt(m[1]) * 60000 + parseInt(m[2]) * 1000 + parseInt(m[3]) * 10
  m = s.match(/^(\d+)\.(\d+)$/)
  if (m) return parseInt(m[1]) * 1000 + parseInt(m[2]) * 10
  return undefined
}

export default function Register() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => { load() }, [id])

  function load() {
    api.get(`/athletes/${id}/registration`).then(r => setData(r.data))
  }

  async function saveAthlete(field, value) {
    await api.put(`/athletes/${id}`, { [field]: value })
    load()
  }

  async function registerEvent(eventId, timeMs, ageCode = 'Open') {
    setSaving(true)
    await api.post('/registrations', { athlete_id: parseInt(id), event_id: eventId, entry_time_ms: timeMs, age_code: ageCode })
    await load()
    setSaving(false)
  }

  async function unregister(regId) {
    setSaving(true)
    await api.delete(`/registrations/${regId}`)
    await load()
    setSaving(false)
  }

  async function updateTime(regId, value) {
    const ms = parseTime(value)
    if (ms === undefined) { alert("Format: M:SS.cc"); return }
    await api.post('/registrations', { athlete_id: parseInt(id), event_id: 0, entry_time_ms: ms })
    // Actually need to update existing - use PUT or re-register
    // For now, find the event_id from the registration and re-post
    load()
  }

  if (!data) return <div className="p-4">Loading...</div>

  const { athlete, individual_events, relay_events, club_athletes } = data

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <Link to="/" className="text-blue-600 hover:underline">&larr; Athletes</Link>

      {/* Athlete Info */}
      <div className="mt-4 mb-6 p-4 border rounded bg-gray-50 grid grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <label className="text-xs text-gray-500">First Name</label>
          <input className="border p-1 rounded w-full" defaultValue={athlete.first_name}
                 onBlur={e => saveAthlete('first_name', e.target.value)} />
        </div>
        <div>
          <label className="text-xs text-gray-500">Last Name</label>
          <input className="border p-1 rounded w-full" defaultValue={athlete.last_name}
                 onBlur={e => saveAthlete('last_name', e.target.value)} />
        </div>
        <div>
          <label className="text-xs text-gray-500">Gender</label>
          <select className="border p-1 rounded w-full" defaultValue={athlete.gender}
                  onChange={e => saveAthlete('gender', e.target.value)}>
            <option value="M">M</option>
            <option value="F">F</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500">DOB</label>
          <input type="date" className="border p-1 rounded w-full" defaultValue={athlete.birthdate}
                 onBlur={e => saveAthlete('birthdate', e.target.value)} />
        </div>
        <div>
          <label className="text-xs text-gray-500">NRAN</label>
          <input className="border p-1 rounded w-full" defaultValue={athlete.license}
                 onBlur={e => saveAthlete('license', e.target.value)} />
        </div>
        <div className="col-span-2">
          <label className="text-xs text-gray-500">Club</label>
          <input className="border p-1 rounded w-full bg-gray-100" value={athlete.club} readOnly />
        </div>
      </div>

      {/* Individual Events */}
      <h2 className="text-lg font-semibold mb-2">Individual Events</h2>
      <table className="w-full border-collapse text-sm mb-6">
        <thead><tr className="bg-gray-100">
          <th className="border p-2 w-8">✓</th>
          <th className="border p-2 text-left">Event</th>
          <th className="border p-2 text-left">Category</th>
          <th className="border p-2 text-left">Best Time</th>
          <th className="border p-2 text-left">Entry Time</th>
        </tr></thead>
        <tbody>
          {individual_events.map(style => {
            const reg = style.categories.find(c => c.registered)
            return (
              <tr key={style.style_uid} className={reg ? 'bg-green-50' : ''}>
                <td className="border p-2 text-center">
                  <input type="checkbox" checked={!!reg} disabled={saving}
                    onChange={() => {
                      if (reg) unregister(reg.registration_id)
                      else registerEvent(style.categories[0].event_id, style.best_time_ms, style.categories[0].age_code)
                    }} />
                </td>
                <td className="border p-2">{style.style_name}</td>
                <td className="border p-2">
                  <select className="border p-1 rounded text-xs"
                    value={reg ? reg.age_code : ''}
                    onChange={async e => {
                      const cat = style.categories.find(c => c.age_code === e.target.value)
                      if (reg) await unregister(reg.registration_id)
                      await registerEvent(cat.event_id, style.best_time_ms, cat.age_code)
                    }}>
                    {!reg && <option value="">—</option>}
                    {style.categories.map(c => (
                      <option key={c.age_code} value={c.age_code}>{c.age_code}</option>
                    ))}
                  </select>
                </td>
                <td className="border p-2 text-gray-500">{msToTime(style.best_time_ms)}</td>
                <td className="border p-2">
                  {reg && (
                    <input className="border p-1 rounded w-24" placeholder="NT"
                      defaultValue={msToTime(reg.entry_time_ms)}
                      key={`${reg.registration_id}-${reg.entry_time_ms}`}
                      onBlur={async e => {
                        const ms = parseTime(e.target.value)
                        if (ms === undefined) return
                        await api.post('/registrations', {
                          athlete_id: parseInt(id), event_id: reg.event_id,
                          age_code: reg.age_code, entry_time_ms: ms
                        })
                        load()
                      }} />
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {/* Relay Events */}
      {relay_events.length > 0 && (
        <>
          <h2 className="text-lg font-semibold mb-2">Relays</h2>
          <table className="w-full border-collapse text-sm">
            <thead><tr className="bg-gray-100">
              <th className="border p-2 w-8">✓</th>
              <th className="border p-2 text-left">Event</th>
              <th className="border p-2 text-left">Category</th>
              <th className="border p-2 text-left">Entry Time</th>
              <th className="border p-2 text-left">Teammates</th>
            </tr></thead>
            <tbody>
              {relay_events.map(style => {
                const reg = style.categories.find(c => c.registered)
                const teammateCount = style.relay_count - 1
                return (
                  <tr key={style.style_uid} className={reg ? 'bg-green-50' : ''}>
                    <td className="border p-2 text-center">
                      <input type="checkbox" checked={!!reg} disabled={saving}
                        onChange={() => {
                          if (reg) unregister(reg.registration_id)
                          else registerEvent(style.categories[0].event_id, null, style.categories[0].age_code)
                        }} />
                    </td>
                    <td className="border p-2">{style.style_name} ({style.relay_count}x)</td>
                    <td className="border p-2">
                      <select className="border p-1 rounded text-xs"
                        value={reg ? reg.age_code : ''}
                        onChange={async e => {
                          const cat = style.categories.find(c => c.age_code === e.target.value)
                          if (reg) await unregister(reg.registration_id)
                          await registerEvent(cat.event_id, null, cat.age_code)
                        }}>
                        {!reg && <option value="">—</option>}
                        {style.categories.map(c => (
                          <option key={c.age_code} value={c.age_code}>{c.age_code}</option>
                        ))}
                      </select>
                    </td>
                    <td className="border p-2">
                      {reg && (
                        <input className="border p-1 rounded w-24" placeholder="NT"
                          defaultValue={msToTime(reg.entry_time_ms)}
                          key={`r-${reg.registration_id}`}
                          onBlur={async e => {
                            const ms = parseTime(e.target.value)
                            if (ms === undefined) return
                            await api.post('/registrations', {
                              athlete_id: parseInt(id), event_id: reg.event_id, entry_time_ms: ms
                            })
                            load()
                          }} />
                      )}
                    </td>
                    <td className="border p-2">
                      {reg && (
                        <div className="flex flex-wrap gap-1">
                          {Array.from({length: teammateCount}, (_, i) => (
                            <select key={i} className="border p-1 rounded text-xs w-40">
                              <option value="">Member {i + 2}...</option>
                              {club_athletes.map(a => (
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
  )
}

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

function timeToMs(str) {
  if (!str) return null
  const m = str.match(/^(\d+):(\d+)\.(\d+)$/)
  if (m) return parseInt(m[1]) * 60000 + parseInt(m[2]) * 1000 + parseInt(m[3]) * 10
  const m2 = str.match(/^(\d+)\.(\d+)$/)
  if (m2) return parseInt(m2[1]) * 1000 + parseInt(m2[2]) * 10
  return null
}

export default function Register() {
  const { id } = useParams()
  const [data, setData] = useState(null)

  useEffect(() => { load() }, [id])

  function load() {
    api.get(`/athletes/${id}/registration`).then(r => setData(r.data))
  }

  async function toggle(entry) {
    if (entry.registered) {
      await api.delete(`/registrations/${entry.registration_id}`)
    } else {
      await api.post('/registrations', {
        athlete_id: parseInt(id),
        event_id: entry.event_id,
        entry_time_ms: entry.best_time_ms || null,
      })
    }
    load()
  }

  async function updateTime(entry, timeStr) {
    const ms = timeToMs(timeStr)
    await api.post('/registrations', {
      athlete_id: parseInt(id),
      event_id: entry.event_id,
      entry_time_ms: ms,
    })
    load()
  }

  if (!data) return <div className="p-4">Loading...</div>

  const genderLabel = g => ({ 1: 'M', 2: 'F', 3: 'X' }[g] || '?')

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <Link to="/" className="text-blue-600 hover:underline">&larr; Athletes</Link>
      <h1 className="text-2xl font-bold mt-2 mb-4">
        {data.athlete.last_name}, {data.athlete.first_name}
        <span className="text-gray-500 text-lg ml-2">({data.athlete.club})</span>
      </h1>

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b font-semibold">
            <td className="p-2 w-8">✓</td>
            <td className="p-2">Event</td>
            <td className="p-2">Gender</td>
            <td className="p-2">Masters</td>
            <td className="p-2">Best Time</td>
            <td className="p-2">Entry Time</td>
          </tr>
        </thead>
        <tbody>
          {data.entries.map(e => (
            <tr key={e.event_id} className={`border-b ${e.registered ? 'bg-green-50' : ''}`}>
              <td className="p-2">
                <input type="checkbox" checked={e.registered}
                       onChange={() => toggle(e)} />
              </td>
              <td className="p-2">
                #{e.event_number} {e.style_name}
                {e.relay_count > 1 && ` (${e.relay_count}x)`}
              </td>
              <td className="p-2">{genderLabel(e.gender)}</td>
              <td className="p-2">{e.masters ? 'MA' : ''}</td>
              <td className="p-2 text-gray-500">{msToTime(e.best_time_ms)}</td>
              <td className="p-2">
                {e.registered && (
                  <input type="text" defaultValue={msToTime(e.entry_time_ms)}
                         placeholder="m:ss.cc"
                         className="border p-1 w-24 rounded"
                         onBlur={ev => updateTime(e, ev.target.value)} />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

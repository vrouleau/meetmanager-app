import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { fetchJson } from '../api'

function msToTime(ms) {
  if (!ms) return 'NT'
  const m = Math.floor(ms / 60000)
  const s = ((ms % 60000) / 1000).toFixed(2).padStart(5, '0')
  return `${m}:${s}`
}

export default function MeetDetail() {
  const { id } = useParams()
  const [meet, setMeet] = useState(null)
  const [events, setEvents] = useState([])
  const [registrations, setRegistrations] = useState([])
  const [athletes, setAthletes] = useState([])
  const [clubs, setClubs] = useState([])
  const [filterClub, setFilterClub] = useState('')
  const [expandedAthlete, setExpandedAthlete] = useState(null)

  const load = () => {
    fetchJson(`/meets/${id}`).then(setMeet)
    fetchJson(`/meets/${id}/events`).then(setEvents)
    fetchJson(`/registrations?meet_id=${id}`).then(setRegistrations)
    fetchJson('/athletes').then(setAthletes)
    fetchJson('/clubs').then(setClubs)
  }
  useEffect(() => { load() }, [id])

  const clubName = (cid) => clubs.find(c => c.id === cid)?.name || ''
  const athleteObj = (aid) => athletes.find(a => a.id === aid)
  const eventObj = (eid) => events.find(e => e.id === eid)

  // Group registrations by athlete
  const byAthlete = {}
  registrations.forEach(r => {
    if (!byAthlete[r.athlete_id]) byAthlete[r.athlete_id] = []
    byAthlete[r.athlete_id].push(r)
  })

  // Filter by club
  const filteredAthleteIds = Object.keys(byAthlete).filter(aid => {
    if (!filterClub) return true
    const a = athleteObj(parseInt(aid))
    return a && a.club_id === parseInt(filterClub)
  })

  const removeAllForAthlete = async (athleteId) => {
    const regs = byAthlete[athleteId] || []
    if (!confirm(`Supprimer les ${regs.length} inscription(s) de cet athlète?`)) return
    for (const r of regs) {
      await fetchJson(`/registrations/${r.id}`, { method: 'DELETE' })
    }
    load()
  }

  if (!meet) return <p>Chargement...</p>

  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">{meet.name}</h1>
      <p className="text-gray-600 mb-4">{meet.city} — {meet.date_start} — {events.length} épreuves</p>

      <div className="flex gap-4 mb-6">
        <Link to={`/meets/${id}/register`} className="bg-blue-600 text-white px-4 py-2 rounded">
          Inscrire des athlètes
        </Link>
        <a href={`/api/meets/${id}/export?format=lenex`}
           className="bg-green-600 text-white px-4 py-2 rounded">
          Exporter Lenex
        </a>
      </div>

      <div className="flex items-center gap-4 mb-4">
        <h2 className="text-xl font-semibold">Inscriptions ({registrations.length})</h2>
        <select className="border p-2 rounded" value={filterClub}
          onChange={e => setFilterClub(e.target.value)}>
          <option value="">Tous les clubs</option>
          {clubs.filter(c => Object.keys(byAthlete).some(aid => {
            const a = athleteObj(parseInt(aid))
            return a && a.club_id === c.id
          })).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      <table className="w-full border-collapse text-sm">
        <thead><tr className="bg-gray-100">
          <th className="border p-2 text-left">Athlète</th>
          <th className="border p-2 text-left">Club</th>
          <th className="border p-2 text-center"># Épreuves</th>
          <th className="border p-2 w-20"></th>
        </tr></thead>
        <tbody>
          {filteredAthleteIds.map(aid => {
            const a = athleteObj(parseInt(aid))
            const regs = byAthlete[aid]
            if (!a) return null
            const expanded = expandedAthlete === parseInt(aid)
            return (
              <>
                <tr key={aid} className="cursor-pointer hover:bg-gray-50"
                    onClick={() => setExpandedAthlete(expanded ? null : parseInt(aid))}>
                  <td className="border p-2 font-medium">
                    {expanded ? '▼' : '▶'} {a.first_name} {a.last_name}
                  </td>
                  <td className="border p-2">{clubName(a.club_id)}</td>
                  <td className="border p-2 text-center">{regs.length}</td>
                  <td className="border p-2">
                    <Link to={`/meets/${id}/register`} onClick={() => {}}
                      state={{ athleteId: parseInt(aid) }}
                      className="text-blue-600 text-xs hover:underline mr-2">Modifier</Link>
                    <button onClick={(e) => { e.stopPropagation(); removeAllForAthlete(aid) }}
                      className="text-red-600 text-xs hover:underline">Tout supprimer</button>
                  </td>
                </tr>
                {expanded && regs.map(r => {
                  const ev = eventObj(r.event_id)
                  return (
                    <tr key={r.id} className="bg-gray-50">
                      <td className="border p-2 pl-8 text-gray-600" colSpan={2}>
                        {ev?.style_name} — {ev?.age_code}
                      </td>
                      <td className="border p-2 text-center text-gray-600">
                        {msToTime(r.best_time_ms)}
                      </td>
                      <td className="border p-2"></td>
                    </tr>
                  )
                })}
              </>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

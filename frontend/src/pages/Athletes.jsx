import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'

export default function Athletes() {
  const [athletes, setAthletes] = useState([])
  const [clubs, setClubs] = useState([])
  const [clubFilter, setClubFilter] = useState('')
  const [search, setSearch] = useState('')

  useEffect(() => {
    api.get('/clubs').then(r => setClubs(r.data))
    api.get('/athletes').then(r => setAthletes(r.data))
  }, [])

  const filtered = athletes.filter(a => {
    if (clubFilter && a.club_id !== parseInt(clubFilter)) return false
    if (search) {
      const s = search.toLowerCase()
      return (a.first_name + ' ' + a.last_name).toLowerCase().includes(s)
    }
    return true
  })

  return (
    <div className="p-4 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Athletes</h1>
      <div className="flex gap-4 mb-4">
        <select value={clubFilter} onChange={e => setClubFilter(e.target.value)}
                className="border p-2 rounded">
          <option value="">All clubs</option>
          {clubs.map(c => <option key={c.id} value={c.id}>{c.name} ({c.athlete_count})</option>)}
        </select>
        <input type="text" placeholder="Search name..." value={search}
               onChange={e => setSearch(e.target.value)}
               className="border p-2 rounded flex-1" />
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b font-semibold">
            <td className="p-2">Name</td>
            <td className="p-2">Club</td>
            <td className="p-2">Gender</td>
            <td className="p-2">DOB</td>
            <td className="p-2"></td>
          </tr>
        </thead>
        <tbody>
          {filtered.map(a => (
            <tr key={a.id} className="border-b hover:bg-gray-50">
              <td className="p-2">{a.last_name}, {a.first_name}</td>
              <td className="p-2">{a.club}</td>
              <td className="p-2">{a.gender}</td>
              <td className="p-2">{a.birthdate}</td>
              <td className="p-2">
                <Link to={`/athletes/${a.id}/register`}
                      className="text-blue-600 hover:underline">Register</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-gray-500">{filtered.length} athletes</p>
    </div>
  )
}

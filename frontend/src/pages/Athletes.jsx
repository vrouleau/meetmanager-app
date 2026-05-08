import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'

export default function Athletes({ role, clubId }) {
  const [athletes, setAthletes] = useState([])
  const [clubs, setClubs] = useState([])
  const [clubFilter, setClubFilter] = useState(clubId || '')
  const [search, setSearch] = useState('')
  const [showAddAthlete, setShowAddAthlete] = useState(false)
  const [showAddClub, setShowAddClub] = useState(false)
  const [newClub, setNewClub] = useState('')
  const isAdmin = role === 'admin'

  useEffect(() => {
    api.get('/clubs').then(r => {
      setClubs(r.data)
      if (clubId) setClubFilter(clubId)
      else if (r.data.length > 0) setClubFilter(String(r.data[0].id))
    })
  }, [])

  useEffect(() => {
    if (clubFilter) {
      api.get(`/athletes?club_id=${clubFilter}`).then(r => setAthletes(r.data))
    } else {
      api.get('/athletes').then(r => setAthletes(r.data))
    }
  }, [clubFilter])

  function reload() {
    if (clubFilter) api.get(`/athletes?club_id=${clubFilter}`).then(r => setAthletes(r.data))
    else api.get('/athletes').then(r => setAthletes(r.data))
  }

  const filtered = athletes.filter(a => {
    if (!search) return true
    return (a.first_name + ' ' + a.last_name).toLowerCase().includes(search.toLowerCase())
  })

  async function addAthlete(e) {
    e.preventDefault()
    const fd = new FormData(e.target)
    await api.post('/athletes', {
      first_name: fd.get('first_name'),
      last_name: fd.get('last_name'),
      gender: fd.get('gender'),
      birthdate: fd.get('birthdate') || null,
      license: fd.get('license') || '',
      club_id: parseInt(clubFilter),
    })
    setShowAddAthlete(false)
    reload()
  }

  async function deleteAthlete(id, name) {
    if (!confirm(`Delete ${name}?`)) return
    await api.delete(`/athletes/${id}`)
    reload()
  }

  async function addClub(e) {
    e.preventDefault()
    await api.post('/clubs', { name: newClub })
    setNewClub('')
    setShowAddClub(false)
    api.get('/clubs').then(r => setClubs(r.data))
  }

  async function deleteClub(id, name) {
    if (!confirm(`Delete club "${name}"? Must have no athletes.`)) return
    try {
      await api.delete(`/clubs/${id}`)
      api.get('/clubs').then(r => {
        setClubs(r.data)
        if (r.data.length) setClubFilter(String(r.data[0].id))
        else setClubFilter('')
      })
    } catch { alert('Cannot delete — club has athletes') }
  }

  return (
    <div className="p-4 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Athletes</h1>

      {/* Club selector */}
      <div className="flex gap-2 mb-4 items-center">
        {isAdmin ? (
          <select value={clubFilter} onChange={e => setClubFilter(e.target.value)}
                  className="border p-2 rounded">
            {clubs.map(c => <option key={c.id} value={c.id}>{c.name} ({c.athlete_count}) PIN:{c.pin}</option>)}
          </select>
        ) : (
          <span className="font-semibold">{clubs.find(c => String(c.id) === clubFilter)?.name}</span>
        )}
        {isAdmin && <button onClick={() => deleteClub(parseInt(clubFilter), clubs.find(c=>c.id===parseInt(clubFilter))?.name)}
                className="text-red-600 text-sm hover:underline">Delete club</button>}
        {isAdmin && <button onClick={() => setShowAddClub(true)}
                className="text-blue-600 text-sm hover:underline">+ New club</button>}
        <button onClick={async () => {
          if (!confirm('Reset PIN for this club?')) return
          const r = await api.post(`/clubs/${clubFilter}/reset-pin`, {})
          alert(`New PIN: ${r.data.pin}`)
          api.get('/clubs').then(r => setClubs(r.data))
        }} className="text-orange-600 text-sm hover:underline">Reset PIN</button>
        <div className="flex-1" />
        <input type="text" placeholder="Search..." value={search}
               onChange={e => setSearch(e.target.value)}
               className="border p-2 rounded w-48" />
      </div>

      {showAddClub && (
        <form onSubmit={addClub} className="mb-4 p-3 border rounded bg-yellow-50 flex gap-2">
          <input placeholder="Club name" value={newClub} onChange={e => setNewClub(e.target.value)}
                 className="border p-1 rounded flex-1" required />
          <button type="submit" className="bg-blue-600 text-white px-3 rounded">Add</button>
          <button type="button" onClick={() => setShowAddClub(false)} className="text-gray-500">Cancel</button>
        </form>
      )}

      {/* Add athlete */}
      <div className="mb-3">
        <button onClick={() => setShowAddAthlete(!showAddAthlete)}
                className="bg-green-600 text-white px-3 py-1 rounded text-sm">+ Add Athlete</button>
      </div>
      {showAddAthlete && clubFilter && (
        <form onSubmit={addAthlete} className="mb-4 p-3 border rounded bg-green-50 grid grid-cols-5 gap-2">
          <input name="first_name" placeholder="First name" className="border p-1 rounded" required />
          <input name="last_name" placeholder="Last name" className="border p-1 rounded" required />
          <select name="gender" className="border p-1 rounded">
            <option value="M">M</option><option value="F">F</option>
          </select>
          <input name="birthdate" type="date" className="border p-1 rounded" />
          <input name="license" placeholder="NRAN" className="border p-1 rounded" />
          <button type="submit" className="bg-green-700 text-white px-3 rounded col-span-2">Save</button>
          <button type="button" onClick={() => setShowAddAthlete(false)} className="text-gray-500">Cancel</button>
        </form>
      )}

      {/* Athletes table */}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b font-semibold">
            <td className="p-2">Name</td>
            <td className="p-2">Gender</td>
            <td className="p-2">DOB</td>
            <td className="p-2">NRAN</td>
            <td className="p-2"></td>
          </tr>
        </thead>
        <tbody>
          {filtered.map(a => (
            <tr key={a.id} className="border-b hover:bg-gray-50">
              <td className="p-2">{a.last_name}, {a.first_name}</td>
              <td className="p-2">{a.gender}</td>
              <td className="p-2">{a.birthdate}</td>
              <td className="p-2">{a.license}</td>
              <td className="p-2 flex gap-2">
                <Link to={`/athletes/${a.id}/register`}
                      className="text-blue-600 hover:underline">Edit</Link>
                <button onClick={() => deleteAthlete(a.id, `${a.first_name} ${a.last_name}`)}
                        className="text-red-500 hover:underline text-xs">Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-gray-500">{filtered.length} athletes</p>
    </div>
  )
}

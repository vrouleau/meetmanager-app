import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useLang } from '../i18n'
import api from '../api'

export default function Athletes({ role, clubId }) {
  const { t } = useLang()
  const [athletes, setAthletes] = useState([])
  const [clubs, setClubs] = useState([])
  const [clubFilter, setClubFilter] = useState(clubId || sessionStorage.getItem('clubFilter') || '')
  const [search, setSearch] = useState('')
  const [showAddAthlete, setShowAddAthlete] = useState(false)

  const isAdmin = role === 'admin'
  const canViewAll = role === 'admin' || role === 'organizer'

  useEffect(() => {
    api.get('/clubs').then(r => {
      setClubs(r.data)
      if (clubId) setClubFilter(clubId)
      else if (!clubFilter && r.data.length > 0) setClubFilter(String(r.data[0].id))
    })
  }, [])

  useEffect(() => {
    if (clubFilter) sessionStorage.setItem('clubFilter', clubFilter)
  }, [clubFilter])

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



  return (
    <div className="p-4 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">
        {!canViewAll && clubs.find(c => String(c.id) === clubFilter)?.name
          ? `${clubs.find(c => String(c.id) === clubFilter).name} — ${t.athletes}`
          : t.athletes}
      </h1>

      {/* Club selector */}
      <div className="flex gap-2 mb-4 items-center">
        {canViewAll ? (
          <select value={clubFilter} onChange={e => setClubFilter(e.target.value)}
                  className="border p-2 rounded">
            {clubs.map(c => <option key={c.id} value={c.id}>{c.name} ({c.athlete_count}){isAdmin ? ` PIN:${c.pin}` : ''}</option>)}
          </select>
        ) : (
          <span className="font-semibold">{clubs.find(c => String(c.id) === clubFilter)?.name}</span>
        )}

        <button onClick={async () => {
          if (!confirm('Reset PIN for this club?')) return
          const r = await api.post(`/clubs/${clubFilter}/reset-pin`, {})
          alert(`New PIN: ${r.data.pin}`)
          api.get('/clubs').then(r => setClubs(r.data))
        }} className="text-orange-600 text-sm hover:underline">{t.reset_pin}</button>
        <div className="flex-1" />
        <input type="text" placeholder={t.search} value={search}
               onChange={e => setSearch(e.target.value)}
               className="border p-2 rounded w-48" />
      </div>



      {/* Add athlete */}
      <div className="mb-3">
        <button onClick={() => setShowAddAthlete(!showAddAthlete)}
                className="bg-green-600 text-white px-3 py-1 rounded text-sm">{t.add_athlete}</button>
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
            <td className="p-2">{t.last_name}, {t.first_name}</td>
            <td className="p-2">{t.gender}</td>
            <td className="p-2">{t.dob}</td>
            <td className="p-2">{t.nran}</td>
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
                      className="text-blue-600 hover:underline">{t.edit}</Link>
                <button onClick={() => deleteAthlete(a.id, `${a.first_name} ${a.last_name}`)}
                        className="text-red-500 hover:underline text-xs">{t.delete}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-gray-500">{filtered.length} athletes</p>
    </div>
  )
}

import React, { useState, useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import './index.css'
import Login from './pages/Login'
import Athletes from './pages/Athletes'
import Register from './pages/Register'
import Admin from './pages/Admin'

function App() {
  const [auth, setAuth] = useState(null)

  useEffect(() => {
    const pin = localStorage.getItem('pin')
    const role = localStorage.getItem('role')
    if (pin && role) {
      setAuth({ role, club_id: localStorage.getItem('club_id'), club_name: localStorage.getItem('club_name') })
    }
  }, [])

  function logout() {
    localStorage.clear()
    setAuth(null)
  }

  if (!auth) return <Login onLogin={setAuth} />

  return (
    <BrowserRouter>
      <nav className="bg-gray-800 text-white p-3 flex gap-4 items-center">
        <Link to="/" className="hover:underline">Athletes</Link>
        {auth.role === 'admin' && <Link to="/admin" className="hover:underline">Admin</Link>}
        <div className="flex-1" />
        <span className="text-sm text-gray-300">{auth.club_name}</span>
        <button onClick={logout} className="text-sm text-red-300 hover:underline">Déconnexion</button>
      </nav>
      <Routes>
        <Route path="/" element={<Athletes role={auth.role} clubId={auth.club_id} />} />
        <Route path="/athletes/:id/register" element={<Register />} />
        {auth.role === 'admin' && <Route path="/admin" element={<Admin />} />}
      </Routes>
    </BrowserRouter>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />)

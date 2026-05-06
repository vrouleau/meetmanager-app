import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import './index.css'
import Clubs from './pages/Clubs'
import Athletes from './pages/Athletes'
import Meets from './pages/Meets'
import MeetDetail from './pages/MeetDetail'
import Register from './pages/Register'

function Nav() {
  return (
    <nav className="bg-blue-800 text-white p-4 flex gap-6">
      <Link to="/" className="font-bold text-lg">Meet Manager</Link>
      <Link to="/clubs" className="hover:underline">Clubs</Link>
      <Link to="/athletes" className="hover:underline">Athlètes</Link>
      <Link to="/meets" className="hover:underline">Compétitions</Link>
    </nav>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Nav />
      <main className="p-6 max-w-6xl mx-auto">
        <Routes>
          <Route path="/" element={<h1 className="text-2xl">Bienvenue</h1>} />
          <Route path="/clubs" element={<Clubs />} />
          <Route path="/athletes" element={<Athletes />} />
          <Route path="/meets" element={<Meets />} />
          <Route path="/meets/:id" element={<MeetDetail />} />
          <Route path="/meets/:meetId/register" element={<Register />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />)

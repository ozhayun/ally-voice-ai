import { Routes, Route } from 'react-router-dom'
import { NavBar } from '@/components/NavBar'
import { Dashboard } from '@/pages/Dashboard'
import { Builder } from '@/pages/Builder'
import { Logs } from '@/pages/Logs'

export function App() {
  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <NavBar />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/builder" element={<Builder />} />
        <Route path="/logs" element={<Logs />} />
      </Routes>
    </div>
  )
}

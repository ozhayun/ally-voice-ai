import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'

export function NavBar() {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'px-3 py-1.5 text-sm transition-colors border-b-2 -mb-px',
      isActive
        ? 'text-zinc-100 border-indigo-500'
        : 'text-zinc-500 border-transparent hover:text-zinc-300',
    )

  return (
    <nav className="h-14 border-b border-zinc-800 flex items-center px-6 sticky top-0 z-10 bg-[#0a0a0a]">
      {/* Logo */}
      <div className="flex items-center gap-2 mr-8">
        <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center">
          <span className="text-white text-xs font-bold">A</span>
        </div>
        <span className="font-bold text-zinc-100 text-base tracking-tight">Ally</span>
      </div>

      {/* Nav links */}
      <div className="flex items-center h-full border-l border-zinc-800 pl-6 gap-1">
        <NavLink to="/" end className={linkClass}>
          Agents
        </NavLink>
        <NavLink to="/logs" className={linkClass}>
          Logs
        </NavLink>
        <NavLink to="/builder" className={linkClass}>
          Builder
        </NavLink>
      </div>

      {/* Right actions */}
      <div className="ml-auto flex items-center gap-3">
        <button className="flex items-center gap-2 px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-500 transition-colors">
          Publish Agent
        </button>
        <div className="w-8 h-8 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center text-xs font-semibold text-zinc-300">
          O
        </div>
      </div>
    </nav>
  )
}

import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Activity, BarChart3, BookOpen, Bot, LogOut, MessageSquare } from 'lucide-react'
import { auth } from '../lib/api'

const links = [
  { to: '/chat', label: '对话', icon: MessageSquare },
  { to: '/knowledge', label: '知识库', icon: BookOpen },
  { to: '/admin/runs', label: '运行记录', icon: Activity },
  { to: '/admin/usage', label: '用量与工具', icon: BarChart3 },
]

export default function Layout() {
  const nav = useNavigate()
  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col bg-slate-950 text-slate-300">
        <div className="flex items-center gap-2.5 px-5 pt-5 pb-4">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-violet-500 shadow-lg shadow-brand-500/30">
            <Bot className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="text-sm font-semibold text-white">客服 Copilot</div>
            <div className="text-[11px] text-slate-500">AI Agent · RAG · MCP</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3 pt-2">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition ${isActive ? 'bg-white/10 text-white shadow-inner' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'}`}>
              <Icon className="h-4 w-4" />{label}
            </NavLink>
          ))}
        </nav>
        <div className="m-3 rounded-xl bg-white/5 p-3">
          <div className="flex items-center gap-2.5">
            <div className="grid h-8 w-8 place-items-center rounded-full bg-brand-600 text-xs font-semibold text-white">{auth.email?.[0]?.toUpperCase()}</div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs font-medium text-slate-200">{auth.email}</div>
              <div className="text-[11px] text-slate-500">客服人员</div>
            </div>
            <button title="退出" onClick={() => { auth.clear(); nav('/login') }} className="rounded-lg p-1.5 text-slate-500 hover:bg-white/10 hover:text-white"><LogOut className="h-4 w-4" /></button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-hidden"><Outlet /></main>
    </div>
  )
}

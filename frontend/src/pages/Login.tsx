import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bot, Database, FileSearch, Workflow } from 'lucide-react'
import { api, auth } from '../lib/api'

export default function Login() {
  const [email, setEmail] = useState('admin@example.com')
  const [password, setPassword] = useState('admin123')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      const r = await api.post<{ access_token: string; email: string }>('/auth/login', { email, password })
      auth.set(r.access_token, r.email); nav('/chat')
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <div className="grid h-full lg:grid-cols-2">
      <div className="hidden lg:flex flex-col justify-between bg-slate-950 p-12 text-slate-300">
        <div className="flex items-center gap-2.5 text-white">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-violet-500"><Bot className="h-5 w-5" /></div>
          <span className="font-semibold">客服 Copilot</span>
        </div>
        <div>
          <h1 className="text-3xl font-semibold leading-tight text-white">让 AI Agent 替客服<br />查订单、写回复、开工单</h1>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-400">LangGraph 状态机编排，RAG 引用知识库，通过 MCP 调用 MySQL 与 Slack，每一步可观测、可回溯。</p>
          <div className="mt-8 grid grid-cols-3 gap-3">
            {[[FileSearch, 'RAG 检索', '带引用来源'], [Database, 'MCP 工具', 'MySQL / Slack'], [Workflow, 'Agent 编排', '重试 · 人工确认']].map(([Icon, t, d]) => {
              const I = Icon as React.ElementType
              return <div key={t as string} className="rounded-xl border border-white/10 bg-white/5 p-3"><I className="h-4 w-4 text-brand-400" /><div className="mt-2 text-sm font-medium text-white">{t as string}</div><div className="text-[11px] text-slate-500">{d as string}</div></div>
            })}
          </div>
        </div>
        <div className="text-[11px] text-slate-600">FastAPI · LangGraph · ChromaDB · MySQL · Redis · React</div>
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-8">
          <div>
            <h2 className="text-xl font-semibold text-slate-900">登录工作区</h2>
            <p className="mt-1 text-sm text-slate-500">使用客服账号进入</p>
          </div>
          <div className="space-y-1.5"><label className="text-xs font-medium text-slate-500">邮箱</label><input className="input" value={email} onChange={e => setEmail(e.target.value)} /></div>
          <div className="space-y-1.5"><label className="text-xs font-medium text-slate-500">密码</label><input className="input" type="password" value={password} onChange={e => setPassword(e.target.value)} /></div>
          {err && <div className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{err}</div>}
          <button disabled={busy} className="btn-primary w-full justify-center py-2.5">{busy ? '登录中…' : '登录'}</button>
          <p className="text-center text-[11px] text-slate-400">演示账号 admin@example.com / admin123</p>
        </form>
      </div>
    </div>
  )
}

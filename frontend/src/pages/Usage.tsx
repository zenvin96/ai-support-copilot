import { useEffect, useState } from 'react'
import { Coins, Database, Hash, Plug, Timer } from 'lucide-react'
import { api, type UsageRow } from '../lib/api'

type Tool = { name: string; server: string; description: string }

export default function Usage() {
  const [rows, setRows] = useState<UsageRow[]>([])
  const [tools, setTools] = useState<Tool[]>([])
  useEffect(() => { api.get<UsageRow[]>('/admin/usage').then(setRows); api.get<Tool[]>('/mcp/tools').then(setTools) }, [])
  const total = rows.reduce((a, r) => ({ calls: a.calls + r.calls, tokens: a.tokens + r.prompt_tokens + r.completion_tokens, cost: a.cost + r.cost_usd, lat: a.lat + r.avg_latency_ms * r.calls }), { calls: 0, tokens: 0, cost: 0, lat: 0 })
  const max = Math.max(1, ...rows.map(r => r.prompt_tokens + r.completion_tokens))
  const tiles = [
    { icon: Hash, label: 'LLM 调用次数', value: total.calls },
    { icon: Coins, label: '总 tokens', value: total.tokens.toLocaleString() },
    { icon: Timer, label: '平均延迟', value: `${total.calls ? Math.round(total.lat / total.calls) : 0} ms` },
    { icon: Database, label: '估算成本', value: `$${total.cost.toFixed(4)}` },
  ]

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto max-w-5xl space-y-6 px-8 py-8">
        <div><h1 className="text-2xl font-semibold text-slate-900">用量与工具</h1><p className="mt-1 text-sm text-slate-500">按天按模型汇总 token、延迟与成本；以及当前 Agent 可用的 MCP 工具</p></div>
        <div className="grid grid-cols-4 gap-4">
          {tiles.map(({ icon: Icon, label, value }) => (
            <div key={label} className="card p-5"><div className="flex items-center gap-2 text-xs text-slate-500"><Icon className="h-3.5 w-3.5" />{label}</div><div className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{value}</div></div>
          ))}
        </div>
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead className="bg-slate-50/80"><tr><th className="th">日期</th><th className="th">模型</th><th className="th text-right">调用</th><th className="th w-1/3">tokens</th><th className="th text-right">平均延迟</th><th className="th text-right">成本</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r, i) => (
                <tr key={i}>
                  <td className="td text-slate-500">{r.day}</td><td className="td font-mono text-xs">{r.model}</td><td className="td text-right tabular-nums">{r.calls}</td>
                  <td className="td"><div className="flex items-center gap-2"><div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-gradient-to-r from-brand-500 to-violet-500" style={{ width: `${((r.prompt_tokens + r.completion_tokens) / max) * 100}%` }} /></div><span className="w-16 text-right text-xs tabular-nums text-slate-500">{(r.prompt_tokens + r.completion_tokens).toLocaleString()}</span></div></td>
                  <td className="td text-right tabular-nums">{r.avg_latency_ms} ms</td><td className="td text-right tabular-nums">${r.cost_usd.toFixed(5)}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={6} className="td py-10 text-center text-slate-400">暂无数据</td></tr>}
            </tbody>
          </table>
        </div>
        <div>
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800"><Plug className="h-4 w-4 text-slate-400" />MCP 工具<span className="badge bg-slate-100 text-slate-500">{tools.length}</span></div>
          <div className="grid grid-cols-2 gap-3">
            {tools.map(t => (
              <div key={t.name} className="card p-4"><div className="flex items-center gap-2"><span className="font-mono text-[13px] font-medium text-slate-800">{t.name}</span><span className="badge bg-brand-50 text-brand-700">{t.server}</span></div><div className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-slate-500">{t.description}</div></div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

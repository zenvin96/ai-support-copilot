import { useEffect, useState } from 'react'
import { Activity } from 'lucide-react'
import { api, type Run, type RunDetail } from '../lib/api'
import { StepItem } from '../components/StepPanel'

const STATUS: Record<string, string> = { done: 'bg-emerald-50 text-emerald-700', failed: 'bg-red-50 text-red-700', running: 'bg-amber-50 text-amber-700', waiting_confirm: 'bg-amber-50 text-amber-700' }
const INTENT: Record<string, string> = { order_inquiry: '订单查询', knowledge_qa: '知识问答', chit_chat: '闲聊' }

export default function Runs() {
  const [runs, setRuns] = useState<Run[]>([])
  const [sel, setSel] = useState<RunDetail | null>(null)
  useEffect(() => { api.get<Run[]>('/admin/runs').then(setRuns) }, [])

  return (
    <div className="flex h-full">
      <div className="flex w-[52%] flex-col border-r border-slate-200/80 bg-white">
        <div className="flex h-14 items-center gap-2 border-b border-slate-200/80 px-5"><Activity className="h-4 w-4 text-slate-400" /><span className="text-sm font-semibold text-slate-800">运行记录</span><span className="badge bg-slate-100 text-slate-500">{runs.length}</span></div>
        <div className="flex-1 overflow-auto">
          <table className="w-full">
            <thead className="sticky top-0 bg-slate-50/95 backdrop-blur"><tr><th className="th">#</th><th className="th">问题</th><th className="th">意图</th><th className="th">状态</th><th className="th text-right">tokens</th><th className="th text-right">耗时</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {runs.map(r => (
                <tr key={r.id} onClick={() => api.get<RunDetail>(`/admin/runs/${r.id}`).then(setSel)} className={`cursor-pointer transition hover:bg-slate-50 ${sel?.id === r.id ? 'bg-brand-50/60' : ''}`}>
                  <td className="td text-slate-400">{r.id}</td>
                  <td className="td max-w-[220px] truncate font-medium">{r.user_query}</td>
                  <td className="td text-slate-500">{INTENT[r.intent ?? ''] ?? r.intent ?? '—'}</td>
                  <td className="td"><span className={`badge ${STATUS[r.status] ?? 'bg-slate-100'}`}>{r.status}</span></td>
                  <td className="td text-right tabular-nums">{r.total_tokens}</td>
                  <td className="td text-right tabular-nums text-slate-500">{(r.latency_ms / 1000).toFixed(1)}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="flex-1 overflow-auto p-6">
        {!sel ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">点击左侧一条记录查看步骤树与 LLM 调用</div>
        ) : (
          <div className="fade-up space-y-4">
            <div className="card p-5">
              <div className="text-[15px] font-semibold text-slate-900">{sel.user_query}</div>
              <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                <span className="badge bg-slate-100 font-mono">{sel.model}</span>
                <span className="badge bg-brand-50 text-brand-700">{INTENT[sel.intent ?? ''] ?? sel.intent}</span>
                <span className={`badge ${STATUS[sel.status] ?? 'bg-slate-100'}`}>{sel.status}</span>
                {sel.ticket_id && <span className="badge bg-emerald-50 text-emerald-700">工单 #{sel.ticket_id}</span>}
                <span className="badge bg-slate-100">{sel.total_tokens} tokens</span>
                <span className="badge bg-slate-100">${sel.cost_usd.toFixed(5)}</span>
                <span className="badge bg-slate-100">{sel.latency_ms} ms</span>
              </div>
              {sel.error && <div className="mt-3 rounded-lg bg-red-50 p-3 text-xs text-red-700">{sel.error}</div>}
            </div>
            <div className="card p-5">
              <div className="mb-4 text-sm font-semibold text-slate-800">步骤树 <span className="ml-1 text-xs font-normal text-slate-400">{sel.steps.length} 步</span></div>
              {sel.steps.map((s, i) => <StepItem key={s.seq} s={{ ...s, type: 'step', status: s.error ? 'error' : 'done' }} last={i === sel.steps.length - 1} />)}
            </div>
            <div className="card overflow-hidden">
              <div className="px-5 py-3 text-sm font-semibold text-slate-800">LLM 调用 <span className="ml-1 text-xs font-normal text-slate-400">{sel.llm_calls.length} 次</span></div>
              <table className="w-full border-t border-slate-100">
                <thead className="bg-slate-50/80"><tr><th className="th">模型</th><th className="th text-right">输入</th><th className="th text-right">输出</th><th className="th text-right">延迟</th><th className="th text-right">成本</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {sel.llm_calls.map(c => <tr key={c.id}><td className="td font-mono text-xs">{c.provider}/{c.model}</td><td className="td text-right tabular-nums">{c.prompt_tokens}</td><td className="td text-right tabular-nums">{c.completion_tokens}</td><td className="td text-right tabular-nums">{c.latency_ms} ms</td><td className="td text-right tabular-nums">${c.cost_usd.toFixed(6)}</td></tr>)}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

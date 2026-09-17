import { useState } from 'react'
import { AlertCircle, Bell, Brain, Check, ChevronDown, Database, FileSearch, Loader2, MessageSquareText, ShieldCheck, Ticket, Wrench } from 'lucide-react'
import type { SseEvent } from '../lib/api'

export type StepEvent = SseEvent & { node: string; status: string; seq?: number; tool_name?: string | null; input?: unknown; output?: unknown; latency_ms?: number; error?: string | null }

const NODE: Record<string, { label: string; icon: React.ElementType }> = {
  classify_intent: { label: '意图识别', icon: Brain },
  retrieve: { label: 'RAG 检索', icon: FileSearch },
  call_tools: { label: '工具调用', icon: Wrench },
  answer: { label: '生成回复', icon: MessageSquareText },
  confirm: { label: '人工确认', icon: ShieldCheck },
  create_ticket: { label: '创建工单', icon: Ticket },
  notify: { label: '通知客服', icon: Bell },
}

function Json({ v }: { v: unknown }) {
  return <pre className="mt-1 max-h-44 overflow-auto rounded-lg bg-slate-900 p-2.5 font-mono text-[11px] leading-relaxed text-slate-200 whitespace-pre-wrap break-all">{typeof v === 'string' ? v : JSON.stringify(v, null, 2)}</pre>
}

export function StepItem({ s, last }: { s: StepEvent; last?: boolean }) {
  const [open, setOpen] = useState(false)
  const meta = NODE[s.node] ?? { label: s.node, icon: Database }
  const Icon = s.tool_name ? Database : meta.icon
  const running = s.status === 'running'
  const err = !!s.error
  const ring = err ? 'border-red-200 bg-red-50 text-red-600' : running ? 'border-amber-200 bg-amber-50 text-amber-600' : 'border-emerald-200 bg-emerald-50 text-emerald-600'
  const hasDetail = s.input != null || s.output != null || err
  return (
    <div className="fade-up relative flex gap-3 pb-4">
      {!last && <div className="absolute left-[15px] top-8 h-full w-px bg-slate-200" />}
      <div className={`relative z-10 grid h-8 w-8 shrink-0 place-items-center rounded-full border ${ring}`}>
        {running ? <Loader2 className="h-4 w-4 animate-spin" /> : err ? <AlertCircle className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
      </div>
      <div className="min-w-0 flex-1 pt-1">
        <button disabled={!hasDetail} onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left">
          <span className="text-[13px] font-medium text-slate-800">{meta.label}</span>
          {s.tool_name && <span className="badge bg-brand-50 text-brand-700 font-mono">{s.tool_name}</span>}
          {!running && !err && <Check className="h-3.5 w-3.5 text-emerald-500" />}
          <span className="ml-auto flex items-center gap-1.5 text-[11px] text-slate-400">
            {s.latency_ms ? `${s.latency_ms} ms` : running ? '运行中' : ''}
            {hasDetail && <ChevronDown className={`h-3.5 w-3.5 transition ${open ? 'rotate-180' : ''}`} />}
          </span>
        </button>
        {open && (
          <div className="mt-1">
            {err && <div className="rounded-lg bg-red-50 px-2.5 py-1.5 text-[12px] text-red-700">{s.error}</div>}
            {s.input != null && <><div className="mt-1.5 text-[11px] font-medium text-slate-400">输入</div><Json v={s.input} /></>}
            {s.output != null && <><div className="mt-1.5 text-[11px] font-medium text-slate-400">输出</div><Json v={s.output} /></>}
          </div>
        )}
      </div>
    </div>
  )
}

export default function StepPanel({ steps }: { steps: StepEvent[] }) {
  if (!steps.length) return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-slate-400">
      <Brain className="h-8 w-8 text-slate-300" />
      <div className="text-sm">发送消息后，这里实时显示 Agent 的每一步</div>
      <div className="text-[11px]">意图 → 检索 → MCP 工具 → 回复 → 工单 → 通知</div>
    </div>
  )
  return <div className="px-4 pt-4">{steps.map((s, i) => <StepItem key={i} s={s} last={i === steps.length - 1} />)}</div>
}

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Bot, Coins, Cpu, Plus, Send, Sparkles, Ticket, Timer, User } from 'lucide-react'
import { api, streamSse, type Citation, type Conversation, type Message, type Model, type SseEvent } from '../lib/api'
import StepPanel, { type StepEvent } from '../components/StepPanel'

type Msg = Message & { citations?: Citation[]; ticket_id?: number | null; streaming?: boolean }

const SUGGESTIONS = [
  '订单 #123 为什么没发货？帮我查一下并通知客户。',
  '退款政策是什么？',
  '订单 124 现在到哪了',
  '拆封的耳机能退吗',
]

export default function Chat() {
  const [convs, setConvs] = useState<Conversation[]>([])
  const [cid, setCid] = useState<number | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [models, setModels] = useState<Model[]>([])
  const [model, setModel] = useState('')
  const [input, setInput] = useState('')
  const [steps, setSteps] = useState<StepEvent[]>([])
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<{ run_id: number; message: string } | null>(null)
  const [usage, setUsage] = useState<Record<string, number> | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.get<Conversation[]>('/conversations').then(setConvs)
    api.get<Model[]>('/agent/models').then(ms => { setModels(ms); setModel(ms.find(m => m.configured)?.model ?? ms[0]?.model ?? '') })
  }, [])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, steps])

  async function selectConv(id: number) {
    setCid(id); setSteps([]); setUsage(null)
    setMsgs(await api.get<Msg[]>(`/conversations/${id}/messages`))
  }

  async function newConv() {
    const c = await api.post<Conversation>('/conversations', { title: '新会话 ' + new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) })
    setConvs([c, ...convs]); setCid(c.id); setMsgs([]); setSteps([]); setUsage(null)
  }

  const patchLast = (f: (m: Msg) => Msg) => setMsgs(prev => { const n = [...prev]; n[n.length - 1] = f(n[n.length - 1]); return n })

  function handleEvent(e: SseEvent) {
    if (e.type === 'step') {
      const s = e as StepEvent
      setSteps(prev => {
        const i = prev.findIndex(p => p.node === s.node && p.status === 'running' && !p.tool_name)
        if (i >= 0 && s.status !== 'running' && !s.tool_name) { const n = [...prev]; n[i] = s; return n }
        if (i >= 0 && !s.tool_name) return prev
        if (s.tool_name) { const n = [...prev]; const idx = n.findIndex(p => p.node === s.node && p.status === 'running' && !p.tool_name); const item = { ...s }; if (idx >= 0) n.splice(idx, 0, item); else n.push(item); return n }
        return [...prev, s]
      })
    } else if (e.type === 'token') {
      patchLast(m => ({ ...m, content: m.content + (e.content as string) }))
    } else if (e.type === 'interrupt') {
      setPending({ run_id: e.run_id as number, message: e.message as string })
    } else if (e.type === 'done') {
      patchLast(m => ({ ...m, streaming: false, citations: e.citations as Citation[], ticket_id: e.ticket_id as number | null }))
      setUsage(e.usage as Record<string, number>)
    } else if (e.type === 'error') {
      patchLast(m => ({ ...m, streaming: false, content: m.content || `出错了：${e.message}` }))
    }
  }

  async function send(text = input) {
    if (!text.trim() || busy) return
    let conv = cid
    if (!conv) { const c = await api.post<Conversation>('/conversations', { title: text.slice(0, 20) }); setConvs(p => [c, ...p]); setCid(c.id); conv = c.id }
    setInput(''); setBusy(true); setSteps([]); setUsage(null)
    setMsgs(prev => [...prev, { id: Date.now(), role: 'user', content: text, run_id: null }, { id: Date.now() + 1, role: 'assistant', content: '', run_id: null, streaming: true }])
    try { await streamSse('/agent/run', { query: text, conversation_id: conv, model }, handleEvent) }
    catch (e) { handleEvent({ type: 'error', message: (e as Error).message }) }
    finally { setBusy(false) }
  }

  async function resume(approved: boolean) {
    const p = pending; setPending(null); if (!p) return
    setBusy(true)
    try { await streamSse('/agent/resume', { run_id: p.run_id, approved }, handleEvent) } finally { setBusy(false) }
  }

  return (
    <div className="flex h-full">
      {/* conversations */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-slate-200/80 bg-white">
        <div className="p-3"><button onClick={newConv} className="btn-primary w-full justify-center"><Plus className="h-4 w-4" />新会话</button></div>
        <div className="flex-1 space-y-0.5 overflow-auto px-2 pb-2">
          {convs.map(c => (
            <button key={c.id} onClick={() => selectConv(c.id)} className={`block w-full truncate rounded-xl px-3 py-2.5 text-left text-[13px] transition ${cid === c.id ? 'bg-brand-50 font-medium text-brand-700' : 'text-slate-600 hover:bg-slate-50'}`}>{c.title}</button>
          ))}
          {convs.length === 0 && <div className="px-3 py-6 text-center text-xs text-slate-400">还没有会话</div>}
        </div>
      </aside>

      {/* chat */}
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-slate-200/80 bg-white/80 px-5 backdrop-blur">
          <Cpu className="h-4 w-4 text-slate-400" />
          <select value={model} onChange={e => setModel(e.target.value)} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[13px] font-medium text-slate-700 outline-none focus:border-brand-500">
            {models.map(m => <option key={m.model} value={m.model} disabled={!m.configured}>{m.provider} / {m.model}{m.configured ? '' : '（未配置）'}</option>)}
          </select>
          {usage && (
            <div className="ml-auto flex items-center gap-2 text-[11px] text-slate-500">
              <span className="badge bg-slate-100"><Coins className="mr-1 h-3 w-3" />{usage.prompt_tokens}+{usage.completion_tokens} tokens</span>
              <span className="badge bg-slate-100">${usage.cost_usd}</span>
              <span className="badge bg-slate-100"><Timer className="mr-1 h-3 w-3" />{usage.latency_ms} ms</span>
            </div>
          )}
        </header>

        <div className="flex-1 overflow-auto">
          <div className="mx-auto max-w-3xl px-6 py-6">
            {msgs.length === 0 && (
              <div className="fade-up mt-16 text-center">
                <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-violet-500 shadow-lg shadow-brand-500/30"><Sparkles className="h-7 w-7 text-white" /></div>
                <h2 className="mt-5 text-xl font-semibold text-slate-900">我可以帮你处理客服问题</h2>
                <p className="mt-1.5 text-sm text-slate-500">查知识库、查订单、查物流、生成回复话术、创建工单并通知同事</p>
                <div className="mx-auto mt-8 grid max-w-xl grid-cols-2 gap-2.5">
                  {SUGGESTIONS.map(s => <button key={s} onClick={() => send(s)} className="card px-4 py-3 text-left text-[13px] text-slate-700 transition hover:border-brand-300 hover:bg-brand-50/40">{s}</button>)}
                </div>
              </div>
            )}
            <div className="space-y-6">
              {msgs.map(m => (
                <div key={m.id} className={`fade-up flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
                  <div className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${m.role === 'user' ? 'bg-slate-200 text-slate-600' : 'bg-gradient-to-br from-brand-500 to-violet-500 text-white'}`}>
                    {m.role === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                  </div>
                  <div className={`min-w-0 max-w-[85%] ${m.role === 'user' ? 'text-right' : ''}`}>
                    {m.role === 'user' ? (
                      <div className="inline-block rounded-2xl rounded-tr-md bg-brand-600 px-4 py-2.5 text-left text-[14.5px] leading-6 text-white shadow-sm shadow-brand-600/20 whitespace-pre-wrap">{m.content}</div>
                    ) : (
                      <div className="card rounded-tl-md px-5 py-3">
                        {m.content ? (
                          <div className={`prose-chat ${m.streaming ? 'cursor-blink' : ''}`}><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
                        ) : (
                          <div className="flex items-center gap-2 py-1 text-sm text-slate-400"><span className="h-2 w-2 animate-bounce rounded-full bg-brand-500" /><span className="h-2 w-2 animate-bounce rounded-full bg-brand-500 [animation-delay:.15s]" /><span className="h-2 w-2 animate-bounce rounded-full bg-brand-500 [animation-delay:.3s]" /><span className="ml-1">Agent 正在处理</span></div>
                        )}
                        {(m.citations?.length || m.ticket_id) ? (
                          <div className="mt-3 border-t border-slate-100 pt-3">
                            {m.ticket_id && <div className="mb-2 inline-flex items-center gap-1.5 rounded-lg bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700"><Ticket className="h-3.5 w-3.5" />已创建工单 #{m.ticket_id}，并已通知客服</div>}
                            {m.citations && m.citations.length > 0 && (
                              <div className="space-y-1">
                                <div className="text-[11px] font-medium text-slate-400">引用来源</div>
                                <div className="flex flex-wrap gap-1.5">
                                  {m.citations.map((c, i) => (
                                    <details key={i} className="group">
                                      <summary className="badge cursor-pointer list-none bg-slate-100 text-slate-600 hover:bg-brand-50 hover:text-brand-700">[{i + 1}] {c.filename} · {Math.round(c.score * 100)}%</summary>
                                      <div className="mt-1.5 max-w-lg rounded-lg bg-slate-50 p-2.5 text-[12px] leading-relaxed text-slate-600 whitespace-pre-wrap">{c.text}</div>
                                    </details>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        ) : null}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {pending && (
              <div className="fade-up mt-4 card border-amber-200 bg-amber-50/60 p-4 text-sm">
                <div className="font-medium text-amber-900">{pending.message}</div>
                <div className="mt-3 flex gap-2">
                  <button onClick={() => resume(true)} className="btn-primary">确认执行</button>
                  <button onClick={() => resume(false)} className="btn-ghost">取消</button>
                </div>
              </div>
            )}
            <div ref={bottom} />
          </div>
        </div>

        <div className="border-t border-slate-200/80 bg-white/80 p-4 backdrop-blur">
          <form onSubmit={e => { e.preventDefault(); send() }} className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm focus-within:border-brand-500 focus-within:ring-4 focus-within:ring-brand-500/10">
            <textarea rows={1} value={input} onChange={e => setInput(e.target.value)} disabled={busy}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder="输入客服问题，Enter 发送，Shift+Enter 换行" className="max-h-40 flex-1 resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-slate-400" />
            <button disabled={busy || !input.trim()} className="btn-primary h-9 w-9 justify-center p-0"><Send className="h-4 w-4" /></button>
          </form>
        </div>
      </section>

      {/* steps */}
      <aside className="flex w-80 shrink-0 flex-col border-l border-slate-200/80 bg-white">
        <div className="flex h-14 items-center border-b border-slate-200/80 px-4 text-[13px] font-semibold text-slate-700">Agent 执行过程{busy && <span className="ml-2 badge bg-amber-50 text-amber-700">运行中</span>}</div>
        <div className="flex-1 overflow-auto"><StepPanel steps={steps} /></div>
      </aside>
    </div>
  )
}

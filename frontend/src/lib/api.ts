const BASE = import.meta.env.VITE_API_BASE ?? '/api'

export const auth = {
  get token() { return localStorage.getItem('token') },
  get email() { return localStorage.getItem('email') },
  set(token: string, email: string) { localStorage.setItem('token', token); localStorage.setItem('email', email) },
  clear() { localStorage.removeItem('token'); localStorage.removeItem('email') },
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> ?? {}) }
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`
  if (init.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const res = await fetch(BASE + path, { ...init, headers })
  if (res.status === 401) { auth.clear(); location.href = '/login'; throw new Error('unauthorized') }
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText)
  return res.json()
}

export const api = {
  get: <T,>(p: string) => request<T>(p),
  post: <T,>(p: string, body?: unknown) => request<T>(p, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body ?? {}) }),
  put: <T,>(p: string, body?: unknown) => request<T>(p, { method: 'PUT', body: JSON.stringify(body ?? {}) }),
  del: <T,>(p: string) => request<T>(p, { method: 'DELETE' }),
}

export type SseEvent = { type: string; [k: string]: unknown }

/** POST + 手动解析 SSE（EventSource 不支持 POST 和自定义 header） */
export async function streamSse(path: string, body: unknown, onEvent: (e: SseEvent) => void, signal?: AbortSignal) {
  const res = await fetch(BASE + path, {
    method: 'POST', signal,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
    body: JSON.stringify(body),
  })
  if (!res.ok || !res.body) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText)
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  const flush = (block: string) => {
    const data = block.split(/\r?\n/).filter(l => l.startsWith('data:')).map(l => l.slice(5).trim()).join('\n')
    if (data) { try { onEvent(JSON.parse(data)) } catch { /* ping / non-json */ } }
  }
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    // sse-starlette 用 \r\n\r\n 分隔事件，兼容 \n\n
    const parts = buf.split(/\r?\n\r?\n/)
    buf = parts.pop() ?? ''
    for (const block of parts) flush(block)
  }
  if (buf.trim()) flush(buf)
}

export type Conversation = { id: number; title: string; created_at: string }
export type Message = { id: number; role: 'user' | 'assistant'; content: string; run_id: number | null }
export type Doc = { id: number; filename: string; chunk_count: number; status: string; error: string | null; created_at: string }
export type DocDetail = { id: number; filename: string; content: string; chunk_count: number; status: string; error: string | null }
export type Model = { provider: string; model: string; configured: boolean }
export type Run = { id: number; user_query: string; intent: string | null; model: string; status: string; total_tokens: number; latency_ms: number; cost_usd: number; ticket_id: number | null; error: string | null; created_at: string }
export type Step = { seq: number; node: string; tool_name: string | null; input: unknown; output: unknown; latency_ms: number; error: string | null }
export type LlmCall = { id: number; provider: string; model: string; prompt_tokens: number; completion_tokens: number; latency_ms: number; cost_usd: number }
export type RunDetail = Run & { steps: Step[]; llm_calls: LlmCall[] }
export type UsageRow = { day: string; model: string; calls: number; prompt_tokens: number; completion_tokens: number; cost_usd: number; avg_latency_ms: number }
export type Citation = { doc_id: number; filename: string; chunk_index: number; score: number; text: string }

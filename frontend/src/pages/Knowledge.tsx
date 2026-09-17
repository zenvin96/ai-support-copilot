import { useEffect, useRef, useState } from 'react'
import { FilePlus2, FileText, Loader2, Pencil, Save, Search, Trash2, UploadCloud, X } from 'lucide-react'
import { api, type Citation, type Doc, type DocDetail } from '../lib/api'

const STATUS: Record<string, string> = { ready: 'bg-emerald-50 text-emerald-700', failed: 'bg-red-50 text-red-700', pending: 'bg-amber-50 text-amber-700' }

type Editor = { mode: 'new' | 'edit'; id?: number; filename: string; content: string }

export default function Knowledge() {
  const [docs, setDocs] = useState<Doc[]>([])
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<Citation[]>([])
  const [drag, setDrag] = useState(false)
  const [editor, setEditor] = useState<Editor | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const file = useRef<HTMLInputElement>(null)
  const load = () => api.get<Doc[]>('/rag/documents').then(setDocs)

  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t) }, [])

  async function upload(files: FileList | null) {
    if (!files) return
    for (const f of Array.from(files)) { const fd = new FormData(); fd.append('file', f); await api.post('/rag/documents', fd) }
    load(); if (file.current) file.current.value = ''
  }

  async function openEdit(id: number) {
    setLoading(true); setEditor({ mode: 'edit', id, filename: '', content: '' })
    const d = await api.get<DocDetail>(`/rag/documents/${id}`)
    setEditor({ mode: 'edit', id, filename: d.filename, content: d.content }); setLoading(false)
  }

  async function save() {
    if (!editor || !editor.content.trim() || !editor.filename.trim()) return
    setSaving(true)
    try {
      if (editor.mode === 'new') await api.post('/rag/documents/text', { filename: editor.filename, content: editor.content })
      else await api.put(`/rag/documents/${editor.id}`, { filename: editor.filename, content: editor.content })
      setEditor(null); load()
    } finally { setSaving(false) }
  }

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto max-w-5xl space-y-6 px-8 py-8">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">知识库</h1>
            <p className="mt-1 text-sm text-slate-500">上传或手写文档，自动切片、向量化；Agent 回答时引用这里的内容</p>
          </div>
          <button onClick={() => setEditor({ mode: 'new', filename: '', content: '' })} className="btn-primary"><FilePlus2 className="h-4 w-4" />新建文档</button>
        </div>

        <label onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
          onDrop={e => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files) }}
          className={`card flex cursor-pointer flex-col items-center justify-center gap-2 border-dashed py-8 transition ${drag ? 'border-brand-500 bg-brand-50/50' : 'hover:border-brand-300'}`}>
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-brand-50 text-brand-600"><UploadCloud className="h-5 w-5" /></div>
          <div className="text-sm font-medium text-slate-700">拖拽文件到这里，或点击选择</div>
          <div className="text-xs text-slate-400">支持 .md / .txt / .pdf，可多选</div>
          <input ref={file} type="file" multiple accept=".md,.txt,.pdf" className="hidden" onChange={e => upload(e.target.files)} />
        </label>

        <div className="card overflow-hidden">
          <table className="w-full">
            <thead className="bg-slate-50/80"><tr><th className="th">文件</th><th className="th">切片数</th><th className="th">状态</th><th className="th">上传时间</th><th className="th text-right">操作</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {docs.map(d => (
                <tr key={d.id} className="hover:bg-slate-50/60">
                  <td className="td"><button onClick={() => openEdit(d.id)} className="flex items-center gap-2.5 text-left hover:text-brand-700"><FileText className="h-4 w-4 text-slate-400" /><span className="font-medium">{d.filename}</span></button></td>
                  <td className="td">{d.chunk_count}</td>
                  <td className="td"><span className={`badge ${STATUS[d.status]}`}>{d.status}</span>{d.error && <div className="mt-1 max-w-xs truncate text-[11px] text-red-500" title={d.error}>{d.error}</div>}</td>
                  <td className="td text-slate-500">{new Date(d.created_at).toLocaleString('zh-CN')}</td>
                  <td className="td"><div className="flex items-center justify-end gap-1">
                    <button title="查看/编辑" className="rounded-lg p-1.5 text-slate-400 hover:bg-brand-50 hover:text-brand-600" onClick={() => openEdit(d.id)}><Pencil className="h-4 w-4" /></button>
                    <button title="删除" className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600" onClick={async () => { await api.del(`/rag/documents/${d.id}`); load() }}><Trash2 className="h-4 w-4" /></button>
                  </div></td>
                </tr>
              ))}
              {docs.length === 0 && <tr><td colSpan={5} className="td py-10 text-center text-slate-400">还没有文档。上传文件，或点右上角「新建文档」手写一篇。</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="card p-5">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800"><Search className="h-4 w-4 text-slate-400" />检索调试</div>
          <form onSubmit={async e => { e.preventDefault(); setHits(await api.post<Citation[]>('/rag/query', { query: q })) }} className="flex gap-2">
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="例如：退款多久到账" className="input" />
            <button className="btn-ghost shrink-0">检索</button>
          </form>
          <div className="mt-3 space-y-2">
            {hits.map((h, i) => (
              <div key={i} className="rounded-xl border border-slate-100 bg-slate-50/60 p-3">
                <div className="flex items-center gap-2 text-[11px] text-slate-500"><span className="badge bg-white">[{i + 1}]</span>{h.filename} · chunk {h.chunk_index}<span className="ml-auto font-medium text-brand-600">{Math.round(h.score * 100)}%</span></div>
                <div className="mt-1.5 text-[13px] leading-relaxed text-slate-700 whitespace-pre-wrap">{h.text}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* editor drawer */}
      {editor && (
        <div className="fixed inset-0 z-30 flex">
          <div className="flex-1 bg-slate-900/30 backdrop-blur-sm" onClick={() => setEditor(null)} />
          <div className="fade-up flex w-full max-w-2xl flex-col bg-white shadow-2xl">
            <div className="flex items-center gap-3 border-b border-slate-200 px-5 py-4">
              <div className="grid h-9 w-9 place-items-center rounded-xl bg-brand-50 text-brand-600">{editor.mode === 'new' ? <FilePlus2 className="h-4 w-4" /> : <Pencil className="h-4 w-4" />}</div>
              <div className="flex-1"><div className="text-sm font-semibold text-slate-800">{editor.mode === 'new' ? '新建文档' : '编辑文档'}</div><div className="text-[11px] text-slate-400">保存后自动重新切片与向量化</div></div>
              <button onClick={() => setEditor(null)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"><X className="h-4 w-4" /></button>
            </div>
            {loading ? (
              <div className="flex flex-1 items-center justify-center text-slate-400"><Loader2 className="h-5 w-5 animate-spin" /></div>
            ) : (
              <div className="flex flex-1 flex-col gap-3 overflow-hidden p-5">
                <div className="space-y-1.5"><label className="text-xs font-medium text-slate-500">文件名</label>
                  <input className="input" value={editor.filename} placeholder="例如：售后政策.md" onChange={e => setEditor({ ...editor, filename: e.target.value })} /></div>
                <div className="flex flex-1 flex-col gap-1.5 overflow-hidden"><label className="text-xs font-medium text-slate-500">内容（支持 Markdown）</label>
                  <textarea className="input flex-1 resize-none font-mono text-[13px] leading-relaxed" value={editor.content} placeholder="在这里输入或粘贴文档内容…" onChange={e => setEditor({ ...editor, content: e.target.value })} /></div>
                <div className="text-[11px] text-slate-400">{editor.content.length} 字</div>
              </div>
            )}
            <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-4">
              <button onClick={() => setEditor(null)} className="btn-ghost">取消</button>
              <button onClick={save} disabled={saving || loading || !editor.content.trim() || !editor.filename.trim()} className="btn-primary">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}{saving ? '保存中' : '保存并向量化'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { type LLMConfig, llmApi } from '../api/client'

const DEFAULT_PROMPT = `判断以下抖音视频内容是否与搜索关键词相关。
只回答"是"或"否"，不要解释。

搜索关键词：{keyword}
视频描述：{desc}
作者：{author}

是否相关：`

const defaults = {
  name: '', base_url: '', api_key: '', model: 'gpt-4o-mini',
  prompt_template: DEFAULT_PROMPT, is_default: false,
}

export default function LLMConfigPage() {
  const [configs, setConfigs] = useState<LLMConfig[]>([])
  const [form, setForm] = useState({ ...defaults })
  const [editing, setEditing] = useState<LLMConfig | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<number | null>(null)
  const [testResult, setTestResult] = useState<Record<number, { ok: boolean; msg: string } | null>>({})

  const load = () => llmApi.list().then(setConfigs)
  useEffect(() => { load() }, [])

  const openCreate = () => { setForm({ ...defaults }); setEditing(null); setShowForm(true) }
  const openEdit = (c: LLMConfig) => {
    setForm({
      name: c.name, base_url: c.base_url, api_key: c.api_key,
      model: c.model, prompt_template: c.prompt_template, is_default: c.is_default,
    })
    setEditing(c); setShowForm(true)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true)
    try {
      if (editing) await llmApi.update(editing.id, form)
      else await llmApi.create(form)
      setShowForm(false); load()
    } finally { setSaving(false) }
  }

  const handleTest = async (id: number) => {
    setTesting(id)
    try {
      const res = await llmApi.test(id)
      setTestResult(r => ({
        ...r,
        [id]: { ok: res.ok, msg: res.ok ? (res.response ?? '✓') : (res.error ?? '失败') },
      }))
      setTimeout(() => setTestResult(r => ({ ...r, [id]: null })), 4000)
    } finally { setTesting(null) }
  }

  const inputCls = 'w-full border border-purple-100 rounded-xl px-3 py-2 text-sm bg-white/70 focus:outline-none focus:border-indigo-400'

  return (
    <div className="p-4 md:p-8">
      <h2 className="text-2xl font-extrabold mb-1" style={{ color: 'var(--text-primary)' }}>
        LLM 配置
      </h2>
      <p className="text-sm text-slate-400 mb-5">
        配置 OpenAI 兼容的远端 LLM 接口，用于采集结果相关性检测
      </p>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={() => setShowForm(false)} />
          <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl shadow-2xl"
            style={{ background: 'linear-gradient(160deg,rgba(255,255,255,0.98) 0%,rgba(248,246,255,0.98) 100%)' }}>
            <div className="sticky top-0 z-10 flex items-center justify-between px-7 py-5 border-b border-purple-50 rounded-t-2xl"
              style={{ background: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(10px)' }}>
              <div>
                <h3 className="text-lg font-extrabold" style={{ color: 'var(--text-primary)' }}>{editing ? '编辑配置' : '新增配置'}</h3>
                <p className="text-xs text-slate-400 mt-0.5">{editing ? `正在编辑「${editing.name}」` : '配置 OpenAI 兼容接口'}</p>
              </div>
              <button onClick={() => setShowForm(false)} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-purple-50 text-slate-400 hover:text-indigo-500 transition-colors text-lg">✕</button>
            </div>
            <div className="px-7 py-6">
              <form onSubmit={handleSubmit} className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-semibold text-slate-600 mb-1">配置名称</label>
                    <input required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className={inputCls} placeholder="如：DeepSeek" />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-600 mb-1">模型名称</label>
                    <input required value={form.model} onChange={e => setForm(f => ({ ...f, model: e.target.value }))} className={inputCls} placeholder="如：deepseek-chat" />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-600 mb-1">API Base URL</label>
                  <input required value={form.base_url} onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))} className={inputCls} placeholder="https://api.deepseek.com/v1" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-600 mb-1">API Key</label>
                  <input value={form.api_key} type="password" onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))} className={inputCls} placeholder="sk-..." />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-600 mb-1">
                    Prompt 模板
                    <span className="ml-2 text-xs font-normal text-slate-400">变量：{'{keyword}'} {'{desc}'} {'{author}'}</span>
                  </label>
                  <textarea value={form.prompt_template} rows={7} onChange={e => setForm(f => ({ ...f, prompt_template: e.target.value }))} className={inputCls + ' font-mono text-xs'} />
                </div>
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="llm_is_default" checked={form.is_default} onChange={e => setForm(f => ({ ...f, is_default: e.target.checked }))} className="w-4 h-4 accent-indigo-500" />
                  <label htmlFor="llm_is_default" className="text-sm text-slate-500">设为默认配置</label>
                </div>
                <div className="flex gap-3 justify-end pt-3 border-t border-purple-50">
                  <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm border border-purple-100 rounded-xl text-slate-500 bg-white/70">取消</button>
                  <button type="submit" disabled={saving} className="btn-primary">{saving ? '保存中...' : '保存'}</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      <button className="btn-primary mb-5" onClick={openCreate}>＋ 新增配置</button>

      {configs.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3" style={{ minHeight: 'calc(100vh - 260px)' }}>
          <div className="text-6xl opacity-40">🤖</div>
          <p className="text-slate-600 font-semibold text-base">还没有 LLM 配置</p>
          <p className="text-slate-400 text-sm">配置 OpenAI 兼容接口，启用相关性智能过滤</p>
        </div>
      ) : (
      <div className="space-y-3 max-w-2xl">
        {configs.map(c => (
          <div key={c.id} className="glass-card p-4 flex items-center gap-4">
            <div
              className="w-10 h-10 rounded-full flex items-center justify-center text-lg flex-shrink-0"
              style={{
                background: 'linear-gradient(135deg,rgba(99,102,241,0.15),rgba(168,85,247,0.15))',
              }}
            >
              🤖
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-slate-700">{c.name}</span>
                {c.is_default && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 font-semibold">
                    默认
                  </span>
                )}
                {testResult[c.id]?.ok === true && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">
                    ✓ {testResult[c.id]?.msg}
                  </span>
                )}
                {testResult[c.id]?.ok === false && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-500 max-w-[200px] truncate">
                    ✗ {testResult[c.id]?.msg}
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-400 mt-0.5">{c.model} · {c.base_url}</div>
            </div>
            <div className="flex gap-2 flex-shrink-0">
              <button
                onClick={() => handleTest(c.id)}
                disabled={testing === c.id}
                className="text-xs px-2.5 py-1 rounded-lg bg-indigo-50 text-indigo-500 border border-indigo-100 disabled:opacity-50"
              >
                {testing === c.id ? '测试中...' : '测试'}
              </button>
              {!c.is_default && (
                <button
                  onClick={() => llmApi.setDefault(c.id).then(load)}
                  className="text-xs px-2.5 py-1 rounded-lg bg-purple-50 text-purple-500 border border-purple-100"
                >
                  设为默认
                </button>
              )}
              <button
                onClick={() => openEdit(c)}
                className="text-xs px-2.5 py-1 rounded-lg bg-white/60 text-slate-500 border border-purple-50"
              >
                编辑
              </button>
              <button
                onClick={() => llmApi.delete(c.id).then(load)}
                className="text-xs px-2.5 py-1 rounded-lg bg-red-50 text-red-400 border border-red-100"
              >
                删除
              </button>
            </div>
          </div>
        ))}
      </div>
      )}
    </div>
  )
}

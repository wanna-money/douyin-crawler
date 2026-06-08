import { useEffect, useState } from 'react'
import { type CookieAccount, cookiesApi } from '../api/client'

const defaults = { name: '', cookie: '', note: '', is_default: false }

export default function Cookies() {
  const [accounts, setAccounts] = useState<CookieAccount[]>([])
  const [form, setForm] = useState({ ...defaults })
  const [editing, setEditing] = useState<CookieAccount | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = () => cookiesApi.list().then(setAccounts)
  useEffect(() => { load() }, [])

  const openCreate = () => { setForm({ ...defaults }); setEditing(null); setShowForm(true) }
  const openEdit = (a: CookieAccount) => {
    setForm({ name: a.name, cookie: a.cookie, note: a.note, is_default: a.is_default })
    setEditing(a); setShowForm(true)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true)
    try {
      if (editing) await cookiesApi.update(editing.id, form)
      else await cookiesApi.create(form)
      setShowForm(false); load()
    } finally { setSaving(false) }
  }

  const inputCls = 'w-full border border-purple-100 rounded-xl px-3 py-2 text-sm bg-white/70 focus:outline-none focus:border-indigo-400'

  return (
    <div className="p-4 md:p-8">
      <h2 className="text-2xl font-extrabold mb-1" style={{ color: 'var(--text-primary)' }}>Cookie 管理</h2>
      <p className="text-sm text-slate-400 mb-5">管理抖音账号 Cookie，支持多账号切换</p>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={() => setShowForm(false)} />
          <div className="relative w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-2xl shadow-2xl"
            style={{ background: 'linear-gradient(160deg,rgba(255,255,255,0.98) 0%,rgba(248,246,255,0.98) 100%)' }}>
            <div className="sticky top-0 z-10 flex items-center justify-between px-7 py-5 border-b border-purple-50 rounded-t-2xl"
              style={{ background: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(10px)' }}>
              <div>
                <h3 className="text-lg font-extrabold" style={{ color: 'var(--text-primary)' }}>{editing ? '编辑账号' : '新增账号'}</h3>
                <p className="text-xs text-slate-400 mt-0.5">{editing ? `正在编辑「${editing.name}」` : '粘贴抖音 Cookie 以授权采集'}</p>
              </div>
              <button onClick={() => setShowForm(false)} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-purple-50 text-slate-400 hover:text-indigo-500 transition-colors text-lg">✕</button>
            </div>
            <div className="px-7 py-6">
              <form onSubmit={handleSubmit} className="space-y-3">
                <div>
                  <label className="block text-sm font-semibold text-slate-600 mb-1">账号名称</label>
                  <input required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className={inputCls} placeholder="如：主号" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-600 mb-1">Cookie</label>
                  <textarea required value={form.cookie} onChange={e => setForm(f => ({ ...f, cookie: e.target.value }))} rows={4} className={inputCls + ' font-mono text-xs'} placeholder="粘贴从浏览器 F12 复制的 Cookie" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-600 mb-1">备注（可选）</label>
                  <input value={form.note} onChange={e => setForm(f => ({ ...f, note: e.target.value }))} className={inputCls} />
                </div>
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="is_default_c" checked={form.is_default} onChange={e => setForm(f => ({ ...f, is_default: e.target.checked }))} className="w-4 h-4 accent-indigo-500" />
                  <label htmlFor="is_default_c" className="text-sm text-slate-500">设为默认账号</label>
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

      <button className="btn-primary mb-5" onClick={openCreate}>＋ 新增账号</button>

      {accounts.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3" style={{ minHeight: 'calc(100vh - 260px)' }}>
          <div className="text-6xl opacity-40">🍪</div>
          <p className="text-slate-600 font-semibold text-base">还没有 Cookie 账号</p>
          <p className="text-slate-400 text-sm">添加抖音账号 Cookie，才能开始采集内容</p>
        </div>
      ) : (
      <div className="space-y-3 max-w-2xl">
        {accounts.map(a => (
          <div key={a.id} className="glass-card p-4 flex items-center gap-4">
            <div className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0"
              style={{ background: 'linear-gradient(135deg,rgba(99,102,241,0.15),rgba(168,85,247,0.15))', color: '#6366f1' }}>
              {a.name[0]}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-700">{a.name}</span>
                {a.is_default && <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 font-semibold">默认</span>}
              </div>
              <div className="text-xs text-slate-400 truncate mt-0.5">{a.cookie.slice(0, 60)}...</div>
              {a.note && <div className="text-xs text-slate-400 mt-0.5">{a.note}</div>}
            </div>
            <div className="flex gap-2 flex-shrink-0">
              {!a.is_default && (
                <button onClick={() => cookiesApi.setDefault(a.id).then(load)} className="text-xs px-2.5 py-1 rounded-lg bg-indigo-50 text-indigo-500 border border-indigo-100">设为默认</button>
              )}
              <button onClick={() => openEdit(a)} className="text-xs px-2.5 py-1 rounded-lg bg-white/60 text-slate-500 border border-purple-50">编辑</button>
              <button onClick={() => cookiesApi.delete(a.id).then(load)} className="text-xs px-2.5 py-1 rounded-lg bg-red-50 text-red-400 border border-red-100">删除</button>
            </div>
          </div>
        ))}
      </div>
      )}
    </div>
  )
}

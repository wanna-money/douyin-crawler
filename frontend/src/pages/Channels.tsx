import { useEffect, useState } from 'react'
import { type NotifyChannel, channelsApi } from '../api/client'

interface ChatItem {
  chat_id: string
  name: string
  avatar: string
  description: string
}

const defaults = {
  name: '', channel_type: 'feishu_bot',
  app_id: '', app_secret: '', chat_id: '', webhook_url: '', is_default: false,
}

export default function Channels() {
  const [channels, setChannels] = useState<NotifyChannel[]>([])
  const [form, setForm] = useState({ ...defaults })
  const [editing, setEditing] = useState<NotifyChannel | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<number | null>(null)
  const [testResult, setTestResult] = useState<Record<number, { ok: boolean; msg: string } | null>>({})
  // 查询群列表
  const [loadingChats, setLoadingChats] = useState(false)
  const [chatList, setChatList] = useState<ChatItem[]>([])
  const [chatError, setChatError] = useState('')

  const load = () => channelsApi.list().then(setChannels)
  useEffect(() => { load() }, [])

  const openCreate = () => { setForm({ ...defaults }); setEditing(null); setShowForm(true); setChatList([]); setChatError('') }
  const openEdit = (ch: NotifyChannel) => {
    setForm({ name: ch.name, channel_type: ch.channel_type, app_id: ch.app_id,
      app_secret: ch.app_secret, chat_id: ch.chat_id, webhook_url: ch.webhook_url, is_default: ch.is_default })
    setEditing(ch); setShowForm(true); setChatList([]); setChatError('')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true)
    try {
      if (editing) await channelsApi.update(editing.id, form)
      else await channelsApi.create(form)
      setShowForm(false); load()
    } finally { setSaving(false) }
  }

  const handleTest = async (id: number) => {
    setTesting(id)
    try {
      const res = await channelsApi.test(id)
      const errMsg = res.error || '测试失败，请查看服务端日志'
      setTestResult(r => ({ ...r, [id]: { ok: res.ok, msg: res.ok ? '发送成功' : errMsg } }))
      // 成功 4 秒后消失，失败保留直到下次测试
      if (res.ok) setTimeout(() => setTestResult(r => ({ ...r, [id]: null })), 4000)
    } catch (e: any) {
      const msg = e?.response?.data?.detail ?? e?.message ?? '请求失败'
      setTestResult(r => ({ ...r, [id]: { ok: false, msg } }))
    } finally { setTesting(null) }
  }

  // 查询机器人所在群（需要先保存后才有 id，编辑模式下可用）
  const handleListChats = async () => {
    if (!editing) return
    setLoadingChats(true); setChatError(''); setChatList([])
    try {
      const chats = await channelsApi.listChats(editing.id)
      if (chats.length === 0) setChatError('该机器人暂未加入任何群，请先将机器人添加到飞书群')
      else setChatList(chats)
    } catch (e: any) {
      setChatError(e?.response?.data?.detail ?? '查询失败，请检查 App ID 和 App Secret')
    } finally { setLoadingChats(false) }
  }

  const inputCls = 'w-full border border-purple-100 rounded-xl px-3 py-2 text-sm bg-white/70 focus:outline-none focus:border-indigo-400'
  const labelCls = 'block text-sm font-semibold text-slate-600 mb-1'

  return (
    <div className="p-8">
      <h2 className="text-2xl font-extrabold mb-1" style={{ color: 'var(--text-primary)' }}>通知渠道</h2>
      <p className="text-sm text-slate-400 mb-5">配置飞书自建应用机器人，采集完成后自动推送卡片消息到群聊</p>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={() => { setShowForm(false); setChatList([]); setChatError('') }} />
          <div className="relative w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-2xl shadow-2xl"
            style={{ background: 'linear-gradient(160deg,rgba(255,255,255,0.98) 0%,rgba(248,246,255,0.98) 100%)' }}>
            <div className="sticky top-0 z-10 flex items-center justify-between px-7 py-5 border-b border-purple-50 rounded-t-2xl"
              style={{ background: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(10px)' }}>
              <div>
                <h3 className="text-lg font-extrabold" style={{ color: 'var(--text-primary)' }}>{editing ? '编辑渠道' : '新增渠道'}</h3>
                <p className="text-xs text-slate-400 mt-0.5">在飞书开放平台创建自建应用，开启「发送消息」权限，将机器人加入目标群</p>
              </div>
              <button onClick={() => { setShowForm(false); setChatList([]); setChatError('') }} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-purple-50 text-slate-400 hover:text-indigo-500 transition-colors text-lg">✕</button>
            </div>
            <div className="px-7 py-6">
              <form onSubmit={handleSubmit} className="space-y-3">
                <div>
                  <label className={labelCls}>渠道名称</label>
                  <input required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className={inputCls} placeholder="如：美食团队群" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={labelCls}>App ID</label>
                    <input required value={form.app_id} onChange={e => setForm(f => ({ ...f, app_id: e.target.value }))} className={inputCls} placeholder="cli_xxxxxx" />
                  </div>
                  <div>
                    <label className={labelCls}>App Secret</label>
                    <input required value={form.app_secret} onChange={e => setForm(f => ({ ...f, app_secret: e.target.value }))} className={inputCls} placeholder="xxxxxx" type="password" />
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className={labelCls + ' mb-0'}>群 Chat ID</label>
                    {editing && (
                      <button type="button" onClick={handleListChats} disabled={loadingChats}
                        className="text-xs px-2.5 py-1 rounded-lg bg-indigo-50 text-indigo-500 border border-indigo-100 disabled:opacity-50 hover:bg-indigo-100 transition-colors">
                        {loadingChats ? '查询中...' : '🔍 查询机器人所在群'}
                      </button>
                    )}
                  </div>
                  <input required value={form.chat_id} onChange={e => setForm(f => ({ ...f, chat_id: e.target.value }))} className={inputCls} placeholder="oc_xxxxxxxxxxxxxx" />
                  {!editing && <p className="text-xs text-slate-400 mt-1">保存后可点击「查询机器人所在群」自动填入 Chat ID</p>}
                  {chatError && <p className="text-xs text-red-400 mt-2">{chatError}</p>}
                  {chatList.length > 0 && (
                    <div className="mt-2 border border-purple-100 rounded-xl overflow-hidden">
                      <div className="px-3 py-2 bg-purple-50 text-xs text-purple-500 font-semibold">选择群 → 自动填入 Chat ID</div>
                      {chatList.map(chat => (
                        <button key={chat.chat_id} type="button" onClick={() => setForm(f => ({ ...f, chat_id: chat.chat_id }))}
                          className={`w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-purple-50 transition-colors border-t border-purple-50 ${form.chat_id === chat.chat_id ? 'bg-indigo-50' : 'bg-white'}`}>
                          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-100 to-purple-100 flex items-center justify-center text-xs font-bold text-indigo-500 flex-shrink-0">
                            {chat.name?.[0] ?? '群'}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-semibold text-slate-700 truncate">{chat.name}</div>
                            <div className="text-xs text-slate-400 truncate">{chat.chat_id}</div>
                          </div>
                          {form.chat_id === chat.chat_id && <span className="text-indigo-500 text-xs">✓ 已选</span>}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="is_default_ch" checked={form.is_default} onChange={e => setForm(f => ({ ...f, is_default: e.target.checked }))} className="w-4 h-4 accent-indigo-500" />
                  <label htmlFor="is_default_ch" className="text-sm text-slate-500">设为默认渠道</label>
                </div>
                <div className="flex gap-3 justify-end pt-3 border-t border-purple-50">
                  <button type="button" onClick={() => { setShowForm(false); setChatList([]); setChatError('') }} className="px-4 py-2 text-sm border border-purple-100 rounded-xl text-slate-500 bg-white/70">取消</button>
                  <button type="submit" disabled={saving} className="btn-primary">{saving ? '保存中...' : '保存'}</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      <button className="btn-primary mb-5" onClick={openCreate}>＋ 新增渠道</button>

      {channels.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3" style={{ minHeight: 'calc(100vh - 260px)' }}>
          <div className="text-6xl opacity-40">🔔</div>
          <p className="text-slate-600 font-semibold text-base">还没有通知渠道</p>
          <p className="text-slate-400 text-sm text-center max-w-xs">配置飞书自建应用机器人，采集结果将以卡片形式推送到群聊</p>
        </div>
      ) : (
      <div className="space-y-3 max-w-2xl">
        {channels.map(ch => (
          <div key={ch.id} className="glass-card p-4 flex items-center gap-4">
            <div className="w-10 h-10 rounded-full flex items-center justify-center text-lg flex-shrink-0"
              style={{ background: 'linear-gradient(135deg,rgba(99,102,241,0.15),rgba(168,85,247,0.15))' }}>
              🤖
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-slate-700">{ch.name}</span>
                {ch.is_default && <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 font-semibold">默认</span>}
                {testResult[ch.id]?.ok === true && <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">✓ 发送成功</span>}
                {testResult[ch.id]?.ok === false && <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-500">✗ 测试失败</span>}
              </div>
              <div className="text-xs text-slate-400 mt-0.5">
                {ch.app_id ? `App: ${ch.app_id}` : '未配置 App ID'}
                {ch.chat_id ? ` · 群: ${ch.chat_id}` : ' · 未配置群 ID'}
              </div>
              {testResult[ch.id]?.ok === false && (
                <div className="mt-1.5 text-xs text-red-500 bg-red-50 rounded-lg px-3 py-2 border border-red-100">
                  <span className="font-semibold">错误原因：</span>{testResult[ch.id]?.msg}
                </div>
              )}
            </div>
            <div className="flex gap-2 flex-shrink-0">
              <button onClick={() => handleTest(ch.id)} disabled={testing === ch.id}
                className="text-xs px-2.5 py-1 rounded-lg bg-indigo-50 text-indigo-500 border border-indigo-100 disabled:opacity-50">
                {testing === ch.id ? '测试中...' : '测试'}
              </button>
              {!ch.is_default && (
                <button onClick={() => channelsApi.setDefault(ch.id).then(load)}
                  className="text-xs px-2.5 py-1 rounded-lg bg-purple-50 text-purple-500 border border-purple-100">设为默认</button>
              )}
              <button onClick={() => openEdit(ch)}
                className="text-xs px-2.5 py-1 rounded-lg bg-white/60 text-slate-500 border border-purple-50">编辑</button>
              <button onClick={() => channelsApi.delete(ch.id).then(load)}
                className="text-xs px-2.5 py-1 rounded-lg bg-red-50 text-red-400 border border-red-100">删除</button>
            </div>
          </div>
        ))}
      </div>
      )}
    </div>
  )
}

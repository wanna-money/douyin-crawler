import { useState, useEffect } from 'react'
import { type SearchConfig, type NotifyChannel, configsApi, channelsApi } from '../api/client'
import SchedulePicker from './SchedulePicker'

type FormData = Omit<SearchConfig, 'id' | 'created_at'>

interface UserEntry {
  sec_uid: string
  limit: number
  nickname: string
  tab: 'post' | 'favorite'
  id_type: 'sec_uid' | 'douyin_id'
}

const defaults: FormData = {
  name: '', query: '', search_type: 'search',
  sort_type: 0, publish_time: 0, content_type: 0,
  filter_duration: '', limit: 50, enabled: true,
  cron: '0 9 * * *', feishu_webhook: '', channel_id: null,
  llm_filter_enabled: false,
}

interface Props {
  initial?: SearchConfig
  onSaved: () => void
  onCancel: () => void
}

function SectionTitle({ icon, title }: { icon: string; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-3 mt-1">
      <span className="text-sm">{icon}</span>
      <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">{title}</span>
      <div className="flex-1 h-px bg-purple-100" />
    </div>
  )
}

function parseUserEntries(query: string): UserEntry[] {
  try {
    const parsed = JSON.parse(query)
    if (Array.isArray(parsed)) return parsed.map(e => ({ tab: 'post' as const, id_type: 'douyin_id' as const, ...e }))
  } catch {}
  return [{ sec_uid: query, limit: 10, nickname: '', tab: 'post' as const, id_type: 'douyin_id' as const }]
}

function serializeUserEntries(entries: UserEntry[]): string {
  return JSON.stringify(entries.filter(e => e.sec_uid.trim()))
}

export default function ConfigForm({ initial, onSaved, onCancel }: Props) {
  const [form, setForm] = useState<FormData>(initial ? { ...initial } : { ...defaults })
  const [saving, setSaving] = useState(false)
  const [channels, setChannels] = useState<NotifyChannel[]>([])
  const [userEntries, setUserEntries] = useState<UserEntry[]>(() =>
    initial?.search_type === 'user' ? parseUserEntries(initial.query) : [{ sec_uid: '', limit: 10, nickname: '', tab: 'post' as const, id_type: 'douyin_id' as const }]
  )

  useEffect(() => { channelsApi.list().then(setChannels) }, [])

  const set = (key: keyof FormData, val: unknown) => setForm(f => ({ ...f, [key]: val }))

  const handleSearchTypeChange = (newType: string) => {
    if (newType === 'user') {
      setUserEntries([{ sec_uid: '', limit: 10, nickname: '', tab: 'post' as const, id_type: 'douyin_id' as const }])
      setForm(f => ({ ...f, search_type: newType, query: '[]' }))
    } else {
      setForm(f => ({ ...f, search_type: newType, query: '' }))
    }
  }

  const updateUserEntry = (idx: number, field: keyof UserEntry, val: string | number) => {
    const updated = userEntries.map((e, i) => i === idx ? { ...e, [field]: val } : e)
    setUserEntries(updated)
    setForm(f => ({ ...f, query: serializeUserEntries(updated) }))
  }

  const addUserEntry = () => {
    const updated = [...userEntries, { sec_uid: '', limit: 10, nickname: '', tab: 'post' as const, id_type: 'douyin_id' as const }]
    setUserEntries(updated)
    setForm(f => ({ ...f, query: serializeUserEntries(updated) }))
  }

  const removeUserEntry = (idx: number) => {
    const filtered = userEntries.filter((_, i) => i !== idx)
    const next = filtered.length ? filtered : [{ sec_uid: '', limit: 10, nickname: '', tab: 'post' as const, id_type: 'douyin_id' as const }]
    setUserEntries(next)
    setForm(f => ({ ...f, query: serializeUserEntries(next) }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      if (initial?.id) await configsApi.update(initial.id, form)
      else await configsApi.create(form)
      onSaved()
    } finally {
      setSaving(false)
    }
  }

  const inputCls = 'w-full border border-purple-100 rounded-xl px-3 py-2 text-sm bg-white/70 focus:outline-none focus:border-indigo-400 transition-colors'
  const labelCls = 'block text-sm font-semibold text-slate-600 mb-1'

  return (
    <form onSubmit={handleSubmit} className="space-y-4">

      {/* ── 基础信息 ── */}
      <SectionTitle icon="📝" title="基础信息" />
      <div className="grid grid-cols-2 gap-4">
        <label className="block">
          <span className={labelCls}>配置名称</span>
          <input required value={form.name} onChange={e => set('name', e.target.value)}
            className={inputCls} placeholder="给这个配置起个名字" />
        </label>
        <label className="block">
          <span className={labelCls}>搜索类型</span>
          <select value={form.search_type} onChange={e => handleSearchTypeChange(e.target.value)} className={inputCls}>
            <option value="search">关键词搜索</option>
            <option value="user">用户主页</option>
          </select>
        </label>
      </div>

      {form.search_type === 'user' ? (
        <div>
          <span className={labelCls}>用户列表</span>
          <div className="space-y-2">
            {userEntries.map((entry, idx) => (
              <div key={idx} className="flex gap-2 items-center">
                <select
                  value={entry.id_type}
                  onChange={e => updateUserEntry(idx, 'id_type', e.target.value)}
                  className="w-24 border border-purple-100 rounded-xl px-2 py-2 text-sm bg-white/70 focus:outline-none focus:border-indigo-400 transition-colors"
                  title="输入类型"
                >
                  <option value="sec_uid">主页链接</option>
                  <option value="douyin_id">抖音号</option>
                </select>
                <input
                  value={entry.sec_uid}
                  onChange={e => updateUserEntry(idx, 'sec_uid', e.target.value)}
                  className={`flex-1 ${inputCls}`}
                  placeholder={entry.id_type === 'douyin_id' ? '输入抖音号，如 71158770' : '粘贴主页链接或 sec_uid'}
                  required={idx === 0}
                />
                <input
                  value={entry.nickname}
                  onChange={e => updateUserEntry(idx, 'nickname', e.target.value)}
                  className="w-20 border border-purple-100 rounded-xl px-2 py-2 text-sm bg-white/70 focus:outline-none focus:border-indigo-400 transition-colors"
                  placeholder="备注名"
                />
                <select
                  value={entry.tab}
                  onChange={e => updateUserEntry(idx, 'tab', e.target.value)}
                  className="w-20 border border-purple-100 rounded-xl px-2 py-2 text-sm bg-white/70 focus:outline-none focus:border-indigo-400 transition-colors"
                  title="采集类型"
                >
                  <option value="post">作品</option>
                  <option value="favorite">收藏</option>
                </select>
                <input
                  type="number"
                  value={entry.limit}
                  onChange={e => updateUserEntry(idx, 'limit', Number(e.target.value))}
                  min={1} max={500}
                  className="w-16 border border-purple-100 rounded-xl px-2 py-2 text-sm bg-white/70 focus:outline-none focus:border-indigo-400 transition-colors"
                  title="最多采集数量"
                />
                <button
                  type="button"
                  onClick={() => removeUserEntry(idx)}
                  className="text-xs px-2 py-1.5 rounded-lg text-red-400 hover:bg-red-50 transition-colors"
                  title="删除该用户"
                >✕</button>
              </div>
            ))}
            <button
              type="button"
              onClick={addUserEntry}
              className="text-xs px-3 py-1.5 rounded-lg border border-purple-100 text-indigo-500 bg-white/60 hover:bg-white/80 transition-colors"
            >＋ 添加用户</button>
          </div>
          <p className="text-xs text-slate-400 mt-1.5">
            支持两种方式：① 抖音号（如 71158770）② 主页链接（douyin.com/user/MS4w...）或 sec_uid
          </p>
        </div>
      ) : (
        <label className="block">
          <span className={labelCls}>关键词</span>
          <input required value={form.query} onChange={e => set('query', e.target.value)}
            className={inputCls} placeholder="美食探店" />
        </label>
      )}

      {/* ── 采集规则 ── */}
      <SectionTitle icon="⚙️" title="采集规则" />
      {form.search_type === 'user' ? (
        <p className="text-xs text-slate-400 -mt-2">用户模式下，每个用户的采集数量单独配置（见上方）。</p>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          <label className="block">
            <span className={labelCls}>排序方式</span>
            <select value={form.sort_type} onChange={e => set('sort_type', Number(e.target.value))} className={inputCls}>
              <option value={0}>综合</option>
              <option value={1}>最多点赞</option>
              <option value={2}>最新</option>
            </select>
          </label>
          <label className="block">
            <span className={labelCls}>发布时间</span>
            <select value={form.publish_time} onChange={e => set('publish_time', Number(e.target.value))} className={inputCls}>
              <option value={0}>不限</option>
              <option value={1}>一天内</option>
              <option value={7}>一周内</option>
              <option value={180}>半年内</option>
            </select>
          </label>
          <label className="block">
            <span className={labelCls}>内容类型</span>
            <select value={form.content_type} onChange={e => set('content_type', Number(e.target.value))} className={inputCls}>
              <option value={0}>不限</option>
              <option value={1}>视频</option>
              <option value={2}>图文</option>
            </select>
          </label>
          <label className="block">
            <span className={labelCls}>采集数量上限</span>
            <input type="number" value={form.limit} onChange={e => set('limit', Number(e.target.value))}
              min={1} max={500} className={inputCls} />
          </label>
        </div>
      )}

      {/* ── 定时与推送 ── */}
      <SectionTitle icon="🔔" title="定时与推送" />
      <div>
        <span className={labelCls}>执行时间</span>
        <div className="rounded-2xl p-4 border border-purple-100 bg-white/50">
          <SchedulePicker key={initial?.id ?? 'new'} value={form.cron} onChange={cron => set('cron', cron)} />
        </div>
      </div>
      <label className="block">
        <span className={labelCls}>通知渠道</span>
        <select value={form.channel_id ?? ''} onChange={e => set('channel_id', e.target.value ? Number(e.target.value) : null)} className={inputCls}>
          <option value="">— 使用默认渠道 —</option>
          {channels.map(ch => (
            <option key={ch.id} value={ch.id}>{ch.name}{ch.is_default ? ' (默认)' : ''}</option>
          ))}
        </select>
      </label>

      {/* 开关 */}
      <div className="flex flex-col gap-2 pt-1">
        <label className="flex items-center gap-2.5 cursor-pointer group">
          <input type="checkbox" id="enabled" checked={form.enabled}
            onChange={e => set('enabled', e.target.checked)} className="w-4 h-4 accent-indigo-500" />
          <span className="text-sm text-slate-600 group-hover:text-indigo-600 transition-colors">启用定时任务</span>
        </label>
        <label className="flex items-center gap-2.5 cursor-pointer group">
          <input type="checkbox" id="llm_filter" checked={form.llm_filter_enabled}
            onChange={e => set('llm_filter_enabled', e.target.checked)} className="w-4 h-4 accent-indigo-500" />
          <span className="text-sm text-slate-600 group-hover:text-indigo-600 transition-colors">
            启用 LLM 相关性过滤
            <span className="ml-1.5 text-xs text-slate-400">（需先在「LLM 配置」页设置默认模型）</span>
          </span>
        </label>
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-3 justify-end pt-3 border-t border-purple-50">
        <button type="button" onClick={onCancel}
          className="px-5 py-2 text-sm border border-purple-100 rounded-xl text-slate-500 bg-white/70 hover:bg-white/90 transition-colors">
          取消
        </button>
        <button type="submit" disabled={saving} className="btn-primary">
          {saving ? '保存中...' : (initial ? '保存修改' : '创建配置')}
        </button>
      </div>
    </form>
  )
}

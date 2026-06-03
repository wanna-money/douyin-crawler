import { useState, useEffect } from 'react'
import { type SearchConfig, type NotifyChannel, configsApi, channelsApi } from '../api/client'
import SchedulePicker from './SchedulePicker'

type FormData = Omit<SearchConfig, 'id' | 'created_at'>

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

export default function ConfigForm({ initial, onSaved, onCancel }: Props) {
  const [form, setForm] = useState<FormData>(initial ? { ...initial } : { ...defaults })
  const [saving, setSaving] = useState(false)
  const [channels, setChannels] = useState<NotifyChannel[]>([])

  useEffect(() => { channelsApi.list().then(setChannels) }, [])

  const set = (key: keyof FormData, val: unknown) => setForm(f => ({ ...f, [key]: val }))

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
          <span className={labelCls}>关键词 / 话题 ID</span>
          <input required value={form.query} onChange={e => set('query', e.target.value)}
            className={inputCls} placeholder="美食探店 或 话题ch_id" />
        </label>
      </div>

      {/* ── 采集规则 ── */}
      <SectionTitle icon="⚙️" title="采集规则" />
      <div className="grid grid-cols-2 gap-4">
        <label className="block">
          <span className={labelCls}>搜索类型</span>
          <select value={form.search_type} onChange={e => set('search_type', e.target.value)} className={inputCls}>
            <option value="search">关键词搜索</option>
            <option value="hashtag">话题抓取</option>
          </select>
        </label>
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
        <label className="block col-span-2">
          <span className={labelCls}>采集数量上限</span>
          <input type="number" value={form.limit} onChange={e => set('limit', Number(e.target.value))}
            min={1} max={500} className={inputCls} />
        </label>
      </div>

      {/* ── 定时与推送 ── */}
      <SectionTitle icon="🔔" title="定时与推送" />
      <div>
        <span className={labelCls}>执行时间</span>
        <div className="rounded-2xl p-4 border border-purple-100 bg-white/50">
          <SchedulePicker value={form.cron} onChange={cron => set('cron', cron)} />
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

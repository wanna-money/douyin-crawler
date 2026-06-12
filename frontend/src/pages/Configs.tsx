import { useEffect, useState } from 'react'
import { type SearchConfig, type TaskRecord, configsApi, tasksApi } from '../api/client'
import ConfigForm from '../components/ConfigForm'
import { toast } from '../components/Toast'

export default function Configs() {
  const [configs, setConfigs] = useState<SearchConfig[]>([])
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<SearchConfig | undefined>()
  const [triggering, setTriggering] = useState<number | null>(null)
  const [runningConfigIds, setRunningConfigIds] = useState<Set<number>>(new Set())
  const [togglingIds, setTogglingIds] = useState<Set<number>>(new Set())

  const load = () => configsApi.list().then(setConfigs)

  const loadRunning = () =>
    tasksApi.list().then((tasks: TaskRecord[]) => {
      setRunningConfigIds(new Set(
        tasks.filter(t => t.status === 'running').map(t => t.config_id)
      ))
    })

  useEffect(() => {
    load()
    loadRunning()
    const t = setInterval(loadRunning, 5000)
    return () => clearInterval(t)
  }, [])

  const handleTrigger = async (id: number) => {
    setTriggering(id)
    try { await configsApi.trigger(id); toast.success('任务已启动') }
    finally { setTriggering(null) }
  }

  const handleToggleEnabled = async (c: SearchConfig) => {
    setTogglingIds(prev => new Set(prev).add(c.id))
    try {
      await configsApi.update(c.id, { enabled: !c.enabled })
      setConfigs(prev => prev.map(x => x.id === c.id ? { ...x, enabled: !c.enabled } : x))
      toast.success(c.enabled ? '已停用定时任务' : '已启用定时任务')
    } finally {
      setTogglingIds(prev => { const s = new Set(prev); s.delete(c.id); return s })
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确认删除？')) return
    await configsApi.delete(id)
    toast.success('配置已删除')
    load()
  }

  const closeForm = () => { setShowForm(false); setEditing(undefined) }
  const isOpen = showForm || !!editing

  return (
    <div className="p-4 md:p-8">
      {/* 页头 */}
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-2xl font-extrabold" style={{ color: 'var(--text-primary)' }}>搜索配置</h2>
        <button className="btn-primary" onClick={() => setShowForm(true)}>＋ 新建配置</button>
      </div>
      <p className="text-sm text-slate-400 mb-6">管理关键词采集任务，支持定时自动执行</p>

      {/* 卡片列表 */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {configs.length === 0 && (
          <div className="col-span-2 flex flex-col items-center justify-center py-20 gap-4">
            <div className="text-6xl opacity-40">🔍</div>
            <div className="text-center">
              <p className="text-slate-600 font-semibold text-base">还没有搜索配置</p>
              <p className="text-slate-400 text-sm mt-1">创建第一个配置，开始自动采集抖音内容</p>
            </div>
          </div>
        )}
        {configs.map(c => (
          <div key={c.id} className="glass-card p-5">
            <div className="flex items-start justify-between mb-3">
              <div>
                <div className="font-bold text-[15px]" style={{ color: 'var(--text-primary)' }}>{c.name}</div>
                <div className="flex gap-1.5 mt-1.5 flex-wrap items-center">
                  {/* 启用/禁用开关 */}
                  <button
                    type="button"
                    disabled={togglingIds.has(c.id)}
                    onClick={() => handleToggleEnabled(c)}
                    title={c.enabled ? '点击停用' : '点击启用'}
                    className={`relative inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full font-semibold transition-all cursor-pointer select-none
                      ${c.enabled ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200' : 'bg-gray-100 text-gray-400 hover:bg-gray-200'}
                      ${togglingIds.has(c.id) ? 'opacity-50 cursor-not-allowed' : ''}
                    `}
                  >
                    <span className={`inline-block w-1.5 h-1.5 rounded-full ${c.enabled ? 'bg-emerald-500' : 'bg-gray-400'}`} />
                    {togglingIds.has(c.id) ? '切换中...' : (c.enabled ? '已启用' : '已停用')}
                  </button>
                  <span className="text-xs px-2 py-0.5 rounded-full font-semibold bg-purple-100 text-purple-700">
                    {c.search_type === 'user' ? '👤 用户主页' : '关键词'}
                  </span>
                  {c.llm_filter_enabled && (
                    <span className="text-xs px-2 py-0.5 rounded-full font-semibold bg-blue-100 text-blue-600">🤖 LLM过滤</span>
                  )}
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 mb-3">
              {(() => {
                let queryLabel = c.query
                let limitLabel = `🎯 ${c.limit} 条`
                if (c.search_type === 'user') {
                  try {
                    const entries = JSON.parse(c.query)
                    if (Array.isArray(entries)) {
                      queryLabel = entries
                        .map((e: { nickname?: string; sec_uid?: string }) => e.nickname || (e.sec_uid ? e.sec_uid.slice(0, 8) + '...' : ''))
                        .filter(Boolean)
                        .join('、') || c.query
                      const total = entries.reduce((sum: number, e: { limit?: number }) => sum + (e.limit ?? 10), 0)
                      limitLabel = `🎯 ${total} 条`
                    }
                  } catch {}
                }
                return [
                  `🔍 ${queryLabel}`,
                  `📅 ${c.publish_time === 0 ? '不限' : c.publish_time === 1 ? '天内' : c.publish_time === 7 ? '周内' : '半年内'}`,
                  limitLabel,
                ].map(label => (
                  <span key={label} className="text-xs text-slate-500 bg-white/60 px-2.5 py-1 rounded-lg border border-purple-50">{label}</span>
                ))
              })()}
            </div>
            <div className={`text-xs rounded-lg px-3 py-1.5 font-mono mb-3 flex items-center gap-2 ${c.enabled ? 'text-indigo-500 bg-indigo-50/60' : 'text-gray-400 bg-gray-50/60 opacity-60'}`}>
              <span>{c.cron}</span>
              {!c.enabled && <span className="font-sans font-semibold text-gray-400 opacity-80">已停用</span>}
            </div>
            <div className="flex gap-2 pt-3 border-t border-purple-50">
              {(() => {
                const isRunning = runningConfigIds.has(c.id)
                const isTriggering = triggering === c.id
                const disabled = isRunning || isTriggering
                return (
                  <button
                    onClick={() => handleTrigger(c.id)}
                    disabled={disabled}
                    className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
                    style={{ fontSize: '12px', padding: '6px 14px' }}
                    title={isRunning ? '该配置正在运行中，请等待完成' : ''}
                  >
                    {isRunning ? '◎ 运行中...' : isTriggering ? '启动中...' : '▶ 立即执行'}
                  </button>
                )
              })()}
              <button onClick={() => setEditing(c)} className="text-xs px-3 py-1.5 rounded-lg bg-white/60 text-slate-500 border border-purple-50 hover:bg-white/80 transition-colors">编辑</button>
              <button onClick={() => handleDelete(c.id)} className="text-xs px-3 py-1.5 rounded-lg bg-red-50/60 text-red-400 border border-red-100 hover:bg-red-50 transition-colors">删除</button>
            </div>
          </div>
        ))}
      </div>

      {/* Modal */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* 遮罩 */}
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={closeForm} />
          {/* 弹窗 */}
          <div
            className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl shadow-2xl"
            style={{
              background: 'linear-gradient(160deg,rgba(255,255,255,0.98) 0%,rgba(248,246,255,0.98) 100%)',
              backdropFilter: 'blur(20px)',
            }}
          >
            <div className="sticky top-0 z-10 flex items-center justify-between px-4 md:px-8 py-4 md:py-5 border-b border-purple-50 rounded-t-2xl"
              style={{ background: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(10px)' }}>
              <div>
                <h3 className="text-lg font-extrabold" style={{ color: 'var(--text-primary)' }}>
                  {editing ? '编辑配置' : '新建配置'}
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  {editing ? `正在编辑「${editing.name}」` : '填写基本信息和采集规则'}
                </p>
              </div>
              <button onClick={closeForm} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-purple-50 text-slate-400 hover:text-indigo-500 transition-colors text-lg">✕</button>
            </div>
            <div className="px-4 md:px-8 py-5 md:py-6">
              <ConfigForm
                initial={editing}
                onSaved={() => { closeForm(); load() }}
                onCancel={closeForm}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

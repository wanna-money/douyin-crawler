import { useEffect, useState } from 'react'
import {
  type TaskRecord, type SearchConfig, type LogEntry,
  tasksApi, configsApi, logsApi,
} from '../api/client'
import { toast } from '../components/Toast'

const STATUS_MAP: Record<string, { label: string; cls: string; dot: string }> = {
  pending: { label: '等待',   cls: 'bg-gray-100 text-gray-500',       dot: '○' },
  running: { label: '运行中', cls: 'bg-yellow-100 text-yellow-700',   dot: '◎' },
  done:    { label: '完成',   cls: 'bg-emerald-100 text-emerald-700', dot: '●' },
  failed:  { label: '失败',   cls: 'bg-red-100 text-red-600',         dot: '✕' },
}

function LogTable({ logs, loading }: { logs: LogEntry[]; loading: boolean }) {
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const filtered = logs.filter(e =>
    (!typeFilter || e.media_type === typeFilter) &&
    (!statusFilter || (statusFilter === 'ok' ? e.downloaded : !e.downloaded))
  )

  if (loading) return <div className="py-8 text-center text-xs text-slate-400">加载中...</div>
  if (logs.length === 0) return <div className="py-8 text-center text-xs text-slate-400">本次任务暂无采集记录</div>

  return (
    <div>
      {/* 过滤栏 */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-purple-50">
        <span className="text-xs text-slate-400">{filtered.length} / {logs.length} 条</span>
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="text-xs border border-purple-100 rounded-lg px-2 py-1 bg-white/70 focus:outline-none"
        >
          <option value="">全部类型</option>
          <option value="video">视频</option>
          <option value="image">图文</option>
        </select>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="text-xs border border-purple-100 rounded-lg px-2 py-1 bg-white/70 focus:outline-none"
        >
          <option value="">全部状态</option>
          <option value="ok">下载成功</option>
          <option value="fail">下载失败</option>
        </select>
      </div>
      {/* 日志行 */}
      <div className="divide-y divide-purple-50 overflow-hidden">
        {filtered.length === 0 ? (
          <div className="py-6 text-center text-xs text-slate-400">无匹配记录</div>
        ) : filtered.map((e, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-2.5 text-xs hover:bg-white/40 transition-colors min-w-0">
            <span className="text-slate-300 font-mono shrink-0 w-[72px]">{new Date(e.ts).toLocaleTimeString('zh-CN')}</span>
            <span className={`shrink-0 px-1.5 py-0.5 rounded text-[11px] font-semibold ${e.media_type === 'video' ? 'bg-blue-50 text-blue-600' : 'bg-pink-50 text-pink-500'}`}>
              {e.media_type === 'video' ? '视频' : '图文'}
            </span>
            <span className="text-indigo-500 shrink-0 font-medium w-20 truncate">{e.author}</span>
            <span className="text-slate-600 min-w-0 flex-1 truncate" title={e.desc}>{e.desc || '（无描述）'}</span>
            <div className="flex items-center gap-2 shrink-0">
              {e.downloaded
                ? <span className="text-emerald-500 font-semibold">✓ 已下载</span>
                : <span className="text-red-400">✗ 失败</span>}
              {e.sent && <span className="text-indigo-400">· 已推送</span>}
            </div>
            {e.error && (
              <span className="text-red-400 truncate max-w-[140px] shrink-0" title={e.error}>{e.error}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function DetailPanel({ task, onClose }: { task: TaskRecord; onClose: () => void }) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    logsApi.byTask(task.id).then(setLogs).finally(() => setLoading(false))
  }, [task.id])

  return (
    <div className="px-4 py-3" style={{ borderBottom: '1px solid rgba(99,102,241,0.05)' }}>
      <div className="rounded-xl border border-purple-100 overflow-hidden" style={{ background: 'rgba(249,248,255,0.9)' }}>
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-purple-50" style={{ background: 'rgba(99,102,241,0.04)' }}>
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold text-indigo-500">采集明细</span>
            {task.note && (
              <span className="text-xs text-amber-600 bg-amber-50 px-2 py-0.5 rounded">⚠ {task.note}</span>
            )}
          </div>
          <button onClick={onClose} className="text-xs text-slate-400 hover:text-slate-600 px-2 py-0.5 rounded hover:bg-white/60 transition-colors">
            收起 ▲
          </button>
        </div>
        <LogTable logs={logs} loading={loading} />
      </div>
    </div>
  )
}

export default function Tasks() {
  const [tasks, setTasks] = useState<TaskRecord[]>([])
  const [configMap, setConfigMap] = useState<Record<number, string>>({})
  const [clearing, setClearing] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [filter, setFilter] = useState({
    configId: '',
    status: '',
    dateFrom: '',
    dateTo: '',
    hasData: '',
  })

  const fetchAll = () =>
    Promise.all([tasksApi.list(), configsApi.list()]).then(([ts, cs]) => {
      setTasks(ts)
      setConfigMap(Object.fromEntries(cs.map((c: SearchConfig) => [c.id, c.name])))
    })
  useEffect(() => {
    fetchAll()
    const t = setInterval(fetchAll, 5000)
    return () => clearInterval(t)
  }, [])

  const handleDelete = async (id: number) => {
    if (expandedId === id) setExpandedId(null)
    await tasksApi.delete(id)
    toast.success('已删除')
    fetchAll()
  }

  const handleClear = async () => {
    if (!confirm(`确认清空全部 ${tasks.length} 条任务记录？`)) return
    setClearing(true)
    setExpandedId(null)
    try {
      await tasksApi.clear()
      toast.success('已清空任务记录')
      fetchAll()
    } finally {
      setClearing(false)
    }
  }

  const toggleDetail = (id: number) => setExpandedId(prev => prev === id ? null : id)

  const filtered = tasks.filter(t => {
    if (filter.configId && t.config_id !== Number(filter.configId)) return false
    if (filter.status && t.status !== filter.status) return false
    if (filter.hasData === 'yes' && t.total === 0) return false
    if (filter.hasData === 'no' && t.total > 0) return false
    const d = t.created_at.slice(0, 10)
    if (filter.dateFrom && d < filter.dateFrom) return false
    if (filter.dateTo && d > filter.dateTo) return false
    return true
  })

  const hasFilter = filter.configId || filter.status || filter.dateFrom || filter.dateTo || filter.hasData
  const selCls = 'text-xs border border-purple-100 rounded-xl px-3 py-1.5 bg-white/70 focus:outline-none focus:border-indigo-400'
  const inputCls = 'text-xs border border-purple-100 rounded-xl px-3 py-1.5 bg-white/70 focus:outline-none focus:border-indigo-400 w-32'

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-2xl font-extrabold" style={{ color: 'var(--text-primary)' }}>任务记录</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400 bg-white/60 px-3 py-1.5 rounded-full border border-purple-50">每 5 秒自动刷新</span>
          <button
            onClick={() => { setRefreshing(true); fetchAll().finally(() => setRefreshing(false)) }}
            disabled={refreshing}
            className="text-xs px-3 py-1.5 rounded-xl bg-white/60 text-indigo-500 border border-purple-100 hover:bg-indigo-50 transition-colors disabled:opacity-60"
            title="手动刷新"
          >
            <span className={refreshing ? 'inline-block animate-spin' : 'inline-block'}>↻</span>
            {' '}刷新
          </button>
          {tasks.length > 0 && (
            <button
              onClick={handleClear}
              disabled={clearing}
              className="text-xs px-3 py-1.5 rounded-xl bg-red-50/80 text-red-400 border border-red-100 hover:bg-red-50 transition-colors disabled:opacity-50"
            >
              {clearing ? '清空中...' : '🗑 清空全部'}
            </button>
          )}
        </div>
      </div>
      <p className="text-sm text-slate-400 mb-6">每次手动触发或定时执行的采集任务，点击「详情」查看采集明细</p>

      {tasks.length === 0 ? (
        <div className="glass-card flex flex-col items-center justify-center py-20 gap-4">
          <div className="text-6xl opacity-40">📋</div>
          <div className="text-center">
            <p className="text-slate-600 font-semibold text-base">暂无任务记录</p>
            <p className="text-slate-400 text-sm mt-1">在「搜索配置」页点击「立即执行」触发第一次采集</p>
          </div>
        </div>
      ) : (
        <>
          {/* 筛选栏 */}
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <select
              value={filter.configId}
              onChange={e => setFilter(f => ({ ...f, configId: e.target.value }))}
              className={selCls}
            >
              <option value="">全部配置</option>
              {Object.entries(configMap).map(([id, name]) => (
                <option key={id} value={id}>{name}</option>
              ))}
            </select>
            <select
              value={filter.status}
              onChange={e => setFilter(f => ({ ...f, status: e.target.value }))}
              className={selCls}
            >
              <option value="">全部状态</option>
              <option value="done">完成</option>
              <option value="failed">失败</option>
              <option value="running">运行中</option>
            </select>
            <select
              value={filter.hasData}
              onChange={e => setFilter(f => ({ ...f, hasData: e.target.value }))}
              className={selCls}
            >
              <option value="">全部结果</option>
              <option value="yes">有数据</option>
              <option value="no">无数据</option>
            </select>
            <input
              type="date"
              value={filter.dateFrom}
              onChange={e => setFilter(f => ({ ...f, dateFrom: e.target.value }))}
              className={inputCls}
              title="开始日期"
            />
            <span className="text-xs text-slate-400">—</span>
            <input
              type="date"
              value={filter.dateTo}
              onChange={e => setFilter(f => ({ ...f, dateTo: e.target.value }))}
              className={inputCls}
              title="结束日期"
            />
            {hasFilter && (
              <button
                onClick={() => setFilter({ configId: '', status: '', dateFrom: '', dateTo: '', hasData: '' })}
                className="text-xs px-3 py-1.5 rounded-xl text-indigo-500 bg-indigo-50 border border-indigo-100 hover:bg-indigo-100 transition-colors"
              >
                清除筛选
              </button>
            )}
            <span className="text-xs text-slate-400 ml-1">
              {hasFilter ? `${filtered.length} / ${tasks.length} 条` : `共 ${tasks.length} 条`}
            </span>
          </div>

          <div className="glass-card overflow-hidden">
            {filtered.length === 0 ? (
              <div className="py-14 text-center text-slate-400 text-sm">无匹配记录</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(99,102,241,0.08)', background: 'rgba(99,102,241,0.03)' }}>
                    {['ID', '配置', '状态', '新内容', '下载', '推送', '备注', '时间', '操作'].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-bold text-purple-400 uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(t => {
                    const s = STATUS_MAP[t.status] ?? { label: t.status, cls: 'bg-gray-100', dot: '·' }
                    const configName = configMap[t.config_id] ?? `#${t.config_id}`
                    const isExpanded = expandedId === t.id
                    return (
                      <>
                        <tr
                          key={t.id}
                          style={{ borderBottom: isExpanded ? 'none' : '1px solid rgba(99,102,241,0.05)' }}
                          className={`transition-colors ${isExpanded ? 'bg-indigo-50/30' : 'hover:bg-white/40'}`}
                        >
                          <td className="px-4 py-3 text-purple-300 text-xs font-mono">#{t.id}</td>
                          <td className="px-4 py-3">
                            <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-lg truncate block">{configName}</span>
                          </td>
                          <td className="px-4 py-3">
                            <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${s.cls}`}>{s.dot} {s.label}</span>
                          </td>
                          <td className="px-4 py-3 text-slate-600 tabular-nums whitespace-nowrap">{t.total}</td>
                          <td className="px-4 py-3 tabular-nums whitespace-nowrap">
                            <span className={t.downloaded < t.total && t.total > 0 ? 'text-red-400' : 'text-slate-600'}>
                              {t.downloaded}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-slate-600 tabular-nums whitespace-nowrap">{t.sent}</td>
                          <td className="px-4 py-3 max-w-xs">
                            {(t.note || t.status === 'failed') ? (
                              <span
                                className={`text-xs truncate block ${t.status === 'failed' ? 'text-red-400' : 'text-amber-600'}`}
                                title={t.status === 'failed' ? (t.error || t.note || '任务失败') : t.note}
                              >
                                {t.status === 'failed' ? (t.error || t.note || '任务失败') : t.note}
                              </span>
                            ) : (
                              <span className="text-xs text-slate-300">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-slate-400 text-xs whitespace-nowrap">{new Date(t.created_at).toLocaleString('zh-CN')}</td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-1.5">
                              <button
                                onClick={() => toggleDetail(t.id)}
                                className={`text-xs px-2 py-1 rounded-lg border transition-colors ${isExpanded
                                  ? 'bg-indigo-100 text-indigo-600 border-indigo-200'
                                  : 'bg-indigo-50 text-indigo-500 border-indigo-100 hover:bg-indigo-100'}`}
                              >
                                {isExpanded ? '收起' : '详情'}
                              </button>
                              <button
                                onClick={() => handleDelete(t.id)}
                                className="text-xs px-2 py-1 rounded-lg bg-red-50 text-red-400 border border-red-100 hover:bg-red-100 transition-colors"
                              >
                                删除
                              </button>
                            </div>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr key={`detail-${t.id}`}>
                            <td colSpan={9} style={{ padding: 0, maxWidth: 0 }}>
                              <div style={{ width: '100%', overflow: 'hidden' }}>
                                <DetailPanel task={t} onClose={() => setExpandedId(null)} />
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}

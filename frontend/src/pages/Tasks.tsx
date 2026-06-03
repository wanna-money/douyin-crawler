import { useEffect, useState } from 'react'
import { type TaskRecord, type SearchConfig, tasksApi, configsApi } from '../api/client'
import { toast } from '../components/Toast'

const STATUS_MAP: Record<string, { label: string; cls: string; dot: string }> = {
  pending: { label: '等待',   cls: 'bg-gray-100 text-gray-500',       dot: '○' },
  running: { label: '运行中', cls: 'bg-yellow-100 text-yellow-700',   dot: '◎' },
  done:    { label: '完成',   cls: 'bg-emerald-100 text-emerald-700', dot: '●' },
  failed:  { label: '失败',   cls: 'bg-red-100 text-red-600',         dot: '✕' },
}

export default function Tasks() {
  const [tasks, setTasks] = useState<TaskRecord[]>([])
  const [configMap, setConfigMap] = useState<Record<number, string>>({})
  const [clearing, setClearing] = useState(false)

  const fetchAll = () => Promise.all([tasksApi.list(), configsApi.list()])
    .then(([ts, cs]) => {
      setTasks(ts)
      setConfigMap(Object.fromEntries(cs.map((c: SearchConfig) => [c.id, c.name])))
    })

  useEffect(() => {
    fetchAll()
    const t = setInterval(fetchAll, 5000)
    return () => clearInterval(t)
  }, [])

  const handleDelete = async (id: number) => {
    await tasksApi.delete(id)
    toast.success('已删除')
    fetchAll()
  }

  const handleClear = async () => {
    if (!confirm(`确认清空全部 ${tasks.length} 条任务记录？`)) return
    setClearing(true)
    try {
      await tasksApi.clear()
      toast.success('已清空任务记录')
      fetchAll()
    } finally {
      setClearing(false)
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-2xl font-extrabold" style={{ color: 'var(--text-primary)' }}>任务记录</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400 bg-white/60 px-3 py-1.5 rounded-full border border-purple-50">每 5 秒自动刷新</span>
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
      <p className="text-sm text-slate-400 mb-6">每次手动触发或定时执行的采集任务明细</p>

      {tasks.length === 0 ? (
        <div className="glass-card flex flex-col items-center justify-center py-20 gap-4">
          <div className="text-6xl opacity-40">📋</div>
          <div className="text-center">
            <p className="text-slate-600 font-semibold text-base">暂无任务记录</p>
            <p className="text-slate-400 text-sm mt-1">在「搜索配置」页点击「立即执行」触发第一次采集</p>
          </div>
        </div>
      ) : (
        <div className="glass-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(99,102,241,0.08)', background: 'rgba(99,102,241,0.03)' }}>
                {['ID', '配置', '状态', '搜索', '下载', '推送', '时间', '操作'].map(h => (
                  <th key={h} className="px-5 py-3 text-left text-xs font-bold text-purple-400 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tasks.map(t => {
                const s = STATUS_MAP[t.status] ?? { label: t.status, cls: 'bg-gray-100', dot: '·' }
                const configName = configMap[t.config_id] ?? `#${t.config_id}`
                return (
                  <tr key={t.id} style={{ borderBottom: '1px solid rgba(99,102,241,0.05)' }} className="hover:bg-white/40 transition-colors">
                    <td className="px-5 py-3 text-purple-300 text-xs font-mono">#{t.id}</td>
                    <td className="px-5 py-3">
                      <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-lg">{configName}</span>
                    </td>
                    <td className="px-5 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${s.cls}`}>{s.dot} {s.label}</span>
                      {t.error && <p className="text-xs text-red-400 mt-1 max-w-xs truncate" title={t.error}>{t.error}</p>}
                    </td>
                    <td className="px-5 py-3 text-slate-600 tabular-nums">{t.total}</td>
                    <td className="px-5 py-3 text-slate-600 tabular-nums">{t.downloaded}</td>
                    <td className="px-5 py-3 text-slate-600 tabular-nums">{t.sent}</td>
                    <td className="px-5 py-3 text-slate-400 text-xs whitespace-nowrap">{new Date(t.created_at).toLocaleString('zh-CN')}</td>
                    <td className="px-5 py-3">
                      <button
                        onClick={() => handleDelete(t.id)}
                        className="text-xs px-2 py-1 rounded-lg bg-red-50 text-red-400 border border-red-100 hover:bg-red-100 transition-colors"
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

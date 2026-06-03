import { useEffect, useState } from 'react'
import { type LogEntry, logsApi } from '../api/client'
import { toast } from '../components/Toast'

export default function Logs() {
  const [dates, setDates] = useState<string[]>([])
  const [selectedDate, setSelectedDate] = useState<string>('')
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState({ config: '', type: '', status: '' })
  const [deleting, setDeleting] = useState(false)
  const [clearing, setClearing] = useState(false)

  const loadDates = () => logsApi.dates().then(d => {
    setDates(d)
    if (d.length > 0 && !selectedDate) setSelectedDate(d[0])
    // 如果当前选中日期已被删除则切换到最新
    if (selectedDate && !d.includes(selectedDate)) {
      setSelectedDate(d[0] ?? '')
      setEntries([])
    }
  })

  useEffect(() => { loadDates() }, [])

  useEffect(() => {
    if (!selectedDate) return
    setLoading(true)
    logsApi.entries(selectedDate)
      .then(e => setEntries(e))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false))
  }, [selectedDate])

  const handleDeleteDate = async () => {
    if (!selectedDate) return
    if (!confirm(`确认删除 ${selectedDate} 的日志（${entries.length} 条）？`)) return
    setDeleting(true)
    try {
      await logsApi.deleteDate(selectedDate)
      toast.success(`已删除 ${selectedDate} 的日志`)
      setEntries([])
      loadDates()
    } catch {
      toast.error('删除失败')
    } finally {
      setDeleting(false)
    }
  }

  const handleClearAll = async () => {
    if (!confirm(`确认清空全部 ${dates.length} 天的日志文件？此操作不可恢复。`)) return
    setClearing(true)
    try {
      const res: any = await logsApi.clearAll()
      toast.success(`已清空全部日志（共 ${res.deleted} 个文件）`)
      setDates([])
      setSelectedDate('')
      setEntries([])
    } catch {
      toast.error('清空失败')
    } finally {
      setClearing(false)
    }
  }

  const filtered = entries.filter(e =>
    (!filter.config || e.config_name.includes(filter.config)) &&
    (!filter.type || e.media_type === filter.type) &&
    (!filter.status || (filter.status === 'ok' ? e.downloaded : !e.downloaded))
  )

  const inputCls = 'border border-purple-100 rounded-xl px-3 py-2 text-sm bg-white/70 focus:outline-none focus:border-indigo-400'

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-2xl font-extrabold" style={{ color: 'var(--text-primary)' }}>采集日志</h2>
        {dates.length > 0 && (
          <button
            onClick={handleClearAll}
            disabled={clearing}
            className="text-xs px-3 py-1.5 rounded-xl bg-red-50/80 text-red-400 border border-red-100 hover:bg-red-50 transition-colors disabled:opacity-50"
          >
            {clearing ? '清空中...' : '🗑 清空所有日志'}
          </button>
        )}
      </div>
      <p className="text-sm text-slate-400 mb-5">查看每次任务的采集明细，按日期存储在本地 JSONL 文件中</p>

      <div className="flex gap-3 mb-5 flex-wrap items-center">
        <select value={selectedDate} onChange={e => setSelectedDate(e.target.value)} className={inputCls}>
          {dates.length === 0 && <option value="">暂无日志</option>}
          {dates.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        {selectedDate && entries.length > 0 && (
          <button
            onClick={handleDeleteDate}
            disabled={deleting}
            className="text-xs px-3 py-1.5 rounded-xl bg-red-50/80 text-red-400 border border-red-100 hover:bg-red-50 transition-colors disabled:opacity-50"
          >
            {deleting ? '删除中...' : `删除 ${selectedDate}`}
          </button>
        )}
        <input
          value={filter.config}
          onChange={e => setFilter(f => ({ ...f, config: e.target.value }))}
          placeholder="配置名称"
          className={inputCls + ' w-32'}
        />
        <select value={filter.type} onChange={e => setFilter(f => ({ ...f, type: e.target.value }))} className={inputCls}>
          <option value="">全部类型</option>
          <option value="video">视频</option>
          <option value="image">图文</option>
        </select>
        <select value={filter.status} onChange={e => setFilter(f => ({ ...f, status: e.target.value }))} className={inputCls}>
          <option value="">全部状态</option>
          <option value="ok">下载成功</option>
          <option value="fail">下载失败</option>
        </select>
        <span className="text-sm text-slate-400">{filtered.length} 条</span>
      </div>

      <div className="glass-card overflow-x-auto">
        {loading ? (
          <div className="py-12 text-center text-slate-400">加载中...</div>
        ) : (
          <table className="w-full text-sm min-w-[800px]">
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(99,102,241,0.08)', background: 'rgba(99,102,241,0.03)' }}>
                {['时间', '配置', '作者', '描述', '类型', '已下载', '已发送', '错误'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-bold text-purple-400 uppercase tracking-wide whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-400">暂无日志记录</td></tr>
              )}
              {filtered.map((e, i) => (
                <tr key={i} style={{ borderBottom: '1px solid rgba(99,102,241,0.05)' }} className="hover:bg-white/30 transition-colors">
                  <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">{new Date(e.ts).toLocaleTimeString('zh-CN')}</td>
                  <td className="px-4 py-3 text-xs font-semibold text-indigo-500">{e.config_name}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">{e.author}</td>
                  <td className="px-4 py-3 text-xs text-slate-500 max-w-[200px] truncate">{e.desc}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${e.media_type === 'video' ? 'bg-blue-100 text-blue-600' : 'bg-pink-100 text-pink-600'}`}>
                      {e.media_type === 'video' ? '📹 视频' : '🖼 图文'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${e.downloaded ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-500'}`}>
                      {e.downloaded ? '✓' : '✗'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${e.sent ? 'bg-emerald-100 text-emerald-600' : 'bg-gray-100 text-gray-400'}`}>
                      {e.sent ? '✓' : '—'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-red-400 max-w-[150px] truncate">{e.error ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

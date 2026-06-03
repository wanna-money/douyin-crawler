import { useState, useEffect } from 'react'

type Mode = 'daily' | 'weekday' | 'weekly' | 'interval' | 'advanced'

interface Props {
  value: string
  onChange: (cron: string) => void
}

const DAYS = ['一', '二', '三', '四', '五', '六', '日']
const DAY_VALUES = [1, 2, 3, 4, 5, 6, 0]

interface Parsed {
  mode: Mode
  times: Array<{ hour: number; minute: number }>
  days: number[]
  interval: number
}

function parseCron(cron: string): Parsed {
  const parts = cron.trim().split(/\s+/)
  const fallback: Parsed = { mode: 'advanced', times: [{ hour: 9, minute: 0 }], days: [1,2,3,4,5], interval: 4 }
  if (parts.length !== 5) return fallback

  const [minPart, hrPart, , , dow] = parts

  // 每隔 N 小时
  if (hrPart.startsWith('*/')) {
    return { mode: 'interval', times: [{ hour: 9, minute: 0 }], days: [], interval: parseInt(hrPart.slice(2)) || 4 }
  }

  // 解析多时间点：hour 和 minute 都可能是逗号分隔
  const hours = hrPart.split(',').map(Number)
  const minutes = minPart.split(',').map(Number)
  // 构建时间点列表：逐一配对，不足的用第一个补齐
  const times = hours.map((h, i) => ({ hour: h, minute: minutes[i] ?? minutes[0] ?? 0 }))

  if (dow === '*') return { mode: 'daily', times, days: [], interval: 4 }
  if (dow === '1-5') return { mode: 'weekday', times, days: [1,2,3,4,5], interval: 4 }
  if (dow.includes(',') || /^\d$/.test(dow)) {
    return { mode: 'weekly', times, days: dow.split(',').map(Number), interval: 4 }
  }
  return fallback
}

function toCron(mode: Mode, times: Array<{ hour: number; minute: number }>, days: number[], interval: number, raw: string): string {
  if (mode === 'interval') return `0 */${interval} * * *`
  if (mode === 'advanced') return raw

  const sorted = [...times].sort((a, b) => a.hour !== b.hour ? a.hour - b.hour : a.minute - b.minute)

  // 如果所有时间点分钟相同，用紧凑语法 "min hour1,hour2 * * dow"
  const allSameMinute = sorted.every(t => t.minute === sorted[0].minute)
  if (allSameMinute) {
    const minStr = sorted[0].minute.toString()
    const hrStr = sorted.map(t => t.hour).join(',')
    const dowStr = mode === 'daily' ? '*' : mode === 'weekday' ? '1-5' : ([...days].sort().join(',') || '*')
    return `${minStr} ${hrStr} * * ${dowStr}`
  }

  // 分钟不同时，展开为多段 cron（用分号分隔，调度器需支持；否则降级第一条）
  // APScheduler 不支持多 cron 字符串，降级：只保留第一个时间点
  const t = sorted[0]
  const dowStr = mode === 'daily' ? '*' : mode === 'weekday' ? '1-5' : ([...days].sort().join(',') || '*')
  return `${t.minute} ${t.hour} * * ${dowStr}`
}

function toHuman(mode: Mode, times: Array<{ hour: number; minute: number }>, days: number[], interval: number): string {
  if (mode === 'interval') return `每 ${interval} 小时执行一次`
  if (mode === 'advanced') return '自定义 Cron'
  const sorted = [...times].sort((a, b) => a.hour !== b.hour ? a.hour - b.hour : a.minute - b.minute)
  const timeStr = sorted.map(t => `${String(t.hour).padStart(2,'0')}:${String(t.minute).padStart(2,'0')}`).join('、')
  if (mode === 'daily') return `每天 ${timeStr} 执行`
  if (mode === 'weekday') return `工作日 ${timeStr} 执行`
  const names = [...days].sort().map(d => '日一二三四五六'[d])
  return `每周${names.join('、')} ${timeStr} 执行`
}

export default function SchedulePicker({ value, onChange }: Props) {
  const parsed = parseCron(value)
  const [mode, setMode] = useState<Mode>(parsed.mode)
  const [times, setTimes] = useState<Array<{ hour: number; minute: number }>>(parsed.times)
  const [days, setDays] = useState<number[]>(parsed.days)
  const [interval, setIntervalVal] = useState(parsed.interval)
  const [raw, setRaw] = useState(value)
  // 新增时间的临时选择值
  const [addHour, setAddHour] = useState(12)
  const [addMinute, setAddMinute] = useState(0)

  useEffect(() => {
    onChange(toCron(mode, times, days, interval, raw))
  }, [mode, times, days, interval, raw]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleDay = (d: number) =>
    setDays(prev => prev.includes(d) ? prev.filter(x => x !== d) : [...prev, d])

  const addTime = () => {
    const exists = times.some(t => t.hour === addHour && t.minute === addMinute)
    if (!exists) setTimes(prev => [...prev, { hour: addHour, minute: addMinute }])
  }

  const removeTime = (idx: number) => {
    if (times.length <= 1) return // 至少保留一个
    setTimes(prev => prev.filter((_, i) => i !== idx))
  }

  const selCls = 'px-2 py-1.5 rounded-lg border border-purple-200 text-sm font-bold text-indigo-700 bg-white/80 focus:outline-none focus:border-indigo-400'

  const modeBtns: { key: Mode; label: string }[] = [
    { key: 'daily', label: '每天' },
    { key: 'weekday', label: '工作日' },
    { key: 'weekly', label: '每周指定' },
    { key: 'interval', label: '每隔N小时' },
    { key: 'advanced', label: '高级Cron' },
  ]

  const showTimes = mode === 'daily' || mode === 'weekday' || mode === 'weekly'

  return (
    <div className="space-y-3">
      {/* 模式选择 */}
      <div className="flex gap-2 flex-wrap">
        {modeBtns.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setMode(key)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-all ${
              mode === key
                ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white border-transparent shadow-md'
                : 'bg-white/70 text-gray-500 border-purple-100 hover:border-indigo-300'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* 星期选择 */}
      {(mode === 'weekday' || mode === 'weekly') && (
        <div className="flex gap-2">
          {DAYS.map((d, i) => {
            const val = DAY_VALUES[i]
            const active = mode === 'weekday' ? val >= 1 && val <= 5 : days.includes(val)
            return (
              <button
                key={d}
                type="button"
                onClick={() => mode === 'weekly' && toggleDay(val)}
                className={`w-8 h-8 rounded-full text-xs font-bold transition-all ${
                  active
                    ? 'bg-gradient-to-br from-indigo-500 to-purple-500 text-white shadow-md'
                    : 'bg-white/70 text-gray-400 border border-purple-100'
                } ${mode === 'weekday' ? 'cursor-default' : 'cursor-pointer'}`}
              >
                {d}
              </button>
            )
          })}
        </div>
      )}

      {/* 多时间点管理 */}
      {showTimes && (
        <div className="space-y-2">
          {/* 已添加的时间列表 */}
          <div className="flex flex-wrap gap-2">
            {[...times]
              .sort((a, b) => a.hour !== b.hour ? a.hour - b.hour : a.minute - b.minute)
              .map((t, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-sm"
                >
                  <span>{String(t.hour).padStart(2,'0')}:{String(t.minute).padStart(2,'0')}</span>
                  {times.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeTime(times.indexOf(t))}
                      className="ml-0.5 opacity-70 hover:opacity-100 leading-none"
                    >
                      ×
                    </button>
                  )}
                </div>
              ))}
          </div>

          {/* 添加时间行 */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-400">添加时间</span>
            <select className={selCls} value={addHour} onChange={e => setAddHour(Number(e.target.value))}>
              {Array.from({ length: 24 }, (_, i) => (
                <option key={i} value={i}>{String(i).padStart(2, '0')}</option>
              ))}
            </select>
            <span className="text-purple-300 font-bold">:</span>
            <select className={selCls} value={addMinute} onChange={e => setAddMinute(Number(e.target.value))}>
              {Array.from({ length: 60 }, (_, i) => (
                <option key={i} value={i}>{String(i).padStart(2, '0')}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={addTime}
              className="px-3 py-1.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-600 border border-indigo-200 hover:bg-indigo-100 transition-colors"
            >
              ＋ 添加
            </button>
            <span className="text-xs text-purple-500 font-semibold">
              → {toHuman(mode, times, days, interval)}
            </span>
          </div>
        </div>
      )}

      {/* 间隔小时 */}
      {mode === 'interval' && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">每隔</span>
          <select className={selCls} value={interval} onChange={e => setIntervalVal(Number(e.target.value))}>
            {[1, 2, 3, 4, 6, 8, 12].map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
          <span className="text-xs text-gray-400">小时执行一次</span>
        </div>
      )}

      {/* 高级 Cron */}
      {mode === 'advanced' && (
        <div className="flex items-center gap-2">
          <input
            value={raw}
            onChange={e => setRaw(e.target.value)}
            placeholder="0 9 * * *"
            className="flex-1 px-3 py-1.5 rounded-lg border border-purple-200 text-sm font-mono text-indigo-700 bg-white/80 focus:outline-none focus:border-indigo-400"
          />
          <span className="text-xs text-gray-400">5段 cron 表达式</span>
        </div>
      )}
    </div>
  )
}

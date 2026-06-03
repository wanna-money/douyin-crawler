import { useState, useEffect } from 'react'

export type ToastType = 'success' | 'error' | 'info'

interface ToastItem {
  id: number
  type: ToastType
  message: string
}

// 模块级事件总线，完全独立于 React 生命周期
type Listener = (item: ToastItem) => void
const _listeners: Listener[] = []
const _queue: ToastItem[] = []   // 挂载前的消息暂存队列
let _id = 0

function emit(type: ToastType, message: string) {
  const item: ToastItem = { id: ++_id, type, message }
  if (_listeners.length === 0) {
    _queue.push(item)
  } else {
    _listeners.forEach(fn => fn(item))
  }
}

export const toast = {
  success: (msg: string) => emit('success', msg),
  error:   (msg: string) => emit('error', msg),
  info:    (msg: string) => emit('info', msg),
}

const ICONS: Record<ToastType, string> = {
  success: '✓', error: '✕', info: 'ℹ',
}
const BAR: Record<ToastType, string> = {
  success: '#10b981', error: '#ef4444', info: '#6366f1',
}
const ICON_CLS: Record<ToastType, string> = {
  success: 'bg-emerald-100 text-emerald-600',
  error:   'bg-red-100 text-red-500',
  info:    'bg-indigo-100 text-indigo-600',
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  useEffect(() => {
    const listener: Listener = (item) => {
      setToasts(prev => [...prev, item])
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== item.id))
      }, 5000)
    }
    _listeners.push(listener)
    // 补发挂载前积压的消息
    if (_queue.length > 0) {
      _queue.splice(0).forEach(listener)
    }
    return () => {
      const idx = _listeners.indexOf(listener)
      if (idx !== -1) _listeners.splice(idx, 1)
    }
  }, [])

  if (toasts.length === 0) return null

  return (
    <div className="fixed top-5 right-5 z-[200] flex flex-col gap-2 pointer-events-none">
      {toasts.map(t => (
        <div
          key={t.id}
          className="pointer-events-auto relative flex items-center gap-3 pl-4 pr-5 py-3 rounded-xl min-w-[240px] max-w-sm"
          style={{
            background: 'rgba(255,255,255,0.96)',
            backdropFilter: 'blur(16px)',
            border: '1px solid rgba(255,255,255,0.85)',
            boxShadow: '0 8px 32px rgba(99,102,241,0.14)',
            animation: 'toast-in 0.22s cubic-bezier(0.34,1.56,0.64,1)',
          }}
        >
          <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l-xl" style={{ background: BAR[t.type] }} />
          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${ICON_CLS[t.type]}`}>
            {ICONS[t.type]}
          </div>
          <span className="text-sm font-medium text-slate-700">{t.message}</span>
        </div>
      ))}
      <style>{`
        @keyframes toast-in {
          from { opacity:0; transform:translateX(20px) scale(0.95); }
          to   { opacity:1; transform:translateX(0) scale(1); }
        }
      `}</style>
    </div>
  )
}

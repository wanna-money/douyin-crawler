import { useEffect, useState } from 'react'
import { type AppSetting, settingsApi } from '../api/client'
import { toast } from '../components/Toast'

const SETTING_META: Record<string, { label: string; desc: string; placeholder: string; icon: string }> = {
  download_dir: {
    label: '下载目录',
    desc: '视频和图片文件的本地存储路径，支持相对路径或绝对路径',
    placeholder: 'downloads',
    icon: '📁',
  },
}

export default function Settings() {
  const [settings, setSettings] = useState<AppSetting[]>([])
  const [values, setValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)

  useEffect(() => {
    settingsApi.list().then(list => {
      setSettings(list)
      setValues(Object.fromEntries(list.map(s => [s.key, s.value])))
    })
  }, [])

  const handleSave = async (key: string) => {
    setSaving(key)
    try {
      await settingsApi.update(key, values[key] ?? '')
      toast.success('设置已保存')
    } catch {
      toast.error('保存失败，请重试')
    } finally {
      setSaving(null)
    }
  }

  const filtered = settings.filter(s => s.key === 'download_dir')

  return (
    <div className="p-4 md:p-8">
      <h2 className="text-2xl font-extrabold mb-1" style={{ color: 'var(--text-primary)' }}>系统设置</h2>
      <p className="text-sm text-slate-400 mb-8">Cookie 和通知渠道请在对应页面管理</p>

      <div className="max-w-2xl space-y-4">
        {filtered.map(s => {
          const meta = SETTING_META[s.key]
          return (
            <div key={s.key} className="glass-card p-7">
              {/* 标题行 */}
              <div className="flex items-center gap-3 mb-5">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center text-xl flex-shrink-0"
                  style={{ background: 'linear-gradient(135deg,rgba(99,102,241,0.12),rgba(168,85,247,0.12))' }}
                >
                  {meta?.icon ?? '⚙️'}
                </div>
                <div>
                  <div className="font-bold text-slate-700">{meta?.label ?? s.key}</div>
                  {meta?.desc && (
                    <div className="text-xs text-slate-400 mt-0.5">{meta.desc}</div>
                  )}
                </div>
              </div>

              {/* 输入区 */}
              <input
                value={values[s.key] ?? ''}
                onChange={e => setValues(v => ({ ...v, [s.key]: e.target.value }))}
                className="w-full border border-purple-100 rounded-xl px-4 py-3 text-sm bg-white/70 focus:outline-none focus:border-indigo-400 transition-colors mb-5"
                placeholder={meta?.placeholder ?? ''}
              />

              {/* 底部操作行 */}
              <div className="flex items-center justify-between pt-4 border-t border-purple-50">
                <span className="text-xs text-slate-400">
                  当前值：<code className="bg-purple-50 px-1.5 py-0.5 rounded text-indigo-500 font-mono">
                    {values[s.key] || '（未设置）'}
                  </code>
                </span>
                <button
                  onClick={() => handleSave(s.key)}
                  disabled={saving === s.key}
                  className="btn-primary"
                >
                  {saving === s.key ? '保存中...' : '保存设置'}
                </button>
              </div>
            </div>
          )
        })}

        {filtered.length === 0 && (
          <p className="text-slate-400 text-sm">暂无配置项</p>
        )}
      </div>
    </div>
  )
}

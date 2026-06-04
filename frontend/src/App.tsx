import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Configs from './pages/Configs'
import Tasks from './pages/Tasks'
import Settings from './pages/Settings'
import Cookies from './pages/Cookies'
import Channels from './pages/Channels'
import LLMConfigPage from './pages/LLMConfig'
import ToastContainer from './components/Toast'

const NAV_GROUPS = [
  {
    label: '采集管理',
    items: [
      { to: '/', label: '搜索配置', icon: '🔍' },
      { to: '/tasks', label: '任务记录', icon: '📋' },
    ],
  },
  {
    label: '账号与通知',
    items: [
      { to: '/llm', label: 'LLM 配置', icon: '🤖' },
      { to: '/cookies', label: 'Cookie 管理', icon: '🍪' },
      { to: '/channels', label: '通知渠道', icon: '🔔' },
      { to: '/settings', label: '系统设置', icon: '⚙️' },
    ],
  },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen" style={{ background: 'var(--bg-gradient)' }}>
        <nav
          className="w-56 min-w-[224px] flex flex-col py-5"
          style={{
            background: 'var(--sidebar-bg)',
            backdropFilter: 'blur(20px)',
            borderRight: '1px solid rgba(99,102,241,0.08)',
            boxShadow: '2px 0 24px rgba(99,102,241,0.07)',
          }}
        >
          <div className="px-5 mb-5">
            <span
              className="text-[17px] font-extrabold"
              style={{ background: 'linear-gradient(135deg,#6366f1,#a855f7)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
            >
              ⚡ 抖音采集
            </span>
          </div>

          {NAV_GROUPS.map(group => (
            <div key={group.label} className="mb-2">
              <div className="px-4 py-1.5 text-[10.5px] font-bold tracking-wider uppercase text-purple-300">
                {group.label}
              </div>
              {group.items.map(({ to, label, icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 mx-2 px-3 py-2 rounded-xl text-[13.5px] transition-all ${
                      isActive ? 'text-indigo-600 font-semibold' : 'text-slate-500 hover:text-indigo-500'
                    }`
                  }
                  style={({ isActive }) => isActive ? {
                    background: 'linear-gradient(135deg,rgba(99,102,241,0.12),rgba(168,85,247,0.12))',
                    borderLeft: '3px solid #6366f1',
                    paddingLeft: '9px',
                  } : { borderLeft: '3px solid transparent', paddingLeft: '9px' }}
                >
                  <span>{icon}</span>
                  <span>{label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Configs />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/llm" element={<LLMConfigPage />} />
            <Route path="/cookies" element={<Cookies />} />
            <Route path="/channels" element={<Channels />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
      <ToastContainer />
    </BrowserRouter>
  )
}

import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { useState } from 'react'
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
  const [drawerOpen, setDrawerOpen] = useState(false)

  return (
    <BrowserRouter>
      <div className="flex h-screen" style={{ background: 'var(--bg-gradient)' }}>

        {/* PC 侧边栏（md 以上显示） */}
        <nav
          className="hidden md:flex w-56 min-w-[224px] flex-col py-5"
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

        {/* 移动端抽屉遮罩 */}
        {drawerOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/40 md:hidden"
            onClick={() => setDrawerOpen(false)}
          />
        )}

        {/* 移动端抽屉侧边栏 */}
        <nav
          className={`fixed top-0 left-0 h-full z-50 w-64 flex flex-col py-5 transition-transform duration-300 md:hidden ${drawerOpen ? 'translate-x-0' : '-translate-x-full'}`}
          style={{
            background: 'var(--sidebar-bg)',
            backdropFilter: 'blur(20px)',
            borderRight: '1px solid rgba(99,102,241,0.08)',
            boxShadow: '4px 0 32px rgba(99,102,241,0.12)',
          }}
        >
          <div className="px-5 mb-5 flex items-center justify-between">
            <span
              className="text-[17px] font-extrabold"
              style={{ background: 'linear-gradient(135deg,#6366f1,#a855f7)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
            >
              ⚡ 抖音采集
            </span>
            <button
              onClick={() => setDrawerOpen(false)}
              className="text-slate-400 hover:text-slate-600 text-xl leading-none"
            >
              ✕
            </button>
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
                  onClick={() => setDrawerOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 mx-2 px-3 py-2.5 rounded-xl text-[14px] transition-all ${
                      isActive ? 'text-indigo-600 font-semibold' : 'text-slate-500'
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

        {/* 主内容区 */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* 移动端顶栏 */}
          <header
            className="flex md:hidden items-center px-4 h-12 shrink-0"
            style={{
              background: 'var(--sidebar-bg)',
              backdropFilter: 'blur(20px)',
              borderBottom: '1px solid rgba(99,102,241,0.08)',
            }}
          >
            <button
              onClick={() => setDrawerOpen(true)}
              className="text-slate-500 text-xl mr-3 leading-none"
              aria-label="打开菜单"
            >
              ☰
            </button>
            <span
              className="text-[16px] font-extrabold"
              style={{ background: 'linear-gradient(135deg,#6366f1,#a855f7)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
            >
              ⚡ 抖音采集
            </span>
          </header>

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
      </div>
      <ToastContainer />
    </BrowserRouter>
  )
}

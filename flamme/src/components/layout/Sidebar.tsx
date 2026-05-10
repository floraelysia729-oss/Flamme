import { NavLink, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'

const navItems = [
  { path: '/', icon: '📊', label: 'Dashboard' },
  { path: '/chat', icon: '💬', label: 'Chat' },
  { path: '/graph', icon: '🔗', label: 'Graph' },
]

type Tab = 'files' | 'history'

interface DocItem {
  path: string
  title: string
  level: string
  updated_at: string
}

interface SessionItem {
  session_id: string
  title: string
  message_count: number
  last_updated: string
}

interface SidebarProps {
  onSessionSelect?: (sessionId: string) => void
  onNewChat?: () => void
  currentSessionId?: string
}

export default function Sidebar({ onSessionSelect, onNewChat, currentSessionId }: SidebarProps) {
  const [tab, setTab] = useState<Tab>('files')
  const [docs, setDocs] = useState<DocItem[]>([])
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [search, setSearch] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    api.documents.list()
      .then((items: any[]) => setDocs(items.map((d: any) => ({
        path: d.path,
        title: d.title,
        level: d.level,
        updated_at: d.updated_at,
      }))))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (tab === 'history') {
      api.chat.sessions()
        .then((data: any) => setSessions(data.sessions || []))
        .catch(() => {})
    }
  }, [tab])

  const filteredDocs = docs.filter(d =>
    d.title.toLowerCase().includes(search.toLowerCase())
  )

  const levelColor: Record<string, string> = {
    raw: '#94a3b8',
    lite: '#60a5fa',
    pro: '#a78bfa',
  }

  function formatTime(iso: string) {
    if (!iso) return ''
    const d = new Date(iso)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return '刚刚'
    if (diffMin < 60) return `${diffMin}分钟前`
    const diffHr = Math.floor(diffMin / 60)
    if (diffHr < 24) return `${diffHr}小时前`
    const diffDay = Math.floor(diffHr / 24)
    if (diffDay < 7) return `${diffDay}天前`
    return `${d.getMonth() + 1}/${d.getDate()}`
  }

  return (
    <aside style={{
      width: 240,
      height: '100vh',
      background: 'var(--bg-200)',
      display: 'flex',
      flexDirection: 'column',
      borderRight: '1px solid var(--bg-300)',
      flexShrink: 0,
    }}>
      {/* Logo + Nav */}
      <div style={{ padding: '12px 12px 8px', borderBottom: '1px solid var(--bg-300)' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'var(--primary-100)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontWeight: 700, fontSize: 11,
          }}>
            WIKI
          </div>
          <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-100)' }}>Flamme</span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {navItems.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              style={({ isActive }) => ({
                flex: 1,
                padding: '6px 0',
                borderRadius: 6,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 16,
                textDecoration: 'none',
                background: isActive ? 'var(--primary-100)' : 'transparent',
                color: isActive ? '#fff' : 'var(--text-200)',
                transition: 'all 0.15s',
              })}
              title={item.label}
            >
              {item.icon}
            </NavLink>
          ))}
        </div>
      </div>

      {/* Tab 切换 */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--bg-300)' }}>
        {(['files', 'history'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              flex: 1,
              padding: '8px 0',
              border: 'none',
              background: 'none',
              fontSize: 13,
              fontWeight: tab === t ? 600 : 400,
              color: tab === t ? 'var(--primary-100)' : 'var(--text-200)',
              borderBottom: tab === t ? '2px solid var(--primary-100)' : '2px solid transparent',
              cursor: 'pointer',
            }}
          >
            {t === 'files' ? '文件' : '历史'}
          </button>
        ))}
      </div>

      {/* 搜索 */}
      <div style={{ padding: '8px 12px' }}>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={tab === 'files' ? '搜索文档...' : '搜索对话...'}
          style={{
            width: '100%',
            padding: '6px 10px',
            borderRadius: 6,
            border: '1px solid var(--bg-300)',
            fontSize: 12,
            outline: 'none',
            background: '#fff',
            boxSizing: 'border-box',
          }}
        />
      </div>

      {/* 列表区域 */}
      <div style={{ flex: 1, overflow: 'auto', padding: '0 12px' }}>
        {tab === 'files' ? (
          filteredDocs.map(doc => (
            <div
              key={doc.path}
              title={doc.path}
              style={{
                padding: '6px 8px',
                borderRadius: 6,
                marginBottom: 2,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                cursor: 'default',
                fontSize: 12,
                color: 'var(--text-100)',
              }}
            >
              <span style={{
                fontSize: 10,
                padding: '1px 4px',
                borderRadius: 3,
                background: levelColor[doc.level] || '#94a3b8',
                color: '#fff',
                flexShrink: 0,
              }}>
                {doc.level}
              </span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {doc.title}
              </span>
            </div>
          ))
        ) : (
          sessions
            .filter(s => s.title.toLowerCase().includes(search.toLowerCase()))
            .map(s => (
              <div
                key={s.session_id}
                onClick={() => {
                  if (onSessionSelect) onSessionSelect(s.session_id)
                  navigate('/chat')
                }}
                style={{
                  padding: '8px',
                  borderRadius: 6,
                  marginBottom: 2,
                  cursor: 'pointer',
                  background: currentSessionId === s.session_id ? 'var(--bg-300)' : 'transparent',
                }}
              >
                <div style={{
                  fontSize: 12,
                  color: 'var(--text-100)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  marginBottom: 2,
                }}>
                  {s.title}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-200)' }}>
                  {formatTime(s.last_updated)} · {s.message_count} 条消息
                </div>
              </div>
            ))
        )}
        {tab === 'files' && filteredDocs.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--text-200)', fontSize: 12, padding: 16 }}>
            {search ? '无匹配文档' : '暂无文档'}
          </div>
        )}
        {tab === 'history' && sessions.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--text-200)', fontSize: 12, padding: 16 }}>
            暂无对话记录
          </div>
        )}
      </div>

      {/* 底部操作 */}
      <div style={{ padding: '8px 12px', borderTop: '1px solid var(--bg-300)' }}>
        <button
          onClick={() => {
            if (onNewChat) onNewChat()
            navigate('/chat')
          }}
          style={{
            width: '100%',
            padding: '8px',
            borderRadius: 6,
            border: '1px dashed var(--bg-300)',
            background: 'transparent',
            color: 'var(--text-200)',
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          + 新对话
        </button>
      </div>
    </aside>
  )
}

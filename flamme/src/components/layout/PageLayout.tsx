import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'

interface SessionState {
  sessionId: string
  setSessionId: (id: string) => void
}

const SessionContext = createContext<SessionState>({
  sessionId: '',
  setSessionId: () => {},
})

export function useSession() {
  return useContext(SessionContext)
}

const SESSION_KEY = 'llm-wiki-session-id'

export default function PageLayout() {
  const [sessionId, setSessionIdState] = useState(() => {
    return localStorage.getItem(SESSION_KEY) || crypto.randomUUID()
  })

  const setSessionId = useCallback((id: string) => {
    localStorage.setItem(SESSION_KEY, id)
    setSessionIdState(id)
  }, [])

  useEffect(() => {
    localStorage.setItem(SESSION_KEY, sessionId)
  }, [sessionId])

  const handleNewChat = useCallback(() => {
    const newId = crypto.randomUUID()
    setSessionId(newId)
  }, [setSessionId])

  const handleSessionSelect = useCallback((id: string) => {
    setSessionId(id)
  }, [setSessionId])

  return (
    <SessionContext.Provider value={{ sessionId, setSessionId }}>
      <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
        <Sidebar
          onSessionSelect={handleSessionSelect}
          onNewChat={handleNewChat}
          currentSessionId={sessionId}
        />
        <main style={{ flex: 1, minWidth: 0, minHeight: 0, overflow: 'hidden', background: 'var(--bg-100)' }}>
          <Outlet />
        </main>
      </div>
    </SessionContext.Provider>
  )
}

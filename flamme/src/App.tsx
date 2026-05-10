import { Routes, Route, Navigate } from 'react-router-dom'
import PageLayout from './components/layout/PageLayout'
import Dashboard from './components/dashboard/Dashboard'
import ChatPage from './components/chat/ChatPage'
import GraphPage from './components/graph/GraphPage'

export default function App() {
  return (
    <Routes>
      <Route element={<PageLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

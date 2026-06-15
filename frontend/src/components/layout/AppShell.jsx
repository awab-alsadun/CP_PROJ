import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import ChatPanel from '../chat/ChatPanel'
import { useChat } from '../../context/ChatContext'

export default function AppShell({ pageTitle, pageSubtitle }) {
  const { isOpen, setIsOpen } = useChat()

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Topbar title={pageTitle} subtitle={pageSubtitle} />
        <main className="flex-1 overflow-y-auto" style={{ background: 'var(--bg-primary)' }}>
          <Outlet />
        </main>
      </div>
      <ChatPanel open={isOpen} onClose={() => setIsOpen(false)} />
    </div>
  )
}
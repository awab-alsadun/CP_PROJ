import { Sun, Moon, MessageSquare, Bell } from 'lucide-react'
import { useTheme } from '../../context/ThemeContext'
import { useChat } from '../../context/ChatContext'

export default function Topbar({ title, subtitle }) {
  const { theme, toggle } = useTheme()
  const { setIsOpen } = useChat()

  return (
    <header className="h-14 flex items-center justify-between px-6 border-b flex-shrink-0"
      style={{ background: 'var(--bg-sidebar)', borderColor: 'var(--border)' }}>

      <div>
        {title && (
          <h1 className="font-display text-base font-semibold leading-none"
            style={{ color: 'var(--text-primary)' }}>
            {title}
          </h1>
        )}
        {subtitle && (
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {subtitle}
          </p>
        )}
      </div>

      <div className="flex items-center gap-1">
        {/* Theme toggle */}
        <button
          onClick={toggle}
          className="btn-ghost p-2 rounded-xl"
          aria-label="Toggle theme"
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark'
            ? <Sun size={16} strokeWidth={1.8} />
            : <Moon size={16} strokeWidth={1.8} />
          }
        </button>

        {/* Notifications stub */}
        <button className="btn-ghost p-2 rounded-xl relative" aria-label="Notifications">
          <Bell size={16} strokeWidth={1.8} />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full"
            style={{ background: 'var(--accent)' }} />
        </button>

        {/* AI Chat trigger */}
        <button
          onClick={() => setIsOpen(true)}
          className="btn-primary ml-2 h-8 text-xs"
          aria-label="Open AI Chat"
        >
          <MessageSquare size={14} strokeWidth={2} />
          Ask AI
        </button>
      </div>
    </header>
  )
}
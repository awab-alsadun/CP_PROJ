import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sun, Moon, MessageSquare, Bell, X, CheckCheck,
  Upload, RefreshCw, CreditCard, AlertCircle, Info, ShieldAlert
} from 'lucide-react'
import { useTheme } from '../../context/ThemeContext'
import { useChat } from '../../context/ChatContext'
import { notificationsApi } from '../../lib/api'
import { formatRelative } from '../../lib/utils'

const TYPE_CONFIG = {
  upload:        { icon: Upload,      color: '#22C55E', bg: '#F0FDF4' },
  status_change: { icon: RefreshCw,   color: '#3B82F6', bg: '#EFF6FF' },
  payment:       { icon: CreditCard,  color: '#D4A847', bg: '#FFFBEB' },
  overdue:       { icon: AlertCircle, color: '#EF4444', bg: '#FEF2F2' },
  system:        { icon: Info,        color: '#6B7280', bg: '#F9FAFB' },
  compliance:    { icon: ShieldAlert, color: '#F97316', bg: '#FFF7ED' },
}

function NotificationItem({ n, onRead, navigate }) {
  const cfg = TYPE_CONFIG[n.type] || TYPE_CONFIG.system
  const Icon = cfg.icon

  const handleClick = () => {
    if (!n.is_read) onRead(n.id)
    if (n.related_invoice_id) {
      const type = n.invoice_type === 'receivable' ? 'receivables' : 'payables'
      navigate(`/${type}/${n.related_invoice_id}`)
    }
  }

  return (
    <div
      onClick={handleClick}
      className="flex gap-3 px-4 py-3 cursor-pointer transition-colors"
      style={{
        background: n.is_read ? 'transparent' : 'var(--accent-light)',
        borderLeft: n.is_read ? '3px solid transparent' : `3px solid ${cfg.color}`,
      }}
      onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-secondary)'}
      onMouseLeave={e => e.currentTarget.style.background = n.is_read ? 'transparent' : 'var(--accent-light)'}
    >
      <div className="w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
        style={{ background: cfg.bg }}>
        <Icon size={13} style={{ color: cfg.color }} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold leading-tight truncate" style={{ color: 'var(--text-primary)' }}>
          {n.title}
        </p>
        <p className="text-xs mt-0.5 leading-snug" style={{ color: 'var(--text-secondary)' }}>
          {n.message}
        </p>
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
          {formatRelative(n.created_at)}
        </p>
      </div>
      {!n.is_read && (
        <div className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0"
          style={{ background: 'var(--accent)' }} />
      )}
    </div>
  )
}

export default function Topbar({ title, subtitle }) {
  const { theme, toggle } = useTheme()
  const { setIsOpen } = useChat()
  const navigate = useNavigate()

  const [open,        setOpen]        = useState(false)
  const [notifs,      setNotifs]      = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loadingN,    setLoadingN]    = useState(false)
  const panelRef = useRef(null)
  const bellRef  = useRef(null)

  const fetchNotifs = useCallback(async () => {
    try {
      const res = await notificationsApi.list(false, 20)
      setNotifs(res?.notifications || [])
      setUnreadCount(res?.unread_count ?? 0)
    } catch { /* fail silently */ }
  }, [])

  useEffect(() => {
    fetchNotifs()
    const interval = setInterval(fetchNotifs, 30000)
    return () => clearInterval(interval)
  }, [fetchNotifs])

  useEffect(() => {
    if (!open) return
    const handleKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    const handleClick = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target) &&
          bellRef.current  && !bellRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('keydown', handleKey)
    document.addEventListener('mousedown', handleClick)
    return () => {
      document.removeEventListener('keydown', handleKey)
      document.removeEventListener('mousedown', handleClick)
    }
  }, [open])

  const handleMarkRead = async (id) => {
    try {
      await notificationsApi.markRead(id)
      setNotifs(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n))
      setUnreadCount(prev => Math.max(0, prev - 1))
    } catch {}
  }

  const handleMarkAllRead = async () => {
    setLoadingN(true)
    try {
      await notificationsApi.markAllRead()
      setNotifs(prev => prev.map(n => ({ ...n, is_read: true })))
      setUnreadCount(0)
    } catch {}
    setLoadingN(false)
  }

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
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{subtitle}</p>
        )}
      </div>

      <div className="flex items-center gap-1">
        <button onClick={toggle} className="btn-ghost p-2 rounded-xl" aria-label="Toggle theme">
          {theme === 'dark' ? <Sun size={16} strokeWidth={1.8} /> : <Moon size={16} strokeWidth={1.8} />}
        </button>

        <div className="relative">
          <button
            ref={bellRef}
            onClick={() => setOpen(v => !v)}
            className="btn-ghost p-2 rounded-xl relative"
            aria-label="Notifications"
          >
            <Bell size={16} strokeWidth={1.8} />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 min-w-[16px] h-4 rounded-full text-[10px] font-semibold flex items-center justify-center px-0.5"
                style={{ background: '#EF4444', color: '#fff' }}>
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>

          {open && (
            <div
              ref={panelRef}
              className="absolute right-0 top-full mt-2 z-50 rounded-2xl border overflow-hidden"
              style={{
                width: 360,
                background: 'var(--bg-card)',
                borderColor: 'var(--border)',
                boxShadow: '0 8px 32px rgba(0,0,0,0.14)',
              }}
            >
              <div className="flex items-center justify-between px-4 py-3 border-b"
                style={{ borderColor: 'var(--border)' }}>
                <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                  Notifications
                  {unreadCount > 0 && (
                    <span className="ml-2 text-xs font-normal px-1.5 py-0.5 rounded-full"
                      style={{ background: 'var(--bg-secondary)', color: 'var(--text-muted)' }}>
                      {unreadCount} unread
                    </span>
                  )}
                </p>
                <div className="flex items-center gap-1">
                  {unreadCount > 0 && (
                    <button
                      onClick={handleMarkAllRead}
                      disabled={loadingN}
                      className="btn-ghost text-xs h-7 px-2 disabled:opacity-50"
                    >
                      <CheckCheck size={12} /> Mark all read
                    </button>
                  )}
                  <button onClick={() => setOpen(false)} className="btn-ghost p-1.5 rounded-lg">
                    <X size={13} />
                  </button>
                </div>
              </div>

              <div className="overflow-y-auto divide-y" style={{ maxHeight: 400, borderColor: 'var(--border-subtle)' }}>
                {notifs.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-10 gap-2">
                    <Bell size={20} style={{ color: 'var(--text-muted)' }} strokeWidth={1.5} />
                    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>No notifications yet</p>
                  </div>
                ) : (
                  notifs.map(n => (
                    <NotificationItem
                      key={n.id}
                      n={n}
                      onRead={handleMarkRead}
                      navigate={(path) => { navigate(path); setOpen(false) }}
                    />
                  ))
                )}
              </div>
            </div>
          )}
        </div>

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

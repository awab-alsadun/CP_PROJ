import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, FileDown, FileUp, FilePlus, Upload,
  Building2, Users, BarChart3, MessageSquare, Settings,
  Zap, ChevronLeft, ChevronRight,
} from 'lucide-react'
import { useState } from 'react'
import { cn } from '../../lib/utils'

const NAV_SECTIONS = [
  {
    items: [
      { to: '/', icon: LayoutDashboard, label: 'Dashboard', exact: true },
    ],
  },
  {
    label: 'Invoicing',
    items: [
      { to: '/payables',    icon: FileDown,  label: 'Payables'        },
      { to: '/receivables', icon: FileUp,    label: 'Receivables'     },
      { to: '/create',      icon: FilePlus,  label: 'Create Invoice'  },
      { to: '/upload',      icon: Upload,    label: 'Upload & Extract'},
    ],
  },
  {
    label: 'Directory',
    items: [
      { to: '/vendors', icon: Building2, label: 'Vendors' },
      { to: '/clients', icon: Users,     label: 'Clients' },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { to: '/analytics', icon: BarChart3,     label: 'Analytics' },
      { to: '/chat',      icon: MessageSquare, label: 'AI Chat'   },
    ],
  },
  {
    label: 'System',
    items: [
      { to: '/settings', icon: Settings, label: 'Settings' },
    ],
  },
]

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const location = useLocation()

  return (
    <aside
      className={cn(
        'flex flex-col h-screen sticky top-0 border-r transition-all duration-200 z-30',
        collapsed ? 'w-16' : 'w-56'
      )}
      style={{ background: 'var(--bg-sidebar)', borderColor: 'var(--border)' }}
    >
      {/* Logo */}
      <div
        className={cn(
          'flex items-center h-14 px-4 border-b flex-shrink-0',
          collapsed ? 'justify-center' : 'justify-between'
        )}
        style={{ borderColor: 'var(--border)' }}
      >
        {!collapsed && (
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ background: 'var(--accent)' }}>
              <Zap size={14} color="#131310" strokeWidth={2.5} />
            </div>
            <span className="font-display font-bold text-base tracking-tight"
              style={{ color: 'var(--text-primary)' }}>
              Invox
            </span>
          </div>
        )}
        {collapsed && (
          <div className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: 'var(--accent)' }}>
            <Zap size={14} color="#131310" strokeWidth={2.5} />
          </div>
        )}
        <button
          onClick={() => setCollapsed(c => !c)}
          className={cn('btn-ghost p-1.5 rounded-lg', collapsed && 'ml-0')}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
        {NAV_SECTIONS.map((section, si) => (
          <div key={si} className={si > 0 ? 'mt-2' : ''}>
            {/* Section label */}
            {section.label && !collapsed && (
              <p
                className="px-3 pt-2 pb-1 text-xs font-semibold uppercase tracking-widest"
                style={{ color: 'var(--text-muted)' }}
              >
                {section.label}
              </p>
            )}
            {section.label && collapsed && (
              <div className="mx-2 my-1 border-t" style={{ borderColor: 'var(--border-subtle)' }} />
            )}
            {section.items.map(({ to, icon: Icon, label, exact }) => {
              const active = exact
                ? location.pathname === to
                : location.pathname === to || location.pathname.startsWith(to + '/')
              return (
                <NavLink
                  key={to}
                  to={to}
                  className={cn(
                    'nav-item',
                    active && 'active',
                    collapsed && 'justify-center px-2'
                  )}
                  title={collapsed ? label : undefined}
                >
                  <Icon size={17} strokeWidth={active ? 2.2 : 1.8} className="flex-shrink-0" />
                  {!collapsed && <span>{label}</span>}
                  {!collapsed && active && (
                    <span className="nav-dot ml-auto w-1.5 h-1.5 rounded-full"
                      style={{ background: 'var(--accent)' }} />
                  )}
                </NavLink>
              )
            })}
          </div>
        ))}
      </nav>
    </aside>
  )
}

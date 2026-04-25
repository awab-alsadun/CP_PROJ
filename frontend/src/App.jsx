import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ThemeProvider } from './context/ThemeContext'
import { ChatProvider } from './context/ChatContext'

// Layout
import AppShell from './components/layout/AppShell'

// Pages
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Invoices from './pages/Invoices'
import InvoiceDetail from './pages/InvoiceDetail'
import CreateInvoice from './pages/CreateInvoice'
import Vendors from './pages/Vendors'
import Clients from './pages/Clients'
import UploadExtract from './pages/UploadExtract'
import Analytics from './pages/Analytics'
import AiChat from './pages/AiChat'
import Settings from './pages/Settings'

// Simple auth guard — replace with Supabase Auth in production
function RequireAuth({ children }) {
  const companyId = localStorage.getItem('company_id')
  if (!companyId) return <Navigate to="/login" replace />
  return children
}

// Page titles for topbar
const PAGE_META = {
  '/':          { title: 'Dashboard',        subtitle: 'Overview of your financial activity' },
  '/invoices':  { title: 'Invoices',         subtitle: 'All invoices across vendors and clients' },
  '/create':    { title: 'Create Invoice',   subtitle: 'New outbound invoice' },
  '/vendors':   { title: 'Vendors',          subtitle: 'Manage and view vendor relationships' },
  '/clients':   { title: 'Clients',          subtitle: 'Manage and view client relationships' },
  '/upload':    { title: 'Upload & Extract', subtitle: 'AI-powered invoice ingestion pipeline' },
  '/analytics': { title: 'Analytics',        subtitle: 'Spending trends and financial metrics' },
  '/chat':      { title: 'AI Chat',          subtitle: 'Hybrid SQL + RAG invoice assistant' },
  '/settings':  { title: 'Settings',         subtitle: 'Workspace and pipeline configuration' },
}

function PagedShell({ path }) {
  const meta = PAGE_META[path] || {}
  return <AppShell pageTitle={meta.title} pageSubtitle={meta.subtitle} />
}

export default function App() {
  return (
    <ThemeProvider>
      <ChatProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />

            <Route path="/" element={
              <RequireAuth>
                <AppShell pageTitle="Dashboard" pageSubtitle="Overview of your financial activity" />
              </RequireAuth>
            }>
              <Route index element={<Dashboard />} />
              <Route path="invoices" element={<Invoices />} />
              <Route path="invoices/:id" element={<InvoiceDetail />} />
              <Route path="create" element={<CreateInvoice />} />
              <Route path="vendors" element={<Vendors />} />
              <Route path="clients" element={<Clients />} />
              <Route path="upload" element={<UploadExtract />} />
              <Route path="analytics" element={<Analytics />} />
              <Route path="chat" element={<AiChat />} />
              <Route path="settings" element={<Settings />} />
            </Route>

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ChatProvider>
    </ThemeProvider>
  )
}
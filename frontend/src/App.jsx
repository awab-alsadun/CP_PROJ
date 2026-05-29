import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
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
import CompanyDocuments from './pages/CompanyDocuments'
import Analytics from './pages/Analytics'
import AiChat from './pages/AiChat'
import Payables from './pages/Payables'
import Receivables from './pages/Receivables'
import Settings from './pages/Settings'

function RequireAuth({ children }) {
  const companyId = localStorage.getItem('company_id')
  if (!companyId) return <Navigate to="/login" replace />
  return children
}

const PAGE_META = {
  '/':            { title: 'Dashboard',         subtitle: 'Overview of your financial activity' },
  '/payables':    { title: 'Payables',          subtitle: 'Accounts payable — invoices you owe' },
  '/receivables': { title: 'Receivables',       subtitle: 'Accounts receivable — invoices owed to you' },
  '/invoices':    { title: 'Invoices',          subtitle: 'All invoices across vendors and clients' },
  '/create':      { title: 'Create Invoice',    subtitle: 'New outbound invoice' },
  '/vendors':     { title: 'Vendors',           subtitle: 'Manage and view vendor relationships' },
  '/clients':     { title: 'Clients',           subtitle: 'Manage and view client relationships' },
  '/upload':      { title: 'Upload & Extract',  subtitle: 'AI-powered invoice ingestion pipeline' },
  '/documents':   { title: 'Company Documents', subtitle: 'Regulation and compliance document library' },
  '/analytics':   { title: 'Analytics',         subtitle: 'Spending trends and financial metrics' },
  '/chat':        { title: 'AI Chat',           subtitle: 'Hybrid SQL + RAG invoice assistant' },
  '/settings':    { title: 'Settings',          subtitle: 'Company configuration and preferences' },
}

function ShellWrapper() {
  const location = useLocation()
  const base = '/' + location.pathname.split('/')[1]
  const meta = PAGE_META[base] || { title: 'K4Y', subtitle: '' }
  return (
    <AppShell pageTitle={meta.title} pageSubtitle={meta.subtitle} />
  )
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
                <ShellWrapper />
              </RequireAuth>
            }>
              <Route index element={<Dashboard />} />

              {/* AP — Payables */}
              <Route path="payables" element={<Payables />} />
              <Route path="payables/:id" element={<InvoiceDetail />} />

              {/* AR — Receivables */}
              <Route path="receivables" element={<Receivables />} />
              <Route path="receivables/:id" element={<InvoiceDetail />} />

              {/* Legacy invoice routes kept as fallback */}
              <Route path="invoices" element={<Invoices />} />
              <Route path="invoices/:id" element={<InvoiceDetail />} />

              <Route path="create" element={<CreateInvoice />} />
              <Route path="vendors" element={<Vendors />} />
              <Route path="clients" element={<Clients />} />
              <Route path="upload" element={<UploadExtract />} />
              <Route path="documents" element={<CompanyDocuments />} />
              <Route path="analytics" element={<Analytics />} />
              <Route path="chat" element={<AiChat />} />
              <Route path="settings" element={<Settings />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ChatProvider>
    </ThemeProvider>
  )
}
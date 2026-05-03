import { createContext, useContext, useState, useCallback } from 'react'

const ChatContext = createContext(null)

export function ChatProvider({ children }) {
  const [isOpen, setIsOpen] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)
  const [messages, setMessages] = useState([
    {
      id: '0',
      role: 'assistant',
      content: 'Hello! I can answer questions about your invoices, vendors, payment trends, and financial summaries. Try asking something like "Which vendors have unpaid invoices?" or "What was the total revenue last month?"',
      timestamp: new Date().toISOString(),
    }
  ])
  const [isLoading, setIsLoading] = useState(false)

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isLoading) return

    const userMsg = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg])
    setIsLoading(true)

    try {
      const res = await fetch('/api/v1/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text }),
      })
      const data = res.ok ? await res.json() : null
      const content = data?.answer || 'The query endpoint is not available yet.'

      // Map backend sources[].citation to the citations array that ChatPanel renders
      const citations = (data?.sources || []).map(s => s.citation).filter(Boolean)

      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content,
        citations,
        queryType: data?.query_type || null,
        sources: data?.sources || [],
        timestamp: new Date().toISOString(),
      }])
    } catch {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Could not reach the backend. Ensure the FastAPI server is running on port 8000.',
        timestamp: new Date().toISOString(),
        error: true,
      }])
    } finally {
      setIsLoading(false)
    }
  }, [isLoading])

  const clearMessages = () => setMessages([{
    id: '0',
    role: 'assistant',
    content: 'Conversation cleared. How can I help you?',
    timestamp: new Date().toISOString(),
  }])

  return (
    <ChatContext.Provider value={{
      isOpen, setIsOpen,
      isExpanded, setIsExpanded,
      messages, isLoading,
      sendMessage, clearMessages,
    }}>
      {children}
    </ChatContext.Provider>
  )
}

export const useChat = () => useContext(ChatContext)
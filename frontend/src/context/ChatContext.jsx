import React, { createContext, useContext, useState } from 'react';
import { queryApi } from '../lib/api';

const ChatContext = createContext(null);

export function ChatProvider({ children }) {
  const [messages,  setMessages]  = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isOpen,    setIsOpen]    = useState(false);

  async function sendMessage(text) {
    const userMsg = {
      id: Date.now(), role: 'user', content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);
    try {
      const data = await queryApi.ask(text);
      const aiMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: data.answer || data.response || 'No response.',
        timestamp: new Date().toISOString(),
        queryType: data.query_type,
        sources:   data.sources || [],
        citations: (data.sources || []).map(s => s.citation).filter(Boolean),
      };
      setMessages(prev => [...prev, aiMsg]);
    } catch (err) {
      const errMsg = {
        id: Date.now() + 1, role: 'assistant',
        content: err.message, error: true,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
    }
  }

  function clearMessages() { setMessages([]); }

  return (
    <ChatContext.Provider value={{
      messages, sendMessage, clearMessages, isLoading,
      isOpen, setIsOpen,
    }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() { return useContext(ChatContext); }
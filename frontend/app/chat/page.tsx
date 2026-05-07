'use client';

import { useCallback, useEffect, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import useSWR from 'swr';
import { streamChat, getDocuments, getConversationHistory } from '@/lib/api';
import type { DocumentsListResponse, Message } from '@/types';
import ChatWindow from '@/components/chat/ChatWindow';
import MessageInput from '@/components/chat/MessageInput';
import { RotateCcw } from 'lucide-react';

const fetcher = () => getDocuments(0, 100);

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());

  const { data } = useSWR<DocumentsListResponse>('/api/documents', fetcher, {
    refreshInterval: 5000,
  });

  const readyDocs = (data?.items ?? []).filter((d) => d.status === 'ready');

  useEffect(() => {
    const stored = localStorage.getItem('conversationId');
    if (!stored) return;
    setConversationId(stored);
    getConversationHistory(stored)
      .then((msgs) => { if (msgs.length > 0) setMessages(msgs); })
      .catch(() => { localStorage.removeItem('conversationId'); });
  }, []);

  const handleNewConversation = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    setInputValue('');
    localStorage.removeItem('conversationId');
  }, []);

  const toggleDocFilter = useCallback((docId: string) => {
    setSelectedDocIds((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  }, []);

  const handleSubmit = useCallback(
    async (text: string) => {
      if (isStreaming) return;

      const userMsg: Message = {
        id: uuidv4(),
        role: 'user',
        content: text,
        sources: [],
      };

      const assistantMsgId = uuidv4();
      const assistantMsg: Message = {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        sources: [],
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setInputValue('');
      setIsStreaming(true);

      const convId = conversationId ?? uuidv4();
      if (!conversationId) {
        setConversationId(convId);
        localStorage.setItem('conversationId', convId);
      }

      await streamChat(
        {
          message: text,
          conversation_id: convId,
          document_ids: selectedDocIds.size > 0 ? Array.from(selectedDocIds) : null,
        },
        (token) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: m.content + token }
                : m,
            ),
          );
        },
        (_returnedConvId, sources) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, sources, isStreaming: false }
                : m,
            ),
          );
          setIsStreaming(false);
        },
        (err) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: `Error: ${err.message}`,
                    isStreaming: false,
                  }
                : m,
            ),
          );
          setIsStreaming(false);
        },
      );
    },
    [isStreaming, conversationId, selectedDocIds],
  );

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 border-r border-gray-200 bg-white flex flex-col">
        <div className="px-3 py-3 border-b border-gray-100">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Filtrar por documento
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            Sin selección = busca en todo
          </p>
        </div>
        <div className="flex-1 overflow-y-auto py-2">
          {readyDocs.length === 0 ? (
            <p className="px-3 py-2 text-xs text-gray-400">
              No hay documentos listos
            </p>
          ) : (
            readyDocs.map((doc) => (
              <button
                key={doc.id}
                onClick={() => toggleDocFilter(doc.id)}
                className={`w-full text-left px-3 py-2 text-xs transition-colors ${
                  selectedDocIds.has(doc.id)
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                <span className="truncate block" title={doc.original_filename}>
                  {doc.original_filename}
                </span>
                <span className="text-gray-400">
                  {doc.chunk_count}c · {doc.image_count}i
                </span>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Chat area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="px-4 py-2 border-b border-gray-200 bg-white flex items-center justify-between">
          <span className="text-xs text-gray-400">
            {messages.length === 0
              ? 'Nueva conversación'
              : `${Math.floor(messages.length / 2)} intercambio${messages.length > 2 ? 's' : ''}`}
          </span>
          <button
            onClick={handleNewConversation}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 px-2 py-1 rounded-md hover:bg-gray-100 transition-colors"
          >
            <RotateCcw size={12} />
            Nueva conversación
          </button>
        </div>

        <ChatWindow messages={messages} />

        <div className="px-4 py-3 border-t border-gray-200 bg-white">
          <MessageInput
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSubmit}
            isStreaming={isStreaming}
          />
          {selectedDocIds.size > 0 && (
            <p className="text-xs text-blue-600 mt-1.5">
              Filtrando por {selectedDocIds.size} documento{selectedDocIds.size > 1 ? 's' : ''}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

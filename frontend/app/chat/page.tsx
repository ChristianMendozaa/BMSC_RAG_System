'use client';

import { useCallback, useEffect, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import useSWR from 'swr';
import * as Dialog from '@radix-ui/react-dialog';
import { streamChat, getDocuments, getConversationHistory } from '@/lib/api';
import type { DocumentsListResponse, Message } from '@/types';
import ChatWindow from '@/components/chat/ChatWindow';
import MessageInput from '@/components/chat/MessageInput';
import { RotateCcw, SlidersHorizontal, X, FileText } from 'lucide-react';

const fetcher = () => getDocuments(0, 100);

function SidebarContent({
  readyDocs,
  selectedDocIds,
  toggleDocFilter,
  onNewConversation,
  messages,
}: {
  readyDocs: { id: string; original_filename: string }[];
  selectedDocIds: Set<string>;
  toggleDocFilter: (id: string) => void;
  onNewConversation: () => void;
  messages: Message[];
}) {
  const questionCount = Math.floor(messages.length / 2);

  return (
    <div className="flex flex-col h-full">
      {/* Sidebar header */}
      <div
        className="px-4 py-4"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        <p
          className="text-xs font-semibold uppercase tracking-wider mb-0.5"
          style={{ color: 'var(--gold-muted)', fontFamily: 'DM Sans, sans-serif' }}
        >
          Buscar en...
        </p>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          Sin filtro: consulta todos los archivos
        </p>
      </div>

      {/* Document list */}
      <div className="flex-1 overflow-y-auto py-2">
        {readyDocs.length === 0 ? (
          <div className="px-4 py-6 text-center">
            <FileText size={24} className="mx-auto mb-2 opacity-30" style={{ color: 'var(--text-muted)' }} />
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              No hay documentos disponibles
            </p>
          </div>
        ) : (
          readyDocs.map((doc) => {
            const isSelected = selectedDocIds.has(doc.id);
            return (
              <button
                key={doc.id}
                onClick={() => toggleDocFilter(doc.id)}
                className="w-full text-left px-4 py-2.5 text-xs transition-all duration-150 flex items-center gap-2"
                style={{
                  color: isSelected ? 'var(--gold-bright)' : 'var(--text-secondary)',
                  background: isSelected ? 'var(--gold-subtle)' : 'transparent',
                  borderLeft: isSelected ? '2px solid var(--gold-bright)' : '2px solid transparent',
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) {
                    (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-hover)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) {
                    (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                  }
                }}
              >
                <FileText size={12} className="shrink-0 opacity-60" />
                <span className="truncate block" title={doc.original_filename}>
                  {doc.original_filename}
                </span>
              </button>
            );
          })
        )}
      </div>

      {/* Sidebar footer */}
      <div className="p-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
        {questionCount > 0 && (
          <p className="text-xs mb-2 text-center" style={{ color: 'var(--text-muted)' }}>
            {questionCount} {questionCount === 1 ? 'pregunta realizada' : 'preguntas realizadas'}
          </p>
        )}
        <button
          onClick={onNewConversation}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors"
          style={{
            border: '1px solid var(--border-gold)',
            color: 'var(--gold-muted)',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--gold-bright)';
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--gold-bright)';
            (e.currentTarget as HTMLButtonElement).style.background = 'var(--gold-subtle)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-gold)';
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--gold-muted)';
            (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
          }}
        >
          <RotateCcw size={12} />
          Nueva consulta
        </button>
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);

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
                ? { ...m, content: `Lo sentimos, ocurrió un error: ${err.message}`, isStreaming: false }
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
      {/* Desktop Sidebar */}
      <aside
        className="hidden md:flex w-44 lg:w-56 shrink-0 flex-col"
        style={{
          background: 'var(--bg-elevated)',
          borderRight: '1px solid var(--border-subtle)',
        }}
      >
        <SidebarContent
          readyDocs={readyDocs}
          selectedDocIds={selectedDocIds}
          toggleDocFilter={toggleDocFilter}
          onNewConversation={handleNewConversation}
          messages={messages}
        />
      </aside>

      {/* Chat area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Mobile toolbar */}
        <div
          className="md:hidden flex items-center justify-between px-4 py-2"
          style={{
            background: 'var(--bg-surface)',
            borderBottom: '1px solid var(--border-subtle)',
          }}
        >
          <Dialog.Root open={mobileFilterOpen} onOpenChange={setMobileFilterOpen}>
            <Dialog.Trigger asChild>
              <button
                className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg transition-colors"
                style={{
                  border: '1px solid var(--border-default)',
                  color: selectedDocIds.size > 0 ? 'var(--gold-bright)' : 'var(--text-secondary)',
                  background: selectedDocIds.size > 0 ? 'var(--gold-subtle)' : 'transparent',
                }}
              >
                <SlidersHorizontal size={13} />
                {selectedDocIds.size > 0
                  ? `${selectedDocIds.size} filtro${selectedDocIds.size > 1 ? 's' : ''}`
                  : 'Filtrar'}
              </button>
            </Dialog.Trigger>

            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 bg-black/70 z-40" />
              <Dialog.Content
                className="fixed left-0 top-0 h-full w-72 z-50 flex flex-col"
                style={{
                  background: 'var(--bg-elevated)',
                  borderRight: '1px solid var(--border-gold)',
                }}
              >
                <div
                  className="flex items-center justify-between px-4 py-3"
                  style={{ borderBottom: '1px solid var(--border-subtle)' }}
                >
                  <span
                    className="text-sm font-semibold"
                    style={{ color: 'var(--gold-muted)', fontFamily: 'Playfair Display, serif' }}
                  >
                    Buscar en...
                  </span>
                  <Dialog.Close asChild>
                    <button style={{ color: 'var(--text-muted)' }} className="p-1 rounded">
                      <X size={16} />
                    </button>
                  </Dialog.Close>
                </div>
                <div className="flex-1 overflow-y-auto">
                  <SidebarContent
                    readyDocs={readyDocs}
                    selectedDocIds={selectedDocIds}
                    toggleDocFilter={toggleDocFilter}
                    onNewConversation={() => {
                      handleNewConversation();
                      setMobileFilterOpen(false);
                    }}
                    messages={messages}
                  />
                </div>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>

          <button
            onClick={handleNewConversation}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors"
            style={{ color: 'var(--text-muted)' }}
          >
            <RotateCcw size={12} />
            Nueva consulta
          </button>
        </div>

        <ChatWindow messages={messages} />

        {/* Input area */}
        <div
          className="px-4 py-3"
          style={{
            borderTop: '1px solid var(--border-subtle)',
            background: 'var(--bg-surface)',
          }}
        >
          <MessageInput
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSubmit}
            isStreaming={isStreaming}
          />
          {selectedDocIds.size > 0 && (
            <p className="text-xs mt-1.5" style={{ color: 'var(--gold-muted)' }}>
              Buscando en {selectedDocIds.size} documento{selectedDocIds.size > 1 ? 's' : ''} seleccionado{selectedDocIds.size > 1 ? 's' : ''}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

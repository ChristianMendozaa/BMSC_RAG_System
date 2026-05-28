'use client';

import { useCallback, useEffect, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {
  streamChat,
  getAccessibleCollections,
  getChatSession,
  listChatSessions,
  resumeCheckSession,
  deleteChatSession,
  getDocumentDownloadUrl,
  API_URL,
} from '@/lib/api';
import type { AccessibleCollectionOut, BlockerItem, ChatSessionListItem } from '@/lib/api';
import type { Message } from '@/types';
import ChatWindow from '@/components/chat/ChatWindow';
import MessageInput from '@/components/chat/MessageInput';
import ChatHistoryPanel, { ResumeBlockerModal } from '@/components/chat/ChatHistoryPanel';
import ConfirmModal from '@/components/ui/ConfirmModal';
import {
  RotateCcw,
  SlidersHorizontal,
  X,
  ChevronDown,
  ChevronRight,
  Layers,
  FileText,
  AlertCircle,
  ExternalLink,
  Download,
  Loader2,
} from 'lucide-react';

// ── Sidebar ────────────────────────────────────────────────────────────────

interface SidebarProps {
  collections: AccessibleCollectionOut[];
  activeCollectionId: string | null;
  selectedDocIds: Set<string>;
  expandedCollections: Set<string>;
  onSelectCollection: (id: string) => void;
  onToggleDoc: (docId: string) => void;
  onToggleExpand: (id: string) => void;
  onNewConversation: () => void;
  messages: Message[];
  // history
  sessions: ChatSessionListItem[];
  sessionsLoading: boolean;
  activeSessionId: string | null;
  onResumeSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

function SidebarContent({
  collections,
  activeCollectionId,
  selectedDocIds,
  expandedCollections,
  onSelectCollection,
  onToggleDoc,
  onToggleExpand,
  onNewConversation,
  messages,
  sessions,
  sessionsLoading,
  activeSessionId,
  onResumeSession,
  onDeleteSession,
}: SidebarProps) {
  const [downloadingCollId, setDownloadingCollId] = useState<string | null>(null);

  const questionCount = Math.floor(messages.length / 2);
  const activeCol = collections.find((c) => c.id === activeCollectionId);

  async function handleDownloadCollection(col: AccessibleCollectionOut) {
    if (downloadingCollId) return;
    setDownloadingCollId(col.id);
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    try {
      for (let i = 0; i < col.documents.length; i++) {
        const doc = col.documents[i];
        const res = await fetch(
          `${API_URL}/api/documents/${doc.doc_id}/download?dl=1`,
          { headers: token ? { Authorization: `Bearer ${token}` } : {} },
        );
        if (!res.ok) { console.warn(`Error descargando ${doc.original_filename}: ${res.status}`); continue; }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = doc.original_filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        if (i < col.documents.length - 1) await new Promise((r) => setTimeout(r, 400));
      }
    } finally {
      setDownloadingCollId(null);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <p
          className="text-xs font-semibold uppercase tracking-wider"
          style={{ color: 'var(--gold-muted)', fontFamily: 'DM Sans, sans-serif' }}
        >
          Mis Colecciones
        </p>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
          Elige una colección para consultar
        </p>
      </div>

      {/* Scope activo */}
      {activeCollectionId && (
        <div
          className="mx-3 mt-2 px-3 py-2 rounded-lg text-xs"
          style={{ background: 'var(--gold-subtle)', border: '1px solid var(--border-gold)' }}
        >
          <p className="font-semibold truncate" style={{ color: 'var(--gold-bright)' }}>
            {selectedDocIds.size > 0
              ? `${selectedDocIds.size} doc${selectedDocIds.size > 1 ? 's' : ''} · ${activeCol?.name}`
              : `Toda la colección: ${activeCol?.name}`}
          </p>
        </div>
      )}

      {/* Collection list — flex-1 so it takes available space, history sits below */}
      <div className="flex-1 overflow-y-auto py-2 min-h-0">
        {collections.length === 0 ? (
          <div className="px-4 py-6 text-center">
            <Layers size={24} className="mx-auto mb-2 opacity-30" style={{ color: 'var(--text-muted)' }} />
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              No tienes acceso a ninguna colección
            </p>
          </div>
        ) : (
          collections.map((col) => {
            const isActive = col.id === activeCollectionId;
            const isExpanded = expandedCollections.has(col.id);
            const isDownloading = downloadingCollId === col.id;

            return (
              <div key={col.id} className="mb-0.5">
                <div
                  className="flex items-center gap-1 px-2 py-1.5 mx-2 rounded-lg group/col"
                  style={{
                    background: isActive ? 'var(--gold-subtle)' : 'transparent',
                    border: isActive ? '1px solid var(--border-gold)' : '1px solid transparent',
                  }}
                >
                  <button
                    onClick={() => onToggleExpand(col.id)}
                    className="p-0.5 rounded transition-colors shrink-0"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                  </button>
                  <button
                    onClick={() => onSelectCollection(col.id)}
                    className="flex-1 text-left text-xs truncate transition-colors"
                    style={{
                      color: isActive ? 'var(--gold-bright)' : 'var(--text-secondary)',
                      fontWeight: isActive ? 600 : 400,
                    }}
                    title={col.name}
                  >
                    {col.name}
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDownloadCollection(col); }}
                    disabled={!!downloadingCollId}
                    className="p-1 rounded transition-all shrink-0 opacity-0 group-hover/col:opacity-100 disabled:cursor-not-allowed"
                    style={{ color: 'var(--text-muted)' }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--gold-bright)'; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)'; }}
                    title="Descargar toda la colección"
                  >
                    {isDownloading ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                  </button>
                  <span className="text-xs shrink-0 opacity-60" style={{ color: 'var(--text-muted)' }}>
                    {col.documents.length}
                  </span>
                </div>

                {isExpanded && (
                  <div className="ml-6 mt-0.5 mb-1">
                    {col.documents.length === 0 ? (
                      <p className="text-xs px-2 py-1" style={{ color: 'var(--text-muted)' }}>
                        Sin documentos disponibles
                      </p>
                    ) : (
                      col.documents.map((doc) => {
                        const isDocSelected = selectedDocIds.has(doc.doc_id);
                        const viewUrl = getDocumentDownloadUrl(doc.doc_id);
                        const dlUrl = getDocumentDownloadUrl(doc.doc_id, true);
                        return (
                          <div
                            key={doc.doc_id}
                            className="flex items-center gap-1 group/doc rounded-md transition-all"
                            style={{ background: isDocSelected ? 'var(--gold-subtle)' : 'transparent' }}
                          >
                            <button
                              onClick={() => {
                                if (!isActive) onSelectCollection(col.id);
                                onToggleDoc(doc.doc_id);
                              }}
                              className="flex-1 text-left flex items-center gap-2 px-2 py-1.5 text-xs transition-all min-w-0"
                              style={{
                                color: isDocSelected ? 'var(--gold-bright)' : 'var(--text-secondary)',
                                opacity: !isActive && !isDocSelected ? 0.6 : 1,
                              }}
                              title={doc.original_filename}
                            >
                              <FileText size={11} className="shrink-0 opacity-70" />
                              <span className="truncate">{doc.original_filename}</span>
                            </button>
                            <div className="flex items-center gap-0.5 pr-1 opacity-0 group-hover/doc:opacity-100 transition-opacity shrink-0">
                              <a
                                href={viewUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="p-1 rounded transition-colors"
                                style={{ color: 'var(--text-muted)' }}
                                onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--gold-bright)'; }}
                                onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-muted)'; }}
                                title="Ver documento"
                              >
                                <ExternalLink size={10} />
                              </a>
                              <a
                                href={dlUrl}
                                download
                                onClick={(e) => e.stopPropagation()}
                                className="p-1 rounded transition-colors"
                                style={{ color: 'var(--text-muted)' }}
                                onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--gold-bright)'; }}
                                onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-muted)'; }}
                                title="Descargar documento"
                              >
                                <Download size={10} />
                              </a>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* History panel — below collections, above footer */}
      <ChatHistoryPanel
        sessions={sessions}
        activeSessionId={activeSessionId}
        onResume={onResumeSession}
        onDelete={onDeleteSession}
        loading={sessionsLoading}
      />

      {/* Footer */}
      <div className="p-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
        {questionCount > 0 && (
          <p className="text-xs mb-2 text-center" style={{ color: 'var(--text-muted)' }}>
            {questionCount} {questionCount === 1 ? 'pregunta realizada' : 'preguntas realizadas'}
          </p>
        )}
        <button
          onClick={onNewConversation}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors"
          style={{ border: '1px solid var(--border-gold)', color: 'var(--gold-muted)' }}
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

// ── Chat page ──────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);

  // Collections & selection
  const [collections, setCollections] = useState<AccessibleCollectionOut[]>([]);
  const [loadingCols, setLoadingCols] = useState(true);
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(null);
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());
  const [expandedCollections, setExpandedCollections] = useState<Set<string>>(new Set());

  // History
  const [sessions, setSessions] = useState<ChatSessionListItem[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);

  // Modals
  const [blockerModal, setBlockerModal] = useState<{ open: boolean; blockers: BlockerItem[] }>({
    open: false,
    blockers: [],
  });
  const [deleteModal, setDeleteModal] = useState<{ open: boolean; sessionId: string | null }>({
    open: false,
    sessionId: null,
  });

  const hasScope = activeCollectionId !== null;

  // Load collections
  useEffect(() => {
    getAccessibleCollections()
      .then((cols) => {
        setCollections(cols);
        if (cols.length === 1) setExpandedCollections(new Set([cols[0].id]));
      })
      .catch(() => {})
      .finally(() => setLoadingCols(false));
  }, []);

  // Load chat history (replaces localStorage)
  const refreshSessions = useCallback(() => {
    listChatSessions()
      .then(setSessions)
      .catch(() => {})
      .finally(() => setSessionsLoading(false));
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  const handleNewConversation = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    setInputValue('');
    setActiveCollectionId(null);
    setSelectedDocIds(new Set());
  }, []);

  // Resume a saved session
  const handleResumeSession = useCallback(
    async (id: string) => {
      try {
        const check = await resumeCheckSession(id);
        if (!check.can_resume) {
          setBlockerModal({ open: true, blockers: check.blockers });
          return;
        }

        // Load session detail
        const detail = await getChatSession(id);

        // Hydrate messages
        const msgs: Message[] = detail.messages.map((m) => ({
          id: crypto.randomUUID(),
          role: m.role as Message['role'],
          content: m.content,
          sources: m.sources ?? [],
        }));
        setMessages(msgs);
        setSessionId(id);

        // Re-fetch collections to ensure fresh state, then restore selection
        const freshCols = await getAccessibleCollections();
        setCollections(freshCols);

        // Restore active collection
        const colId = detail.collection_id;
        if (colId) {
          const colExists = freshCols.some((c) => c.id === colId);
          if (colExists) {
            setActiveCollectionId(colId);
            setExpandedCollections((prev) => new Set([...prev, colId]));
          }
        }

        // Restore selected doc IDs (intersect with what's still accessible)
        const accessibleDocIds = new Set(
          freshCols.flatMap((c) => c.documents.map((d) => d.doc_id)),
        );
        const restored = new Set(
          detail.document_ids.filter((did) => accessibleDocIds.has(did)),
        );
        setSelectedDocIds(restored);
      } catch (err) {
        console.error('Error al reanudar sesión:', err);
      }
    },
    [],
  );

  // Delete a session
  const handleDeleteSession = useCallback((id: string) => {
    setDeleteModal({ open: true, sessionId: id });
  }, []);

  const confirmDeleteSession = useCallback(async () => {
    if (!deleteModal.sessionId) return;
    try {
      await deleteChatSession(deleteModal.sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== deleteModal.sessionId));
      if (sessionId === deleteModal.sessionId) {
        handleNewConversation();
      }
    } catch (err) {
      console.error('Error al eliminar sesión:', err);
    }
  }, [deleteModal.sessionId, sessionId, handleNewConversation]);

  const handleSelectCollection = useCallback((colId: string) => {
    setActiveCollectionId(colId);
    setSelectedDocIds(new Set());
    setExpandedCollections((prev) => {
      const next = new Set(prev);
      next.add(colId);
      return next;
    });
  }, []);

  const handleToggleDoc = useCallback((docId: string) => {
    setSelectedDocIds((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  }, []);

  const handleToggleExpand = useCallback((colId: string) => {
    setExpandedCollections((prev) => {
      const next = new Set(prev);
      if (next.has(colId)) next.delete(colId);
      else next.add(colId);
      return next;
    });
  }, []);

  const handleSubmit = useCallback(
    async (text: string) => {
      if (isStreaming || !hasScope) return;

      const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content: text, sources: [] };
      const assistantMsgId = crypto.randomUUID();
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

      await streamChat(
        {
          message: text,
          session_id: sessionId,
          collection_id: activeCollectionId,
          document_ids: selectedDocIds.size > 0 ? Array.from(selectedDocIds) : null,
        },
        (token) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, content: m.content + token } : m,
            ),
          );
        },
        (newSessionId, sources) => {
          // First message: server returned a new session_id
          if (!sessionId && newSessionId) {
            setSessionId(newSessionId);
            // Refresh history list so the new session appears
            listChatSessions().then(setSessions).catch(() => {});
          } else {
            // Subsequent message: refresh to update updated_at ordering
            listChatSessions().then(setSessions).catch(() => {});
          }
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, sources, isStreaming: false } : m,
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
    [isStreaming, hasScope, sessionId, activeCollectionId, selectedDocIds],
  );

  const sidebarProps: SidebarProps = {
    collections,
    activeCollectionId,
    selectedDocIds,
    expandedCollections,
    onSelectCollection: handleSelectCollection,
    onToggleDoc: handleToggleDoc,
    onToggleExpand: handleToggleExpand,
    onNewConversation: handleNewConversation,
    messages,
    sessions,
    sessionsLoading,
    activeSessionId: sessionId,
    onResumeSession: handleResumeSession,
    onDeleteSession: handleDeleteSession,
  };

  const activeCol = collections.find((c) => c.id === activeCollectionId);

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Desktop Sidebar */}
      <aside
        className="hidden md:flex w-48 lg:w-60 shrink-0 flex-col"
        style={{
          background: 'var(--bg-elevated)',
          borderRight: '1px solid var(--border-subtle)',
        }}
      >
        {loadingCols ? (
          <div className="flex-1 flex items-center justify-center">
            <div
              className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin"
              style={{ borderColor: 'var(--gold-muted)', borderTopColor: 'transparent' }}
            />
          </div>
        ) : (
          <SidebarContent {...sidebarProps} />
        )}
      </aside>

      {/* Chat area */}
      <div className="flex-1 relative overflow-hidden">
        {/* Mobile toolbar */}
        <div
          className="absolute top-0 left-0 right-0 z-10 md:hidden flex items-center justify-between px-4 py-2"
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
                  color: hasScope ? 'var(--gold-bright)' : 'var(--text-secondary)',
                  background: hasScope ? 'var(--gold-subtle)' : 'transparent',
                }}
              >
                <SlidersHorizontal size={13} />
                {hasScope ? activeCol?.name ?? 'Colección' : 'Seleccionar colección'}
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
                    Mis Colecciones
                  </span>
                  <Dialog.Close asChild>
                    <button style={{ color: 'var(--text-muted)' }} className="p-1 rounded">
                      <X size={16} />
                    </button>
                  </Dialog.Close>
                </div>
                <div className="flex-1 overflow-y-auto">
                  <SidebarContent
                    {...sidebarProps}
                    onNewConversation={() => {
                      handleNewConversation();
                      setMobileFilterOpen(false);
                    }}
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

        {/* Content area */}
        <div className="absolute inset-0 flex flex-col overflow-hidden md:pt-0 pt-12">
          {!hasScope && messages.length === 0 && (
            <div className="flex-1 flex flex-col items-center justify-center px-8 text-center">
              <Layers size={40} className="mb-4 opacity-20" style={{ color: 'var(--gold-muted)' }} />
              <p
                className="text-sm font-medium mb-1"
                style={{ color: 'var(--text-secondary)', fontFamily: 'Playfair Display, serif' }}
              >
                Selecciona una colección
              </p>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Elige una colección en el panel izquierdo para comenzar a consultar documentos.
              </p>
            </div>
          )}
          {(hasScope || messages.length > 0) && <ChatWindow messages={messages} />}
        </div>

        {/* Input */}
        <div className="absolute bottom-0 left-0 right-0 px-4 pb-4 pt-1">
          <div
            className="max-w-2xl mx-auto rounded-2xl px-4 py-3"
            style={{
              background: 'rgba(10, 26, 16, 0.6)',
              backdropFilter: 'blur(12px)',
              WebkitBackdropFilter: 'blur(12px)',
              border: '1px solid var(--border-gold)',
              boxShadow: '0 -4px 32px rgba(0,0,0,0.45), 0 2px 8px rgba(0,0,0,0.3)',
            }}
          >
            {!hasScope && (
              <div
                className="flex items-center gap-2 mb-2 px-2 py-1.5 rounded-lg text-xs"
                style={{
                  background: 'rgba(212, 168, 67, 0.06)',
                  border: '1px solid var(--border-gold)',
                  color: 'var(--gold-muted)',
                }}
              >
                <AlertCircle size={12} />
                Selecciona una colección en el panel izquierdo para habilitar el chat
              </div>
            )}
            {hasScope && (
              <p className="text-xs mb-1.5" style={{ color: 'var(--gold-muted)' }}>
                {selectedDocIds.size > 0
                  ? `Consultando ${selectedDocIds.size} documento${selectedDocIds.size > 1 ? 's' : ''} de "${activeCol?.name}"`
                  : `Consultando toda la colección: "${activeCol?.name}"`}
              </p>
            )}
            <MessageInput
              value={inputValue}
              onChange={setInputValue}
              onSubmit={handleSubmit}
              isStreaming={isStreaming}
              disabled={!hasScope}
            />
          </div>
        </div>
      </div>

      {/* Resume blocker modal */}
      <ResumeBlockerModal
        open={blockerModal.open}
        onOpenChange={(open) => setBlockerModal((prev) => ({ ...prev, open }))}
        blockers={blockerModal.blockers}
        onNewConversation={handleNewConversation}
      />

      {/* Delete confirm modal */}
      <ConfirmModal
        open={deleteModal.open}
        onOpenChange={(open) => setDeleteModal((prev) => ({ ...prev, open }))}
        title="Eliminar conversación"
        description="¿Estás seguro? Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        destructive
        onConfirm={confirmDeleteSession}
      />
    </div>
  );
}

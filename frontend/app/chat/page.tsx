'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import * as Dialog from '@radix-ui/react-dialog';
import {
  getAccessibleCollections,
  getChatSession,
  listChatSessions,
  resumeCheckSession,
  deleteChatSession,
  renameChatSession,
  getDocumentDownloadUrl,
  API_URL,
} from '@/lib/api';
import { useChatStream } from '@/lib/chat-stream-context';
import type { AccessibleCollectionOut, BlockerItem, ChatSessionListItem } from '@/lib/api';
import type { ChatMode, Message } from '@/types';
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
  Pencil,
  SearchCheck,
  Zap,
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
  onRenameSession: (id: string) => void;
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
  onRenameSession,
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
      {activeCollectionId && activeCol && activeCol.documents.length > 0 && (
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
        onRename={onRenameSession}
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
  const chatStream = useChatStream();

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  // Key used to track the in-progress generation (temp key or real session_id)
  const [streamKey, setStreamKey] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);
  const [chatMode, setChatMode] = useState<ChatMode>('fast');

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
  const [renameModal, setRenameModal] = useState<{ open: boolean; sessionId: string | null; currentTitle: string }>({
    open: false,
    sessionId: null,
    currentTitle: '',
  });

  const activeCol = collections.find((c) => c.id === activeCollectionId) ?? null;
  const hasScope = activeCol !== null && activeCol.documents.length > 0;
  const isEmptyCollectionSelected = activeCollectionId !== null && (activeCol === null || activeCol.documents.length === 0);

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
    setStreamKey(null);
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
          id: uuidv4(),
          role: m.role as Message['role'],
          content: m.content,
          sources: m.sources ?? [],
        }));
        setMessages(msgs);
        setSessionId(id);
        setStreamKey(id);

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

        // Attach to any still-running background generation
        await chatStream.attachIfActive(id);
      } catch (err) {
        console.error('Error al reanudar sesión:', err);
      }
    },
    [chatStream],
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

  // Rename session
  const handleRenameSession = useCallback((id: string) => {
    const session = sessions.find((s) => s.id === id);
    setRenameModal({ open: true, sessionId: id, currentTitle: session?.title ?? '' });
  }, [sessions]);

  const confirmRenameSession = useCallback(async (newTitle: string) => {
    if (!renameModal.sessionId || !newTitle.trim()) return;
    try {
      const updated = await renameChatSession(renameModal.sessionId, newTitle.trim());
      setSessions((prev) => prev.map((s) => s.id === updated.id ? { ...s, title: updated.title } : s));
    } catch (err) {
      console.error('Error al renombrar sesión:', err);
    }
  }, [renameModal.sessionId]);

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

  // Current stream entry for this session
  const activeKey = streamKey ?? sessionId;
  const currentStream = activeKey ? chatStream.getStream(activeKey) : undefined;
  const isStreaming = currentStream?.status === 'streaming';

  // Fold a completed stream back into the messages array
  const chatStreamRef = useRef(chatStream);
  chatStreamRef.current = chatStream;

  useEffect(() => {
    if (!activeKey) return;
    if (!currentStream) return;
    if (currentStream.status !== 'done' && currentStream.status !== 'stopped') return;

    const finalMsg: Message = {
      id: uuidv4(),
      role: 'assistant',
      content: currentStream.content,
      sources: currentStream.sources,
      isStreaming: false,
      traceEvents: currentStream.traceEvents,
      mode: currentStream.mode,
    };
    setMessages((prev) => {
      const withoutPlaceholder = prev.filter((m) => !(m.role === 'assistant' && m.isStreaming));
      return [...withoutPlaceholder, finalMsg];
    });
    chatStreamRef.current.clearStream(activeKey);
    setStreamKey(null);
    listChatSessions().then(setSessions).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKey, currentStream?.status]);

  const handleSubmit = useCallback(
    (text: string) => {
      if (isStreaming || !hasScope) return;

      const userMsg: Message = { id: uuidv4(), role: 'user', content: text, sources: [] };
      setMessages((prev) => [...prev, userMsg]);
      setInputValue('');

      const key = chatStream.startStream(
        {
          message: text,
          session_id: sessionId,
          collection_id: activeCollectionId,
          document_ids: selectedDocIds.size > 0 ? Array.from(selectedDocIds) : null,
          mode: chatMode,
        },
        {
          onNewSession: (realId) => {
            setSessionId(realId);
            setStreamKey(realId);
            listChatSessions().then(setSessions).catch(() => {});
          },
        },
      );
      // If we already have a session_id, the key equals it; otherwise use temp key
      setStreamKey(sessionId ?? key);
    },
    [isStreaming, hasScope, sessionId, activeCollectionId, selectedDocIds, chatMode, chatStream],
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
    onRenameSession: handleRenameSession,
  };

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
                aria-describedby={undefined}
              >
                <div
                  className="flex items-center justify-between px-4 py-3"
                  style={{ borderBottom: '1px solid var(--border-subtle)' }}
                >
                  <Dialog.Title
                    className="text-sm font-semibold"
                    style={{ color: 'var(--gold-muted)', fontFamily: 'Playfair Display, serif' }}
                  >
                    Mis Colecciones
                  </Dialog.Title>
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
          {(hasScope || messages.length > 0) && (
            <ChatWindow
              messages={
                currentStream && currentStream.status === 'streaming'
                  ? [
                      ...messages,
                      {
                        id: '__streaming__',
                        role: 'assistant' as const,
                        content: currentStream.content,
                        sources: [],
                        isStreaming: true,
                        statusMessage: currentStream.statusMessage,
                        traceEvents: currentStream.traceEvents,
                        mode: currentStream.mode,
                      },
                    ]
                  : messages
              }
              title={sessionId ? (sessions.find((s) => s.id === sessionId)?.title ?? null) : null}
              onRename={sessionId ? () => handleRenameSession(sessionId) : undefined}
            />
          )}
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
            {!activeCollectionId && (
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
            {isEmptyCollectionSelected && (
              <div
                className="flex items-center gap-2 mb-2 px-2 py-1.5 rounded-lg text-xs"
                style={{
                  background: 'rgba(212, 168, 67, 0.06)',
                  border: '1px solid var(--border-gold)',
                  color: 'var(--gold-muted)',
                }}
              >
                <AlertCircle size={12} />
                La colección seleccionada no tiene documentos disponibles
              </div>
            )}
            {hasScope && (
              <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs" style={{ color: 'var(--gold-muted)' }}>
                  {selectedDocIds.size > 0
                    ? `Consultando ${selectedDocIds.size} documento${selectedDocIds.size > 1 ? 's' : ''} de "${activeCol?.name}"`
                    : `Consultando toda la colección: "${activeCol?.name}"`}
                </p>
                <div
                  className="inline-flex shrink-0 rounded-lg p-0.5"
                  style={{
                    border: '1px solid var(--border-gold)',
                    background: 'rgba(212, 168, 67, 0.06)',
                  }}
                  aria-label="Modo de respuesta"
                >
                  {([
                    { mode: 'fast' as const, label: 'Rápido', icon: Zap },
                    { mode: 'agentic' as const, label: 'Agéntico', icon: SearchCheck },
                  ]).map((item) => {
                    const Icon = item.icon;
                    const active = chatMode === item.mode;
                    return (
                      <button
                        key={item.mode}
                        type="button"
                        onClick={() => setChatMode(item.mode)}
                        disabled={isStreaming}
                        className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] transition-colors disabled:cursor-not-allowed disabled:opacity-60"
                        style={{
                          background: active ? 'var(--gold-bright)' : 'transparent',
                          color: active ? '#0A1A10' : 'var(--gold-muted)',
                        }}
                        title={item.mode === 'fast' ? 'Una búsqueda rápida' : 'Búsqueda con verificación adicional'}
                      >
                        <Icon size={12} />
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            <MessageInput
              value={inputValue}
              onChange={setInputValue}
              onSubmit={handleSubmit}
              onStop={sessionId ? () => chatStream.stopStream(sessionId) : undefined}
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

      {/* Rename modal */}
      <RenameChatModal
        open={renameModal.open}
        currentTitle={renameModal.currentTitle}
        onOpenChange={(open) => setRenameModal((prev) => ({ ...prev, open }))}
        onConfirm={confirmRenameSession}
      />
    </div>
  );
}

// ── RenameChatModal ────────────────────────────────────────────────────────

function RenameChatModal({
  open,
  currentTitle,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  currentTitle: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: (title: string) => Promise<void>;
}) {
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);

  // Reset field whenever modal opens
  useEffect(() => {
    if (open) setValue(currentTitle);
  }, [open, currentTitle]);

  const trimmed = value.trim();
  const valid = trimmed.length >= 1 && trimmed !== currentTitle;

  const handleSave = async () => {
    if (!valid || busy) return;
    setBusy(true);
    try {
      await onConfirm(trimmed);
      onOpenChange(false);
    } catch {
      // error already logged by caller
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={(o) => { if (!busy) onOpenChange(o); }}>
      <Dialog.Portal>
        <Dialog.Overlay
          style={{
            position: 'fixed', inset: 0, zIndex: 50,
            background: 'rgba(0,0,0,0.65)',
            backdropFilter: 'blur(3px)',
            WebkitBackdropFilter: 'blur(3px)',
          }}
        />
        <Dialog.Content
          style={{
            position: 'fixed', zIndex: 51,
            top: '50%', left: '50%',
            transform: 'translate(-50%, -50%)',
            width: '100%', maxWidth: '380px',
            padding: '24px',
            borderRadius: '16px',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-default)',
            boxShadow: '0 24px 64px rgba(0,0,0,0.55)',
          }}
        >
          <Dialog.Close asChild>
            <button
              style={{
                position: 'absolute', top: '14px', right: '14px',
                padding: '4px', borderRadius: '6px',
                border: 'none', background: 'transparent',
                cursor: 'pointer', color: 'var(--text-muted)',
                display: 'flex', alignItems: 'center',
              }}
            >
              <X size={14} />
            </button>
          </Dialog.Close>

          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', marginBottom: '16px' }}>
            <div
              style={{
                flexShrink: 0, width: '38px', height: '38px',
                borderRadius: '10px', display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                background: 'rgba(212,168,67,0.12)',
                border: '1px solid rgba(212,168,67,0.25)',
              }}
            >
              <Pencil size={16} style={{ color: 'var(--gold-bright)' }} />
            </div>
            <div style={{ flex: 1, paddingTop: '2px' }}>
              <Dialog.Title
                style={{
                  margin: '0 0 4px',
                  fontSize: '15px', fontWeight: 600,
                  fontFamily: 'Playfair Display, serif',
                  color: 'var(--text-primary)', lineHeight: 1.3,
                }}
              >
                Renombrar conversación
              </Dialog.Title>
              <Dialog.Description
                style={{
                  margin: 0, fontSize: '12px',
                  color: 'var(--text-muted)',
                  fontFamily: 'DM Sans, sans-serif', lineHeight: 1.45,
                }}
              >
                Escribe el nuevo nombre para esta conversación.
              </Dialog.Description>
            </div>
          </div>

          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); }}
            autoFocus
            maxLength={200}
            style={{
              width: '100%', padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid var(--border-default)',
              background: 'var(--bg-surface)',
              color: 'var(--text-primary)',
              fontSize: '13px',
              fontFamily: 'DM Sans, sans-serif',
              outline: 'none',
              marginBottom: '16px',
              boxSizing: 'border-box',
            }}
          />

          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
            <Dialog.Close asChild>
              <button
                disabled={busy}
                style={{
                  padding: '8px 16px', borderRadius: '8px',
                  fontSize: '12px', fontWeight: 500,
                  fontFamily: 'DM Sans, sans-serif',
                  cursor: 'pointer',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-default)',
                  color: 'var(--text-secondary)',
                }}
              >
                Cancelar
              </button>
            </Dialog.Close>
            <button
              onClick={handleSave}
              disabled={!valid || busy}
              style={{
                padding: '8px 16px', borderRadius: '8px',
                fontSize: '12px', fontWeight: 600,
                fontFamily: 'DM Sans, sans-serif',
                cursor: valid && !busy ? 'pointer' : 'not-allowed',
                background: 'var(--gold-bright)',
                border: 'none',
                color: '#0A1A10',
                opacity: valid && !busy ? 1 : 0.5,
                display: 'flex', alignItems: 'center', gap: '6px',
              }}
            >
              {busy && <Loader2 size={12} style={{ animation: 'spin 0.8s linear infinite' }} />}
              Guardar
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

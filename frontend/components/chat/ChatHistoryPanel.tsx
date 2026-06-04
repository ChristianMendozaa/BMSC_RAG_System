'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, History, MessageSquare, Pencil, Trash2, X } from 'lucide-react';
import type { BlockerItem, ChatSessionListItem } from '@/types';

// ── Relative time formatter (Spanish) ────────────────────────────────────────

function relativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  const diffH = Math.floor(diffMs / 3_600_000);
  const diffD = Math.floor(diffMs / 86_400_000);

  if (diffMin < 1) return 'ahora';
  if (diffMin < 60) return `hace ${diffMin} min`;
  if (diffH < 24) return `hace ${diffH} h`;
  if (diffD === 1) return 'ayer';
  if (diffD < 7) return `hace ${diffD} días`;
  return date.toLocaleDateString('es-ES', { day: 'numeric', month: 'short' });
}

// ── Blocker message formatter ─────────────────────────────────────────────────

function blockerMessage(item: BlockerItem): string {
  const t = item.doc_title_snapshot;
  switch (item.reason) {
    case 'doc_hard_deleted':
      return `El documento «${t}» fue eliminado permanentemente.`;
    case 'doc_obsolete':
      return `El documento «${t}» fue marcado como obsoleto.`;
    case 'doc_no_access':
      return `Ya no tienes acceso al documento «${t}».`;
    case 'doc_not_ready':
      return `El documento «${t}» no está disponible para consulta (en proceso o sin contenido).`;
    case 'collection_gone':
      return 'La colección asociada a este chat ya no existe.';
    case 'collection_inactive':
      return 'La colección asociada a este chat fue desactivada.';
    default:
      return item.reason;
  }
}

// ── ChatHistoryPanel ──────────────────────────────────────────────────────────

interface ChatHistoryPanelProps {
  sessions: ChatSessionListItem[];
  activeSessionId: string | null;
  onResume: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string) => void;
  loading: boolean;
}

export default function ChatHistoryPanel({
  sessions,
  activeSessionId,
  onResume,
  onDelete,
  onRename,
  loading,
}: ChatHistoryPanelProps) {
  return (
    <div
      style={{
        borderTop: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
        flex: '0 0 auto',
        maxHeight: '42%',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '10px 16px 8px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          flexShrink: 0,
        }}
      >
        <History size={11} style={{ color: 'var(--gold-muted)', flexShrink: 0 }} />
        <p
          style={{
            fontSize: '10px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: 'var(--gold-muted)',
            fontFamily: 'DM Sans, sans-serif',
            margin: 0,
          }}
        >
          Historial
        </p>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', paddingBottom: '6px', minHeight: 0 }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '16px 0' }}>
            <div
              style={{
                width: '16px',
                height: '16px',
                borderRadius: '50%',
                border: '2px solid var(--gold-muted)',
                borderTopColor: 'transparent',
                animation: 'spin 0.8s linear infinite',
              }}
            />
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        ) : sessions.length === 0 ? (
          <div
            style={{
              padding: '12px 16px 8px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '6px',
              textAlign: 'center',
            }}
          >
            <MessageSquare size={18} style={{ color: 'var(--text-muted)', opacity: 0.35 }} />
            <p
              style={{
                fontSize: '11px',
                color: 'var(--text-muted)',
                fontFamily: 'DM Sans, sans-serif',
                margin: 0,
                lineHeight: 1.4,
              }}
            >
              Sin conversaciones guardadas
            </p>
          </div>
        ) : (
          sessions.map((s) => (
            <SessionRow
              key={s.id}
              session={s}
              isActive={s.id === activeSessionId}
              onResume={onResume}
              onDelete={onDelete}
              onRename={onRename}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ── SessionRow ────────────────────────────────────────────────────────────────

interface SessionRowProps {
  session: ChatSessionListItem;
  isActive: boolean;
  onResume: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string) => void;
}

function SessionRow({ session, isActive, onResume, onDelete, onRename }: SessionRowProps) {
  return (
    <div
      className="group/session"
      onClick={() => onResume(session.id)}
      style={{
        margin: '1px 8px',
        padding: '7px 8px 6px',
        borderRadius: '8px',
        cursor: 'pointer',
        border: isActive ? '1px solid var(--border-gold)' : '1px solid transparent',
        background: isActive ? 'var(--gold-subtle)' : 'transparent',
        transition: 'background 120ms, border-color 120ms',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        gap: '3px',
        userSelect: 'none',
      }}
      onMouseEnter={(e) => {
        if (!isActive) (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-hover)';
      }}
      onMouseLeave={(e) => {
        if (!isActive) (e.currentTarget as HTMLDivElement).style.background = 'transparent';
      }}
    >
      {/* Title */}
      <span
        style={{
          fontSize: '11.5px',
          fontWeight: isActive ? 600 : 400,
          color: isActive ? 'var(--gold-bright)' : 'var(--text-secondary)',
          fontFamily: 'DM Sans, sans-serif',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          lineHeight: 1.35,
          paddingRight: '44px',
          display: 'block',
        }}
        title={session.title}
      >
        {session.title}
      </span>

      {/* Meta: doc count + time */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1px 5px',
            borderRadius: '10px',
            fontSize: '9.5px',
            fontWeight: 500,
            background: isActive ? 'rgba(212,168,67,0.15)' : 'rgba(255,255,255,0.05)',
            color: isActive ? 'var(--gold-muted)' : 'var(--text-muted)',
            border: isActive ? '1px solid rgba(212,168,67,0.2)' : '1px solid rgba(255,255,255,0.08)',
            fontFamily: 'DM Sans, sans-serif',
          }}
        >
          {session.document_count} doc{session.document_count !== 1 ? 's' : ''}
        </span>
        <span
          style={{
            fontSize: '10px',
            color: 'var(--text-muted)',
            fontFamily: 'DM Sans, sans-serif',
            opacity: 0.7,
          }}
        >
          {relativeTime(session.updated_at)}
        </span>
      </div>

      {/* Rename — visible only on hover */}
      <button
        className="opacity-0 group-hover/session:opacity-100"
        onClick={(e) => {
          e.stopPropagation();
          onRename(session.id);
        }}
        style={{
          position: 'absolute',
          right: '26px',
          top: '6px',
          padding: '2px',
          borderRadius: '4px',
          border: 'none',
          background: 'transparent',
          cursor: 'pointer',
          color: 'var(--text-muted)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'color 120ms',
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.color = 'var(--gold-bright)';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
        }}
        title="Renombrar conversación"
      >
        <Pencil size={11} />
      </button>
      {/* Trash — visible only on hover */}
      <button
        className="opacity-0 group-hover/session:opacity-100"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(session.id);
        }}
        style={{
          position: 'absolute',
          right: '6px',
          top: '6px',
          padding: '2px',
          borderRadius: '4px',
          border: 'none',
          background: 'transparent',
          cursor: 'pointer',
          color: 'var(--text-muted)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'color 120ms',
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.color = 'var(--status-red)';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
        }}
        title="Eliminar conversación"
      >
        <Trash2 size={11} />
      </button>
    </div>
  );
}

// ── ResumeBlockerModal ────────────────────────────────────────────────────────

interface ResumeBlockerModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  blockers: BlockerItem[];
  onNewConversation: () => void;
}

export function ResumeBlockerModal({
  open,
  onOpenChange,
  blockers,
  onNewConversation,
}: ResumeBlockerModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 50,
            background: 'rgba(0,0,0,0.65)',
            backdropFilter: 'blur(3px)',
            WebkitBackdropFilter: 'blur(3px)',
          }}
        />
        <Dialog.Content
          style={{
            position: 'fixed',
            zIndex: 51,
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: '100%',
            maxWidth: '380px',
            padding: '24px',
            borderRadius: '16px',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-default)',
            boxShadow: '0 24px 64px rgba(0,0,0,0.55)',
          }}
        >
          {/* Close */}
          <Dialog.Close asChild>
            <button
              style={{
                position: 'absolute',
                top: '14px',
                right: '14px',
                padding: '4px',
                borderRadius: '6px',
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                color: 'var(--text-muted)',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <X size={14} />
            </button>
          </Dialog.Close>

          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', marginBottom: '16px' }}>
            <div
              style={{
                flexShrink: 0,
                width: '38px',
                height: '38px',
                borderRadius: '10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'rgba(139, 30, 71, 0.14)',
                border: '1px solid rgba(139, 30, 71, 0.25)',
              }}
            >
              <AlertTriangle size={18} style={{ color: 'var(--status-red)' }} />
            </div>
            <div style={{ flex: 1, paddingTop: '2px' }}>
              <Dialog.Title
                style={{
                  margin: '0 0 4px',
                  fontSize: '15px',
                  fontWeight: 600,
                  fontFamily: 'Playfair Display, serif',
                  color: 'var(--text-primary)',
                  lineHeight: 1.3,
                }}
              >
                No se puede reanudar
              </Dialog.Title>
              <Dialog.Description
                style={{
                  margin: 0,
                  fontSize: '12px',
                  color: 'var(--text-muted)',
                  fontFamily: 'DM Sans, sans-serif',
                  lineHeight: 1.45,
                }}
              >
                Esta conversación no puede reanudarse porque:
              </Dialog.Description>
            </div>
          </div>

          {/* Blockers list */}
          <div
            style={{
              maxHeight: '160px',
              overflowY: 'auto',
              marginBottom: '20px',
              padding: '10px 12px',
              borderRadius: '10px',
              background: 'rgba(0,0,0,0.2)',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            }}
          >
            {blockers.map((b, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                <span
                  style={{
                    flexShrink: 0,
                    width: '5px',
                    height: '5px',
                    borderRadius: '50%',
                    background: 'var(--maroon)',
                    marginTop: '5px',
                  }}
                />
                <p
                  style={{
                    margin: 0,
                    fontSize: '12px',
                    color: 'var(--text-secondary)',
                    fontFamily: 'DM Sans, sans-serif',
                    lineHeight: 1.5,
                  }}
                >
                  {blockerMessage(b)}
                </p>
              </div>
            ))}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
            <Dialog.Close asChild>
              <button
                style={{
                  padding: '8px 16px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 500,
                  fontFamily: 'DM Sans, sans-serif',
                  cursor: 'pointer',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-default)',
                  color: 'var(--text-secondary)',
                  transition: 'background 120ms',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-hover)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-surface)';
                }}
              >
                Cancelar
              </button>
            </Dialog.Close>
            <button
              onClick={() => {
                onNewConversation();
                onOpenChange(false);
              }}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                fontSize: '12px',
                fontWeight: 600,
                fontFamily: 'DM Sans, sans-serif',
                cursor: 'pointer',
                background: 'var(--gold-bright)',
                border: 'none',
                color: '#0A1A10',
                transition: 'opacity 120ms',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.opacity = '0.85';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.opacity = '1';
              }}
            >
              Nueva conversación
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

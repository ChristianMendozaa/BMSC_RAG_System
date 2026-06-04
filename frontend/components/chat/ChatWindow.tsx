'use client';

import { useEffect, useRef } from 'react';
import Image from 'next/image';
import { Pencil } from 'lucide-react';
import type { Message } from '@/types';
import MessageBubble from './MessageBubble';

interface Props {
  messages: Message[];
  title?: string | null;
  onRename?: () => void;
}

export default function ChatWindow({ messages, title, onRename }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const titleHeader = title ? (
    <div
      style={{
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '8px 16px',
        borderBottom: '1px solid var(--border-subtle)',
        background: 'var(--bg-base)',
      }}
    >
      <span
        style={{
          flex: 1,
          fontSize: '13px',
          fontWeight: 600,
          fontFamily: 'Playfair Display, serif',
          color: 'var(--text-primary)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
        title={title}
      >
        {title}
      </span>
      {onRename && (
        <button
          onClick={onRename}
          title="Renombrar conversación"
          style={{
            flexShrink: 0,
            padding: '4px',
            borderRadius: '6px',
            border: 'none',
            background: 'transparent',
            cursor: 'pointer',
            color: 'var(--text-muted)',
            display: 'flex',
            alignItems: 'center',
            transition: 'color 120ms',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--gold-bright)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
          }}
        >
          <Pencil size={13} />
        </button>
      )}
    </div>
  ) : null;

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col overflow-hidden" style={{ background: 'var(--bg-base)' }}>
        {titleHeader}
        <div className="flex-1 flex items-center justify-center text-center px-6">
          <div>
            <div className="flex justify-center mb-5">
              <Image
                src="/LogoBMSC.png"
                alt="Banco Mercantil Santa Cruz"
                width={72}
                height={72}
                className="opacity-25"
                style={{ filter: 'sepia(40%) saturate(80%)' }}
              />
            </div>
            <p
              className="text-xl font-semibold mb-2"
              style={{
                color: 'var(--text-primary)',
                fontFamily: 'Playfair Display, serif',
              }}
            >
              ¿En qué puedo ayudarte hoy?
            </p>
            <p className="text-sm max-w-xs mx-auto" style={{ color: 'var(--text-muted)' }}>
              Sube un documento en Biblioteca para comenzar a hacer consultas
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {titleHeader}
      <div className="flex-1 relative overflow-hidden">
        <div
          className="absolute inset-0 overflow-y-auto px-4 pt-4 pb-28 space-y-4"
          style={{ background: 'var(--bg-base)' }}
        >
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} className="h-2" />
        </div>
      </div>
    </div>
  );
}

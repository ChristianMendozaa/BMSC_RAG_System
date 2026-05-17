'use client';

import { useEffect, useRef } from 'react';
import Image from 'next/image';
import type { Message } from '@/types';
import MessageBubble from './MessageBubble';

interface Props {
  messages: Message[];
}

export default function ChatWindow({ messages }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div
        className="flex-1 flex items-center justify-center text-center px-6"
        style={{ background: 'var(--bg-base)' }}
      >
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
    );
  }

  return (
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
  );
}

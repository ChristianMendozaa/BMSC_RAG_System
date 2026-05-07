'use client';

import { useEffect, useRef } from 'react';
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
      <div className="flex-1 flex items-center justify-center text-center px-6">
        <div className="text-gray-400">
          <div className="text-4xl mb-3">💬</div>
          <p className="text-sm font-medium text-gray-500">Haz una pregunta sobre tus documentos</p>
          <p className="text-xs text-gray-400 mt-1">Los documentos deben estar en estado &quot;listo&quot; para consultarlos</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

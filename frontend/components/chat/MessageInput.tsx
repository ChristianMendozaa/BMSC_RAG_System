'use client';

import { KeyboardEvent, useRef } from 'react';
import { SendHorizonal } from 'lucide-react';

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (text: string) => void;
  isStreaming: boolean;
}

export default function MessageInput({ value, onChange, onSubmit, isStreaming }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !isStreaming) {
      e.preventDefault();
      const trimmed = value.trim();
      if (trimmed) {
        onSubmit(trimmed);
      }
    }
  };

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (trimmed && !isStreaming) {
      onSubmit(trimmed);
    }
  };

  return (
    <div className="flex items-end gap-2 bg-white border border-gray-200 rounded-2xl px-4 py-2 shadow-sm focus-within:border-blue-400 transition-colors">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isStreaming}
        placeholder="Escribe tu pregunta... (Enter para enviar, Shift+Enter para nueva línea)"
        rows={1}
        className="flex-1 resize-none bg-transparent text-sm text-gray-900 placeholder-gray-400 outline-none min-h-[36px] max-h-36 py-1.5 disabled:opacity-60"
        style={{ height: 'auto' }}
        onInput={(e) => {
          const target = e.target as HTMLTextAreaElement;
          target.style.height = 'auto';
          target.style.height = `${Math.min(target.scrollHeight, 144)}px`;
        }}
      />
      <button
        onClick={handleSubmit}
        disabled={!value.trim() || isStreaming}
        className="p-1.5 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
        aria-label="Enviar mensaje"
      >
        <SendHorizonal size={16} />
      </button>
    </div>
  );
}

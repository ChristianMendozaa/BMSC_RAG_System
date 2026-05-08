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
    <div
      className="flex items-end gap-2 rounded-2xl px-4 py-2 transition-colors"
      style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border-default)',
      }}
      onFocus={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--gold-bright)';
      }}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) {
          (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-default)';
        }
      }}
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isStreaming}
        placeholder="Escribe tu pregunta aquí..."
        rows={1}
        className="flex-1 resize-none bg-transparent text-sm outline-none min-h-[36px] max-h-36 py-1.5 disabled:opacity-60"
        style={{
          color: 'var(--text-primary)',
          caretColor: 'var(--gold-bright)',
          fontFamily: 'DM Sans, sans-serif',
        }}
        onInput={(e) => {
          const target = e.target as HTMLTextAreaElement;
          target.style.height = 'auto';
          target.style.height = `${Math.min(target.scrollHeight, 144)}px`;
        }}
      />
      <button
        onClick={handleSubmit}
        disabled={!value.trim() || isStreaming}
        className="p-2 rounded-xl transition-colors shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
        style={{
          background: 'var(--gold-bright)',
          color: '#0A1A10',
        }}
        onMouseEnter={(e) => {
          if (!e.currentTarget.disabled) {
            (e.currentTarget as HTMLButtonElement).style.background = 'var(--gold-muted)';
          }
        }}
        onMouseLeave={(e) => {
          if (!e.currentTarget.disabled) {
            (e.currentTarget as HTMLButtonElement).style.background = 'var(--gold-bright)';
          }
        }}
        aria-label="Enviar pregunta"
      >
        <SendHorizonal size={16} />
      </button>
    </div>
  );
}

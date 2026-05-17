'use client';

import { KeyboardEvent, useRef } from 'react';
import { SendHorizonal } from 'lucide-react';

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (text: string) => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export default function MessageInput({ value, onChange, onSubmit, isStreaming, disabled = false }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const isDisabled = isStreaming || disabled;

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !isDisabled) {
      e.preventDefault();
      const trimmed = value.trim();
      if (trimmed) {
        onSubmit(trimmed);
      }
    }
  };

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (trimmed && !isDisabled) {
      onSubmit(trimmed);
    }
  };

  return (
    <div className="flex items-end gap-2">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isDisabled}
        placeholder={disabled ? 'Selecciona una colección para comenzar...' : 'Escribe tu pregunta aquí...'}
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
        disabled={!value.trim() || isDisabled}
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

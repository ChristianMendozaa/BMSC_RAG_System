'use client';

import * as Tooltip from '@radix-ui/react-tooltip';
import { Loader2 } from 'lucide-react';
import type { DocumentStatus } from '@/types';

interface Props {
  status: DocumentStatus;
  errorMessage?: string | null;
}

const STATUS_CONFIG: Record<DocumentStatus, { label: string; bg: string; text: string; border: string }> = {
  pending: {
    label: 'En cola',
    bg: 'var(--bg-hover)',
    text: 'var(--text-muted)',
    border: 'var(--border-subtle)',
  },
  processing: {
    label: 'Procesando...',
    bg: '#1F1400',
    text: '#D4A843',
    border: '#6B5020',
  },
  indexing_images: {
    label: 'Analizando...',
    bg: '#0A1525',
    text: '#60A5FA',
    border: '#1E3A5F',
  },
  ready: {
    label: 'Disponible',
    bg: '#071A0F',
    text: '#4ADE80',
    border: '#1A5C32',
  },
  error: {
    label: 'Error',
    bg: 'var(--maroon-subtle)',
    text: '#F87171',
    border: 'var(--maroon)',
  },
};

export default function StatusBadge({ status, errorMessage }: Props) {
  const config = STATUS_CONFIG[status];

  const badge = (
    <span
      className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium"
      style={{
        background: config.bg,
        color: config.text,
        border: `1px solid ${config.border}`,
      }}
    >
      {(status === 'processing' || status === 'indexing_images') && (
        <Loader2 size={10} className="animate-spin" />
      )}
      {config.label}
    </span>
  );

  if (status === 'error' && errorMessage) {
    return (
      <Tooltip.Provider delayDuration={200}>
        <Tooltip.Root>
          <Tooltip.Trigger asChild>
            <span className="cursor-help">{badge}</span>
          </Tooltip.Trigger>
          <Tooltip.Portal>
            <Tooltip.Content
              side="top"
              className="text-xs px-3 py-1.5 rounded shadow-lg max-w-xs"
              style={{
                background: 'var(--bg-elevated)',
                border: '1px solid var(--maroon)',
                color: 'var(--text-primary)',
              }}
              sideOffset={4}
            >
              {errorMessage}
              <Tooltip.Arrow style={{ fill: 'var(--bg-elevated)' }} />
            </Tooltip.Content>
          </Tooltip.Portal>
        </Tooltip.Root>
      </Tooltip.Provider>
    );
  }

  return badge;
}

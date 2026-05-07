'use client';

import * as Tooltip from '@radix-ui/react-tooltip';
import { Loader2 } from 'lucide-react';
import type { DocumentStatus } from '@/types';

interface Props {
  status: DocumentStatus;
  errorMessage?: string | null;
}

const STATUS_CONFIG: Record<DocumentStatus, { label: string; className: string }> = {
  pending: { label: 'Pendiente', className: 'bg-gray-100 text-gray-600' },
  processing: { label: 'Procesando', className: 'bg-yellow-100 text-yellow-700' },
  indexing_images: { label: 'Indexando imágenes', className: 'bg-blue-100 text-blue-700' },
  ready: { label: 'Listo', className: 'bg-green-100 text-green-700' },
  error: { label: 'Error', className: 'bg-red-100 text-red-700' },
};

export default function StatusBadge({ status, errorMessage }: Props) {
  const config = STATUS_CONFIG[status];

  const badge = (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${config.className}`}
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
              className="bg-gray-900 text-white text-xs px-2 py-1.5 rounded shadow-lg max-w-xs"
              sideOffset={4}
            >
              {errorMessage}
              <Tooltip.Arrow className="fill-gray-900" />
            </Tooltip.Content>
          </Tooltip.Portal>
        </Tooltip.Root>
      </Tooltip.Provider>
    );
  }

  return badge;
}

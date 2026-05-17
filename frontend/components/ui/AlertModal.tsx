'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { CheckCircle, Info, X } from 'lucide-react';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  type?: 'info' | 'success';
  confirmLabel?: string;
}

export default function AlertModal({
  open,
  onOpenChange,
  title,
  description,
  type = 'info',
  confirmLabel = 'Entendido',
}: Props) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-sm rounded-2xl p-6 shadow-2xl"
          style={{
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-default)',
          }}
        >
          <div className="flex items-start gap-3 mb-4">
            <div
              className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center mt-0.5"
              style={{
                background:
                  type === 'success' ? 'rgba(30, 139, 71, 0.15)' : 'rgba(212, 168, 67, 0.1)',
              }}
            >
              {type === 'success' ? (
                <CheckCircle size={18} style={{ color: '#3dba6f' }} />
              ) : (
                <Info size={18} style={{ color: 'var(--gold-muted)' }} />
              )}
            </div>
            <div className="flex-1">
              <Dialog.Title
                className="text-sm font-semibold mb-1"
                style={{ color: 'var(--text-primary)', fontFamily: 'Playfair Display, serif' }}
              >
                {title}
              </Dialog.Title>
              <Dialog.Description
                className="text-xs leading-relaxed"
                style={{ color: 'var(--text-secondary)' }}
              >
                {description}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button className="shrink-0 p-1 rounded-md" style={{ color: 'var(--text-muted)' }}>
                <X size={14} />
              </button>
            </Dialog.Close>
          </div>

          <div className="flex justify-end">
            <Dialog.Close asChild>
              <button
                className="px-4 py-2 rounded-lg text-xs font-semibold"
                style={{ background: 'var(--gold-bright)', color: '#0A1A10' }}
              >
                {confirmLabel}
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

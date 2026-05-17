'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, X } from 'lucide-react';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
}

export default function ConfirmModal({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
  destructive = false,
  onConfirm,
}: Props) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
          style={{ animation: 'fadeIn 150ms ease' }}
        />
        <Dialog.Content
          className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-sm rounded-2xl p-6 shadow-2xl"
          style={{
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-default)',
          }}
        >
          <div className="flex items-start gap-3 mb-4">
            {destructive && (
              <div
                className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center mt-0.5"
                style={{ background: 'rgba(139, 30, 71, 0.15)' }}
              >
                <AlertTriangle size={18} style={{ color: 'var(--status-red)' }} />
              </div>
            )}
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
              <button
                className="shrink-0 p-1 rounded-md transition-colors"
                style={{ color: 'var(--text-muted)' }}
              >
                <X size={14} />
              </button>
            </Dialog.Close>
          </div>

          <div className="flex gap-2 justify-end">
            <Dialog.Close asChild>
              <button
                className="px-4 py-2 rounded-lg text-xs font-medium transition-colors"
                style={{
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-default)',
                  color: 'var(--text-secondary)',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-hover)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-surface)';
                }}
              >
                {cancelLabel}
              </button>
            </Dialog.Close>
            <button
              onClick={() => {
                onConfirm();
                onOpenChange(false);
              }}
              className="px-4 py-2 rounded-lg text-xs font-semibold transition-colors"
              style={
                destructive
                  ? { background: 'var(--maroon)', color: '#fff' }
                  : { background: 'var(--gold-bright)', color: '#0A1A10' }
              }
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.opacity = '0.85';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.opacity = '1';
              }}
            >
              {confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

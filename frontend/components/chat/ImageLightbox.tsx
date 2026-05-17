'use client';

import { useState, useCallback } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, ZoomIn, ZoomOut, Download, FileText } from 'lucide-react';
import { getImageUrl, getDocumentDownloadUrl } from '@/lib/api';
import type { Source } from '@/types';

interface Props {
  source: Source | null;
  onClose: () => void;
}

export default function ImageLightbox({ source, onClose }: Props) {
  const [zoom, setZoom] = useState(1);

  const handleClose = useCallback(() => {
    setZoom(1);
    onClose();
  }, [onClose]);

  const zoomIn = useCallback(() => setZoom((z) => Math.min(z + 0.5, 4)), []);
  const zoomOut = useCallback(() => setZoom((z) => Math.max(z - 0.5, 0.5)), []);

  if (!source?.image_id) return null;

  const imageUrl = getImageUrl(source.image_id);
  const label = `${source.filename}${source.page ? ` · p.${source.page}` : ''}`;
  const docViewUrl = source.page
    ? `${getDocumentDownloadUrl(source.doc_id)}#page=${source.page}`
    : getDocumentDownloadUrl(source.doc_id);

  return (
    <Dialog.Root open={!!source} onOpenChange={(open) => { if (!open) handleClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-50"
          style={{ background: 'rgba(0,0,0,0.88)', backdropFilter: 'blur(4px)' }}
          onClick={handleClose}
        />
        <Dialog.Content
          className="fixed inset-0 z-50 flex flex-col items-center justify-center outline-none"
          aria-describedby={undefined}
        >
          <Dialog.Title className="sr-only">{label}</Dialog.Title>
          {/* Top bar */}
          <div
            className="absolute top-0 left-0 right-0 flex items-center justify-between px-4 py-3 z-10"
            style={{ background: 'linear-gradient(to bottom, rgba(5,15,9,0.95), transparent)' }}
          >
            <div className="flex items-center gap-2">
              <span
                className="text-xs px-2.5 py-1 rounded-lg flex items-center gap-1.5"
                style={{
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-gold)',
                  color: 'var(--text-secondary)',
                }}
              >
                <FileText size={11} style={{ color: 'var(--gold-muted)' }} />
                {label}
              </span>
              {source.page && (
                <a
                  href={docViewUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs px-2.5 py-1 rounded-lg transition-colors"
                  style={{
                    background: 'var(--gold-subtle)',
                    border: '1px solid var(--border-gold)',
                    color: 'var(--gold-bright)',
                  }}
                >
                  Abrir en documento →
                </a>
              )}
            </div>

            <div className="flex items-center gap-1.5">
              <button
                onClick={zoomOut}
                disabled={zoom <= 0.5}
                className="p-2 rounded-lg transition-all disabled:opacity-30"
                style={{
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-default)',
                  color: 'var(--text-secondary)',
                }}
                title="Reducir zoom"
              >
                <ZoomOut size={15} />
              </button>
              <span
                className="text-xs w-12 text-center font-mono tabular-nums"
                style={{ color: 'var(--text-muted)' }}
              >
                {Math.round(zoom * 100)}%
              </span>
              <button
                onClick={zoomIn}
                disabled={zoom >= 4}
                className="p-2 rounded-lg transition-all disabled:opacity-30"
                style={{
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-default)',
                  color: 'var(--text-secondary)',
                }}
                title="Aumentar zoom"
              >
                <ZoomIn size={15} />
              </button>
              <a
                href={imageUrl}
                download={`imagen-p${source.page ?? source.image_id}.png`}
                className="p-2 rounded-lg transition-all"
                style={{
                  background: 'var(--gold-subtle)',
                  border: '1px solid var(--border-gold)',
                  color: 'var(--gold-bright)',
                }}
                title="Descargar imagen"
              >
                <Download size={15} />
              </a>
              <Dialog.Close asChild>
                <button
                  className="p-2 rounded-lg transition-all"
                  style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-muted)',
                  }}
                  title="Cerrar"
                >
                  <X size={15} />
                </button>
              </Dialog.Close>
            </div>
          </div>

          {/* Image scroll area — click backdrop to close, click image to stop propagation */}
          <div
            className="w-full h-full flex items-center justify-center p-16 overflow-auto"
            onClick={handleClose}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                flexShrink: 0,
                cursor: zoom < 4 ? 'zoom-in' : 'default',
              }}
              onDoubleClick={zoom < 4 ? zoomIn : zoomOut}
            >
              <img
                src={imageUrl}
                alt={label}
                draggable={false}
                style={{
                  width: `${zoom * 100}%`,
                  maxWidth: zoom === 1 ? 'min(85vw, 900px)' : 'none',
                  height: 'auto',
                  display: 'block',
                  borderRadius: '8px',
                  border: '1px solid var(--border-gold)',
                  boxShadow: '0 8px 40px rgba(0,0,0,0.6)',
                  transition: 'width 0.2s ease',
                  userSelect: 'none',
                }}
              />
            </div>
          </div>

          {/* Bottom hint */}
          <div
            className="absolute bottom-4 left-1/2 -translate-x-1/2 text-xs pointer-events-none"
            style={{ color: 'var(--text-muted)' }}
          >
            Doble clic para ampliar · Clic fuera para cerrar
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

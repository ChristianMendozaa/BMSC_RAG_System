'use client';

import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Trash2, X, Eye, FileText } from 'lucide-react';
import { deleteDocument, getDocument, getImageUrl } from '@/lib/api';
import type { DocumentDetail, DocumentSummary } from '@/types';
import StatusBadge from './StatusBadge';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface Props {
  documents: DocumentSummary[];
  onRefresh: () => void;
}

export default function DocumentTable({ documents, onRefresh }: Props) {
  const [deleteTarget, setDeleteTarget] = useState<DocumentSummary | null>(null);
  const [detailDoc, setDetailDoc] = useState<DocumentDetail | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await deleteDocument(deleteTarget.id);
      setDeleteTarget(null);
      onRefresh();
    } catch (err) {
      console.error('Delete failed:', err);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleViewDetail = async (doc: DocumentSummary) => {
    if (doc.status !== 'ready' && doc.status !== 'indexing_images') return;
    setIsLoadingDetail(true);
    try {
      const detail = await getDocument(doc.id);
      setDetailDoc(detail);
    } catch (err) {
      console.error('Failed to load document detail:', err);
    } finally {
      setIsLoadingDetail(false);
    }
  };

  if (documents.length === 0) {
    return (
      <div
        className="text-center py-14 rounded-xl"
        style={{
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <FileText
          size={32}
          className="mx-auto mb-3 opacity-20"
          style={{ color: 'var(--text-muted)' }}
        />
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
          Todavía no hay documentos. Sube uno arriba para comenzar.
        </p>
      </div>
    );
  }

  return (
    <>
      <div
        className="overflow-x-auto rounded-xl"
        style={{
          border: '1px solid var(--border-default)',
          background: 'var(--bg-elevated)',
        }}
      >
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-surface)' }}>
              <th
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider"
                style={{ color: 'var(--gold-muted)' }}
              >
                Nombre
              </th>
              <th
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider hidden sm:table-cell"
                style={{ color: 'var(--gold-muted)' }}
              >
                Tipo
              </th>
              <th
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider hidden sm:table-cell"
                style={{ color: 'var(--gold-muted)' }}
              >
                Tamaño
              </th>
              <th
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider"
                style={{ color: 'var(--gold-muted)' }}
              >
                Estado
              </th>
              <th
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider hidden md:table-cell"
                style={{ color: 'var(--gold-muted)' }}
              >
                Secciones / Imágenes
              </th>
              <th
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider hidden lg:table-cell"
                style={{ color: 'var(--gold-muted)' }}
              >
                Fecha
              </th>
              <th
                className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider"
                style={{ color: 'var(--gold-muted)' }}
              >
                Acciones
              </th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr
                key={doc.id}
                className="transition-colors"
                style={{ borderBottom: '1px solid var(--border-subtle)' }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLTableRowElement).style.background = 'var(--bg-hover)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLTableRowElement).style.background = 'transparent';
                }}
              >
                <td className="px-4 py-3 max-w-xs">
                  <span
                    className={`truncate block font-medium text-sm ${
                      doc.status === 'ready' || doc.status === 'indexing_images'
                        ? 'cursor-pointer'
                        : ''
                    }`}
                    style={{ color: 'var(--text-primary)' }}
                    onClick={() => handleViewDetail(doc)}
                    title={doc.original_filename}
                    onMouseEnter={(e) => {
                      if (doc.status === 'ready' || doc.status === 'indexing_images') {
                        (e.currentTarget as HTMLElement).style.color = 'var(--gold-bright)';
                      }
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.color = 'var(--text-primary)';
                    }}
                  >
                    {doc.original_filename}
                  </span>
                </td>
                <td className="px-4 py-3 hidden sm:table-cell">
                  <span
                    className="uppercase text-xs font-mono"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {doc.file_type}
                  </span>
                </td>
                <td className="px-4 py-3 hidden sm:table-cell" style={{ color: 'var(--text-secondary)' }}>
                  {formatBytes(doc.file_size)}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={doc.status} errorMessage={doc.error_message} />
                </td>
                <td className="px-4 py-3 hidden md:table-cell" style={{ color: 'var(--text-muted)' }}>
                  {doc.chunk_count} / {doc.image_count}
                </td>
                <td className="px-4 py-3 hidden lg:table-cell text-xs" style={{ color: 'var(--text-muted)' }}>
                  {formatDate(doc.created_at)}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1">
                    {(doc.status === 'ready' || doc.status === 'indexing_images') && (
                      <button
                        onClick={() => handleViewDetail(doc)}
                        disabled={isLoadingDetail}
                        className="p-1.5 rounded-md transition-colors disabled:opacity-50"
                        style={{ color: 'var(--text-muted)' }}
                        title="Ver detalles"
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLButtonElement).style.color = 'var(--gold-bright)';
                          (e.currentTarget as HTMLButtonElement).style.background = 'var(--gold-subtle)';
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
                          (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                        }}
                      >
                        <Eye size={15} />
                      </button>
                    )}
                    <button
                      onClick={() => setDeleteTarget(doc)}
                      className="p-1.5 rounded-md transition-colors"
                      style={{ color: 'var(--text-muted)' }}
                      title="Eliminar"
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLButtonElement).style.color = '#F87171';
                        (e.currentTarget as HTMLButtonElement).style.background = 'var(--maroon-subtle)';
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
                        (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                      }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Delete confirmation dialog */}
      <Dialog.Root open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/70 z-40" />
          <Dialog.Content
            className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-xl shadow-xl p-6 w-full max-w-sm"
            style={{
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-default)',
            }}
          >
            <Dialog.Title
              className="text-base font-semibold mb-2"
              style={{ color: 'var(--text-primary)', fontFamily: 'Playfair Display, serif' }}
            >
              Quitar documento
            </Dialog.Title>
            <Dialog.Description className="text-sm mb-5" style={{ color: 'var(--text-secondary)' }}>
              ¿Deseas eliminar{' '}
              <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                &quot;{deleteTarget?.original_filename}&quot;
              </span>
              ? Se eliminará el documento y toda su información asociada.
            </Dialog.Description>
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild>
                <button
                  className="px-4 py-1.5 text-sm rounded-lg transition-colors"
                  style={{
                    border: '1px solid var(--border-default)',
                    color: 'var(--text-secondary)',
                    background: 'transparent',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-hover)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                  }}
                >
                  Cancelar
                </button>
              </Dialog.Close>
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="px-4 py-1.5 text-sm rounded-lg transition-colors disabled:opacity-50"
                style={{
                  background: 'var(--maroon)',
                  color: 'var(--text-primary)',
                }}
                onMouseEnter={(e) => {
                  if (!e.currentTarget.disabled) {
                    (e.currentTarget as HTMLButtonElement).style.background = '#6B1536';
                  }
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'var(--maroon)';
                }}
              >
                {isDeleting ? 'Eliminando...' : 'Eliminar'}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Document detail dialog */}
      <Dialog.Root open={!!detailDoc} onOpenChange={(open) => !open && setDetailDoc(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/70 z-40" />
          <Dialog.Content
            className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-xl shadow-xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto"
            style={{
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-default)',
            }}
          >
            <div className="flex justify-between items-start mb-4">
              <Dialog.Title
                className="text-base font-semibold pr-4"
                style={{ color: 'var(--text-primary)', fontFamily: 'Playfair Display, serif' }}
              >
                {detailDoc?.original_filename}
              </Dialog.Title>
              <Dialog.Close asChild>
                <button
                  className="p-1 rounded-md transition-colors"
                  style={{ color: 'var(--text-muted)' }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)';
                  }}
                >
                  <X size={16} />
                </button>
              </Dialog.Close>
            </div>

            {detailDoc && (
              <div className="space-y-4">
                <div className="flex gap-4 text-sm" style={{ color: 'var(--text-secondary)' }}>
                  <span>{detailDoc.chunk_count} secciones indexadas</span>
                  <span style={{ color: 'var(--border-default)' }}>·</span>
                  <span>{detailDoc.image_count} imágenes encontradas</span>
                </div>

                {detailDoc.images.length > 0 && (
                  <div>
                    <h3
                      className="text-sm font-semibold mb-2"
                      style={{ color: 'var(--gold-muted)', fontFamily: 'Playfair Display, serif' }}
                    >
                      Imágenes encontradas
                    </h3>
                    <div className="grid grid-cols-4 gap-2">
                      {detailDoc.images.map((img) => (
                        <div key={img.id} className="relative">
                          {/* pb-[100%] = cuadrado sin aspect-ratio (no soportado en Edge 86) */}
                          <div
                            className="relative w-full pb-[100%] rounded-lg overflow-hidden"
                            style={{ border: '1px solid var(--border-subtle)' }}
                          >
                            <img
                              src={getImageUrl(img.id)}
                              alt={img.description ?? `Imagen ${img.image_index}`}
                              className="absolute inset-0 w-full h-full object-cover"
                            />
                          </div>
                          {img.page_number && (
                            <span
                              className="absolute bottom-1 right-1 text-xs px-1 rounded"
                              style={{ background: 'rgba(0,0,0,0.7)', color: 'var(--text-primary)' }}
                            >
                              p.{img.page_number}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {detailDoc.chunks.length > 0 && (
                  <div>
                    <h3
                      className="text-sm font-semibold mb-2"
                      style={{ color: 'var(--gold-muted)', fontFamily: 'Playfair Display, serif' }}
                    >
                      Contenido indexado ({detailDoc.chunks.length} secciones)
                    </h3>
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {detailDoc.chunks.slice(0, 20).map((chunk) => (
                        <div
                          key={chunk.id}
                          className="text-xs rounded-lg p-2.5"
                          style={{
                            background: 'var(--bg-base)',
                            border: '1px solid var(--border-subtle)',
                          }}
                        >
                          <div className="flex gap-2 mb-1">
                            <span style={{ color: 'var(--text-muted)' }}>#{chunk.chunk_index}</span>
                            {chunk.page_number && (
                              <span style={{ color: 'var(--text-muted)' }}>p.{chunk.page_number}</span>
                            )}
                            <span
                              className="px-1 rounded text-xs"
                              style={{
                                background: chunk.chunk_type === 'image_description'
                                  ? '#2A0A2A'
                                  : 'var(--gold-subtle)',
                                color: chunk.chunk_type === 'image_description'
                                  ? '#D8A0D8'
                                  : 'var(--gold-muted)',
                              }}
                            >
                              {chunk.chunk_type === 'image_description' ? 'imagen' : 'texto'}
                            </span>
                          </div>
                          <p className="line-clamp-3" style={{ color: 'var(--text-secondary)' }}>
                            {chunk.content}
                          </p>
                        </div>
                      ))}
                      {detailDoc.chunks.length > 20 && (
                        <p className="text-xs text-center py-1" style={{ color: 'var(--text-muted)' }}>
                          ... y {detailDoc.chunks.length - 20} secciones más
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}

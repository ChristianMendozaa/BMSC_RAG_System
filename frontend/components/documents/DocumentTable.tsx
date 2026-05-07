'use client';

import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Trash2, X, Eye } from 'lucide-react';
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
      <div className="text-center py-12 text-gray-400">
        <p className="text-sm">No hay documentos todavía. Sube uno arriba.</p>
      </div>
    );
  }

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50">
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Nombre
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Tipo
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Tamaño
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Estado
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Chunks / Imgs
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Fecha
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Acciones
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {documents.map((doc) => (
              <tr key={doc.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 max-w-xs">
                  <span
                    className={`truncate block font-medium text-gray-900 ${
                      doc.status === 'ready' || doc.status === 'indexing_images' ? 'cursor-pointer hover:text-blue-600' : ''
                    }`}
                    onClick={() => handleViewDetail(doc)}
                    title={doc.original_filename}
                  >
                    {doc.original_filename}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className="uppercase text-xs text-gray-500 font-mono">
                    {doc.file_type}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500">{formatBytes(doc.file_size)}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={doc.status} errorMessage={doc.error_message} />
                </td>
                <td className="px-4 py-3 text-gray-500">
                  {doc.chunk_count} / {doc.image_count}
                </td>
                <td className="px-4 py-3 text-gray-400 text-xs">
                  {formatDate(doc.created_at)}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1">
                    {(doc.status === 'ready' || doc.status === 'indexing_images') && (
                      <button
                        onClick={() => handleViewDetail(doc)}
                        disabled={isLoadingDetail}
                        className="p-1.5 rounded-md text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors disabled:opacity-50"
                        title="Ver detalles"
                      >
                        <Eye size={15} />
                      </button>
                    )}
                    <button
                      onClick={() => setDeleteTarget(doc)}
                      className="p-1.5 rounded-md text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                      title="Eliminar"
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
          <Dialog.Overlay className="fixed inset-0 bg-black/40 z-40" />
          <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white rounded-xl shadow-xl p-6 w-full max-w-sm">
            <Dialog.Title className="text-base font-semibold text-gray-900 mb-2">
              Eliminar documento
            </Dialog.Title>
            <Dialog.Description className="text-sm text-gray-600 mb-4">
              ¿Eliminar{' '}
              <span className="font-medium">&quot;{deleteTarget?.original_filename}&quot;</span>?
              Esta acción borrará también todos los vectores e imágenes asociadas.
            </Dialog.Description>
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild>
                <button className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors">
                  Cancelar
                </button>
              </Dialog.Close>
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="px-3 py-1.5 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
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
          <Dialog.Overlay className="fixed inset-0 bg-black/40 z-40" />
          <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-white rounded-xl shadow-xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-start mb-4">
              <Dialog.Title className="text-base font-semibold text-gray-900 pr-4">
                {detailDoc?.original_filename}
              </Dialog.Title>
              <Dialog.Close asChild>
                <button className="p-1 rounded-md text-gray-400 hover:text-gray-600 transition-colors">
                  <X size={16} />
                </button>
              </Dialog.Close>
            </div>

            {detailDoc && (
              <div className="space-y-4">
                <div className="flex gap-4 text-sm text-gray-600">
                  <span>{detailDoc.chunk_count} chunks indexados</span>
                  <span>·</span>
                  <span>{detailDoc.image_count} imágenes extraídas</span>
                </div>

                {detailDoc.images.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">Imágenes extraídas</h3>
                    <div className="grid grid-cols-4 gap-2">
                      {detailDoc.images.map((img) => (
                        <div key={img.id} className="relative">
                          <img
                            src={getImageUrl(img.id)}
                            alt={img.description ?? `Imagen ${img.image_index}`}
                            className="w-full aspect-square object-cover rounded-lg border border-gray-200"
                          />
                          {img.page_number && (
                            <span className="absolute bottom-1 right-1 bg-black/60 text-white text-xs px-1 rounded">
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
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">
                      Chunks ({detailDoc.chunks.length})
                    </h3>
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {detailDoc.chunks.slice(0, 20).map((chunk) => (
                        <div
                          key={chunk.id}
                          className="text-xs bg-gray-50 border border-gray-100 rounded-lg p-2.5"
                        >
                          <div className="flex gap-2 mb-1">
                            <span className="text-gray-400">#{chunk.chunk_index}</span>
                            {chunk.page_number && (
                              <span className="text-gray-400">p.{chunk.page_number}</span>
                            )}
                            <span
                              className={`px-1 rounded text-xs ${
                                chunk.chunk_type === 'image_description'
                                  ? 'bg-purple-100 text-purple-600'
                                  : 'bg-blue-100 text-blue-600'
                              }`}
                            >
                              {chunk.chunk_type}
                            </span>
                          </div>
                          <p className="text-gray-700 line-clamp-3">{chunk.content}</p>
                        </div>
                      ))}
                      {detailDoc.chunks.length > 20 && (
                        <p className="text-xs text-gray-400 text-center py-1">
                          ... y {detailDoc.chunks.length - 20} más
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

'use client';

import useSWR from 'swr';
import { getDocuments } from '@/lib/api';
import type { DocumentsListResponse } from '@/types';
import DocumentTable from '@/components/documents/DocumentTable';
import UploadZone from '@/components/documents/UploadZone';

const fetcher = () => getDocuments(0, 100);

export default function DocumentsPage() {
  const { data, mutate, isLoading } = useSWR<DocumentsListResponse>(
    '/api/documents',
    fetcher,
    {
      refreshInterval: 2000,
      revalidateOnFocus: true,
    },
  );

  const documents = data?.items ?? [];

  return (
    <div className="max-w-6xl mx-auto w-full px-4 md:px-6 py-6 space-y-6">
      <div>
        <h1
          className="text-2xl font-semibold"
          style={{
            color: 'var(--gold-bright)',
            fontFamily: 'Playfair Display, serif',
          }}
        >
          Biblioteca de Documentos
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
          Aquí puedes subir y revisar los documentos disponibles para consultar
        </p>
      </div>

      <UploadZone onUploadComplete={() => mutate()} />

      {isLoading ? (
        <div
          className="text-center py-8 text-sm"
          style={{ color: 'var(--text-muted)' }}
        >
          Cargando documentos...
        </div>
      ) : (
        <DocumentTable documents={documents} onRefresh={() => mutate()} />
      )}
    </div>
  );
}

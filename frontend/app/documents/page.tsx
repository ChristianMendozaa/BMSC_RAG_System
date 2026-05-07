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
    <div className="max-w-6xl mx-auto w-full px-6 py-6 space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">Documentos</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Sube y gestiona la documentación interna del banco
        </p>
      </div>

      <UploadZone onUploadComplete={() => mutate()} />

      {isLoading ? (
        <div className="text-center py-8 text-sm text-gray-400">Cargando documentos...</div>
      ) : (
        <DocumentTable documents={documents} onRefresh={() => mutate()} />
      )}
    </div>
  );
}

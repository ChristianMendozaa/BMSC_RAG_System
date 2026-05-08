'use client';

import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { uploadDocument } from '@/lib/api';

const ACCEPTED_TYPES: Record<string, string[]> = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'text/plain': ['.txt'],
  'text/markdown': ['.md'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'image/webp': ['.webp'],
};

interface UploadState {
  status: 'idle' | 'uploading' | 'success' | 'error';
  message: string;
}

interface Props {
  onUploadComplete: () => void;
}

export default function UploadZone({ onUploadComplete }: Props) {
  const [uploadState, setUploadState] = useState<UploadState>({
    status: 'idle',
    message: '',
  });

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) return;
      const file = acceptedFiles[0];

      setUploadState({ status: 'uploading', message: `Cargando ${file.name}...` });

      try {
        const result = await uploadDocument(file);
        setUploadState({
          status: 'success',
          message: `"${result.filename}" recibido y en proceso`,
        });
        onUploadComplete();
        setTimeout(() => setUploadState({ status: 'idle', message: '' }), 3000);
      } catch (err) {
        setUploadState({
          status: 'error',
          message: err instanceof Error ? err.message : 'No se pudo subir el archivo. Intenta de nuevo.',
        });
      }
    },
    [onUploadComplete],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    multiple: false,
    disabled: uploadState.status === 'uploading',
  });

  const isUploading = uploadState.status === 'uploading';

  return (
    <div className="space-y-3">
      <div
        {...getRootProps()}
        className="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200"
        style={{
          background: isDragActive ? 'var(--gold-subtle)' : 'var(--bg-elevated)',
          borderColor: isDragActive
            ? 'var(--gold-bright)'
            : isUploading
            ? 'var(--border-subtle)'
            : 'var(--border-gold)',
          cursor: isUploading ? 'not-allowed' : 'pointer',
        }}
        onMouseEnter={(e) => {
          if (!isUploading && !isDragActive) {
            (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--gold-bright)';
            (e.currentTarget as HTMLDivElement).style.background = 'var(--gold-subtle)';
          }
        }}
        onMouseLeave={(e) => {
          if (!isDragActive) {
            (e.currentTarget as HTMLDivElement).style.borderColor = isUploading ? 'var(--border-subtle)' : 'var(--border-gold)';
            (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-elevated)';
          }
        }}
      >
        <input {...getInputProps()} />

        {isUploading ? (
          <Loader2
            size={32}
            className="mx-auto mb-3 animate-spin"
            style={{ color: 'var(--gold-bright)' }}
          />
        ) : (
          <Upload
            size={32}
            className="mx-auto mb-3"
            style={{ color: isDragActive ? 'var(--gold-bright)' : 'var(--gold-muted)' }}
          />
        )}

        {isDragActive ? (
          <p className="text-sm font-medium" style={{ color: 'var(--gold-bright)' }}>
            Suelta el archivo aquí
          </p>
        ) : isUploading ? (
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {uploadState.message}
          </p>
        ) : (
          <>
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              Arrastra tu documento aquí, o haz clic para buscarlo
            </p>
            <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
              PDF, Word, Excel, PowerPoint, imágenes y más
            </p>
          </>
        )}
      </div>

      {uploadState.status !== 'idle' && uploadState.status !== 'uploading' && (
        <div
          className="flex items-center gap-2 text-sm px-4 py-2.5 rounded-lg"
          style={{
            background: uploadState.status === 'success' ? '#0A1F12' : 'var(--maroon-subtle)',
            border: `1px solid ${uploadState.status === 'success' ? 'var(--status-green)' : 'var(--maroon)'}`,
            color: uploadState.status === 'success' ? '#4ADE80' : '#F87171',
          }}
        >
          {uploadState.status === 'success' && <CheckCircle size={14} />}
          {uploadState.status === 'error' && <AlertCircle size={14} />}
          <span>{uploadState.message}</span>
        </div>
      )}
    </div>
  );
}

'use client';

import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, CheckCircle, AlertCircle } from 'lucide-react';
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

      setUploadState({ status: 'uploading', message: `Subiendo ${file.name}...` });

      try {
        const result = await uploadDocument(file);
        setUploadState({
          status: 'success',
          message: `"${result.filename}" en cola para procesamiento`,
        });
        onUploadComplete();
        setTimeout(() => setUploadState({ status: 'idle', message: '' }), 3000);
      } catch (err) {
        setUploadState({
          status: 'error',
          message: err instanceof Error ? err.message : 'Error al subir el archivo',
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

  return (
    <div className="space-y-2">
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          isDragActive
            ? 'border-blue-400 bg-blue-50'
            : uploadState.status === 'uploading'
            ? 'border-gray-200 bg-gray-50 cursor-not-allowed'
            : 'border-gray-300 hover:border-blue-400 hover:bg-blue-50'
        }`}
      >
        <input {...getInputProps()} />
        <Upload
          size={32}
          className={`mx-auto mb-3 ${isDragActive ? 'text-blue-500' : 'text-gray-400'}`}
        />
        {isDragActive ? (
          <p className="text-sm text-blue-600 font-medium">Suelta el archivo aquí</p>
        ) : (
          <>
            <p className="text-sm text-gray-600 font-medium">
              Arrastra un archivo o haz click para seleccionar
            </p>
            <p className="text-xs text-gray-400 mt-1">
              PDF, DOCX, PPTX, XLSX, TXT, MD, JPG, PNG, WEBP
            </p>
          </>
        )}
      </div>

      {uploadState.status !== 'idle' && (
        <div
          className={`flex items-center gap-2 text-sm px-3 py-2 rounded-lg ${
            uploadState.status === 'uploading'
              ? 'bg-blue-50 text-blue-700'
              : uploadState.status === 'success'
              ? 'bg-green-50 text-green-700'
              : 'bg-red-50 text-red-700'
          }`}
        >
          {uploadState.status === 'success' && <CheckCircle size={14} />}
          {uploadState.status === 'error' && <AlertCircle size={14} />}
          <span>{uploadState.message}</span>
        </div>
      )}
    </div>
  );
}

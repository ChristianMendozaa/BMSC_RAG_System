'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, FileText, ExternalLink, Download, Loader2 } from 'lucide-react';
import { getDocumentDownloadUrl, API_URL } from '@/lib/api';
import type { Source } from '@/types';

interface Props {
  textSources: Source[];
}

interface DocGroup {
  doc_id: string;
  filename: string;
}

export default function SourcesPanel({ textSources }: Props) {
  const [expanded, setExpanded] = useState(true);
  const [isDownloadingAll, setIsDownloadingAll] = useState(false);

  if (textSources.length === 0) return null;

  const groupMap = textSources.reduce<Record<string, DocGroup>>((acc, s) => {
    if (!acc[s.doc_id]) {
      acc[s.doc_id] = { doc_id: s.doc_id, filename: s.filename };
    }
    return acc;
  }, {});

  const docGroups = Object.values(groupMap);

  async function handleDownloadAll() {
    if (isDownloadingAll) return;
    setIsDownloadingAll(true);
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    try {
      for (let i = 0; i < docGroups.length; i++) {
        const group = docGroups[i];
        const res = await fetch(
          `${API_URL}/api/documents/${group.doc_id}/download?dl=1`,
          { headers: token ? { Authorization: `Bearer ${token}` } : {} },
        );
        if (!res.ok) {
          console.warn(`Error descargando ${group.filename}: ${res.status}`);
          continue;
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = group.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        if (i < docGroups.length - 1) {
          await new Promise((r) => setTimeout(r, 400));
        }
      }
    } finally {
      setIsDownloadingAll(false);
    }
  }

  return (
    <div
      className="mt-3 rounded-xl overflow-hidden text-xs"
      style={{ border: '1px solid var(--border-subtle)' }}
    >
      {/* Header */}
      <div
        className="flex items-center"
        style={{ background: 'var(--bg-surface)' }}
      >
        {/* Toggle */}
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex-1 flex items-center justify-between px-3 py-2 transition-colors"
          style={{ color: 'var(--text-muted)' }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-hover)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
          }}
        >
          <span
            className="flex items-center gap-1.5 font-semibold uppercase tracking-wide"
            style={{ color: 'var(--gold-muted)' }}
          >
            <FileText size={11} />
            Fuentes · {docGroups.length} {docGroups.length === 1 ? 'documento' : 'documentos'}
          </span>
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>

        {/* Separator */}
        <div style={{ width: '1px', alignSelf: 'stretch', background: 'var(--border-subtle)' }} />

        {/* Download all */}
        <button
          onClick={handleDownloadAll}
          disabled={isDownloadingAll}
          className="flex items-center gap-1 px-3 py-2 transition-colors shrink-0 disabled:opacity-50"
          style={{ color: 'var(--gold-muted)', fontSize: '11px' }}
          onMouseEnter={(e) => {
            if (!isDownloadingAll) {
              (e.currentTarget as HTMLButtonElement).style.color = 'var(--gold-bright)';
              (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-hover)';
            }
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--gold-muted)';
            (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
          }}
          title="Descargar todos los documentos citados"
        >
          {isDownloadingAll ? (
            <>
              <Loader2 size={10} className="animate-spin" />
              Descargando...
            </>
          ) : (
            <>
              <Download size={10} />
              Descargar todo
            </>
          )}
        </button>
      </div>

      {/* Doc rows */}
      {expanded && (
        <div style={{ borderTop: '1px solid var(--border-subtle)' }}>
          {docGroups.map((group) => {
            const viewUrl = getDocumentDownloadUrl(group.doc_id);
            const dlUrl = getDocumentDownloadUrl(group.doc_id, true);
            return (
              <div
                key={group.doc_id}
                className="flex items-center justify-between gap-3 px-3 py-2.5"
                style={{
                  background: 'var(--bg-elevated)',
                  borderTop: '1px solid var(--border-subtle)',
                }}
              >
                {/* Left: icon + filename */}
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <FileText
                    size={13}
                    className="shrink-0"
                    style={{ color: 'var(--gold-muted)' }}
                  />
                  <p
                    className="truncate font-medium"
                    style={{ color: 'var(--text-secondary)' }}
                    title={group.filename}
                  >
                    {group.filename}
                  </p>
                </div>

                {/* Right: Ver + Descargar */}
                <div className="flex items-center gap-1.5 shrink-0">
                  <a
                    href={viewUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 px-2 py-1 rounded-lg transition-colors"
                    style={{
                      border: '1px solid var(--border-default)',
                      color: 'var(--text-secondary)',
                      fontSize: '10px',
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--gold-bright)';
                      (e.currentTarget as HTMLAnchorElement).style.color = 'var(--gold-bright)';
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--border-default)';
                      (e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-secondary)';
                    }}
                    title="Ver documento"
                  >
                    <ExternalLink size={10} />
                    Ver
                  </a>
                  <a
                    href={dlUrl}
                    download
                    className="flex items-center gap-1 px-2 py-1 rounded-lg transition-colors"
                    style={{
                      background: 'var(--gold-subtle)',
                      border: '1px solid var(--border-gold)',
                      color: 'var(--gold-muted)',
                      fontSize: '10px',
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLAnchorElement).style.color = 'var(--gold-bright)';
                      (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--gold-bright)';
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLAnchorElement).style.color = 'var(--gold-muted)';
                      (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--border-gold)';
                    }}
                    title="Descargar documento"
                  >
                    <Download size={10} />
                    Descargar
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

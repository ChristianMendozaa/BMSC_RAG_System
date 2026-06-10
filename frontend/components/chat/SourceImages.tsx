'use client';

import { getImageUrl } from '@/lib/api';
import type { Source } from '@/types';

interface Props {
  sources: Source[];
}

export default function SourceImages({ sources }: Props) {
  const imageSources = sources.filter((s) => s.type === 'image' && s.image_id);
  if (imageSources.length === 0) return null;

  return (
    <div className="mt-4">
      <p
        className="text-xs font-medium mb-2 uppercase tracking-wide"
        style={{ color: 'var(--text-muted)' }}
      >
        Imágenes de referencia
      </p>
      <div
        className="grid gap-3"
        style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}
      >
        {imageSources.map((source) => {
          const label = `${source.filename}${source.page ? ` · p.${source.page}` : ''}`;
          return (
            <a
              key={source.image_id}
              href={getImageUrl(source.image_id!)}
              target="_blank"
              rel="noopener noreferrer"
              className="flex flex-col gap-1.5 group"
            >
              {/* paddingTop 75% = ratio 4/3 sin aspect-ratio (no soportado en Edge 86) */}
              <div
                className="relative w-full rounded-lg overflow-hidden transition-all"
                style={{
                  border: '1px solid var(--border-default)',
                  background: 'var(--bg-surface)',
                  paddingTop: '75%',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--gold-bright)';
                  (e.currentTarget as HTMLDivElement).style.boxShadow =
                    '0 0 0 2px var(--gold-subtle)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-default)';
                  (e.currentTarget as HTMLDivElement).style.boxShadow = 'none';
                }}
              >
                <img
                  src={getImageUrl(source.image_id!)}
                  alt={label}
                  className="absolute inset-0 w-full h-full object-contain"
                  style={{ background: 'var(--bg-elevated)' }}
                />
              </div>
              <p
                className="text-xs truncate transition-colors"
                style={{ color: 'var(--text-muted)' }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.color = 'var(--gold-bright)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.color = 'var(--text-muted)';
                }}
              >
                {label}
              </p>
            </a>
          );
        })}
      </div>
    </div>
  );
}

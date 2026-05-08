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
    <div className="mt-3 flex flex-wrap gap-3">
      {imageSources.map((source) => {
        const label = `${source.filename}${source.page ? ` · p.${source.page}` : ''}`;
        return (
          <a
            key={source.image_id}
            href={getImageUrl(source.image_id!)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col gap-1 shrink-0 group"
          >
            <div
              className="w-44 h-44 rounded-lg overflow-hidden transition-colors"
              style={{
                border: '1px solid var(--border-default)',
                background: 'var(--bg-surface)',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--gold-bright)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-default)';
              }}
            >
              <img
                src={getImageUrl(source.image_id!)}
                alt={label}
                className="w-full h-full object-contain"
                style={{ background: 'var(--bg-elevated)' }}
              />
            </div>
            <p
              className="text-xs truncate max-w-[11rem] transition-colors"
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
  );
}

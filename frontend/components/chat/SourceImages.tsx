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
            <div className="w-48 h-48 rounded-lg overflow-hidden border border-gray-200 group-hover:border-blue-400 transition-colors shadow-sm">
              <img
                src={getImageUrl(source.image_id!)}
                alt={label}
                className="w-full h-full object-contain bg-white"
              />
            </div>
            <p className="text-xs text-gray-500 truncate max-w-[12rem] group-hover:text-blue-600">
              {label}
            </p>
          </a>
        );
      })}
    </div>
  );
}

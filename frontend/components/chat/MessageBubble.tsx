'use client';

import { useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ZoomIn, FileText } from 'lucide-react';
import type { Message, Source } from '@/types';
import { getImageUrl, getDocumentDownloadUrl } from '@/lib/api';
import ImageLightbox from './ImageLightbox';

interface Props {
  message: Message;
}

// ── Markdown renderer ─────────────────────────────────────────────────────────

function MarkdownSection({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => (
          <p className="mb-2 last:mb-0" style={{ color: 'var(--text-primary)' }}>
            {children}
          </p>
        ),
        ul: ({ children }) => (
          <ul className="list-disc list-inside mb-2 space-y-0.5">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal list-inside mb-2 space-y-0.5">{children}</ol>
        ),
        li: ({ children }) => (
          <li className="text-sm" style={{ color: 'var(--text-primary)' }}>
            {children}
          </li>
        ),
        h1: ({ children }) => (
          <h1
            className="text-base font-bold mb-2"
            style={{ color: 'var(--gold-bright)', fontFamily: 'Playfair Display, serif' }}
          >
            {children}
          </h1>
        ),
        h2: ({ children }) => (
          <h2
            className="text-sm font-bold mb-1.5"
            style={{ color: 'var(--gold-bright)', fontFamily: 'Playfair Display, serif' }}
          >
            {children}
          </h2>
        ),
        h3: ({ children }) => (
          <h3
            className="text-sm font-semibold mb-1"
            style={{ color: 'var(--gold-muted)', fontFamily: 'Playfair Display, serif' }}
          >
            {children}
          </h3>
        ),
        code: ({ children }) => (
          <code
            className="px-1.5 py-0.5 rounded text-xs font-mono"
            style={{
              background: 'var(--bg-hover)',
              color: 'var(--gold-bright)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            {children}
          </code>
        ),
        pre: ({ children }) => (
          <pre
            className="rounded-lg p-3 overflow-x-auto text-xs font-mono mb-2"
            style={{
              background: 'var(--bg-base)',
              border: '1px solid var(--border-default)',
            }}
          >
            {children}
          </pre>
        ),
        blockquote: ({ children }) => (
          <blockquote
            className="pl-3 italic mb-2"
            style={{
              borderLeft: '3px solid var(--gold-muted)',
              color: 'var(--text-secondary)',
            }}
          >
            {children}
          </blockquote>
        ),
        strong: ({ children }) => (
          <strong style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
            {children}
          </strong>
        ),
        a: ({ children, href }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: 'var(--gold-bright)', textDecoration: 'underline' }}
          >
            {children}
          </a>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

// ── Inline image card ─────────────────────────────────────────────────────────

interface ImageCardProps {
  source: Source;
  onOpen: (source: Source) => void;
}

function InlineImageCard({ source, onOpen }: ImageCardProps) {
  const label = `${source.filename}${source.page ? ` · p.${source.page}` : ''}`;
  return (
    <button
      onClick={() => onOpen(source)}
      className="group relative w-full text-left rounded-xl overflow-hidden transition-all"
      style={{
        border: '1px solid var(--border-default)',
        background: 'var(--bg-surface)',
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--gold-bright)';
        (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 0 0 2px var(--gold-subtle)';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-default)';
        (e.currentTarget as HTMLButtonElement).style.boxShadow = 'none';
      }}
      title="Clic para ampliar"
    >
      <div style={{ aspectRatio: '16/9', background: 'var(--bg-elevated)', overflow: 'hidden' }}>
        <img
          src={getImageUrl(source.image_id!)}
          alt={label}
          className="w-full h-full object-contain transition-transform duration-300 group-hover:scale-105"
          style={{ background: 'var(--bg-elevated)' }}
        />
      </div>
      <div
        className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: 'rgba(5,15,9,0.5)' }}
      >
        <div
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
          style={{
            background: 'var(--bg-elevated)',
            border: '1px solid var(--gold-bright)',
            color: 'var(--gold-bright)',
          }}
        >
          <ZoomIn size={13} />
          Ampliar
        </div>
      </div>
      <div
        className="px-2.5 py-1.5 text-xs truncate"
        style={{
          borderTop: '1px solid var(--border-subtle)',
          color: 'var(--text-muted)',
          background: 'var(--bg-elevated)',
        }}
      >
        {label}
      </div>
    </button>
  );
}

// ── Inline page citation badges ───────────────────────────────────────────────

interface PageCitation {
  doc_id: string;
  filename: string;
  page: number;
  viewUrl: string;
}

function buildPageCitations(textSources: Source[]): PageCitation[] {
  const seen = new Set<string>();
  const citations: PageCitation[] = [];
  const sorted = [...textSources]
    .filter((s) => s.page !== null)
    .sort((a, b) => (a.page ?? 0) - (b.page ?? 0));
  for (const s of sorted) {
    const key = `${s.doc_id}::${s.page}`;
    if (!seen.has(key)) {
      seen.add(key);
      citations.push({
        doc_id: s.doc_id,
        filename: s.filename,
        page: s.page!,
        viewUrl: getDocumentDownloadUrl(s.doc_id),
      });
    }
  }
  return citations;
}

function distributePageCitations(
  citations: PageCitation[],
  numSections: number,
): PageCitation[][] {
  const groups: PageCitation[][] = Array.from({ length: numSections }, () => []);
  if (numSections === 0 || citations.length === 0) return groups;
  citations.forEach((c, i) => {
    const idx = Math.min(
      Math.floor((i * numSections) / citations.length),
      numSections - 1,
    );
    groups[idx].push(c);
  });
  return groups;
}

function InlinePageCitations({ citations }: { citations: PageCitation[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 my-2">
      {citations.map((c) => (
        <a
          key={`${c.doc_id}-${c.page}`}
          href={`${c.viewUrl}#page=${c.page}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] transition-all"
          style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-gold)',
            color: 'var(--gold-muted)',
          }}
          onMouseEnter={(e) => {
            const el = e.currentTarget as HTMLAnchorElement;
            el.style.borderColor = 'var(--gold-bright)';
            el.style.color = 'var(--gold-bright)';
            el.style.background = 'var(--gold-subtle)';
          }}
          onMouseLeave={(e) => {
            const el = e.currentTarget as HTMLAnchorElement;
            el.style.borderColor = 'var(--border-gold)';
            el.style.color = 'var(--gold-muted)';
            el.style.background = 'var(--bg-surface)';
          }}
          title={`Abrir ${c.filename} en página ${c.page}`}
        >
          <FileText size={10} />
          <span className="max-w-[120px] truncate">{c.filename}</span>
          <span style={{ color: 'var(--text-muted)', margin: '0 1px' }}>·</span>
          <span>p.{c.page}</span>
        </a>
      ))}
    </div>
  );
}

// ── Content splitting helpers ─────────────────────────────────────────────────

function splitIntoSections(content: string): string[] {
  const parts = content.split(/(?=\n#{1,3} )/).filter((p) => p.trim());
  if (parts.length > 1) return parts;

  const paragraphs = content.split(/\n\n+/).filter((p) => p.trim());
  if (paragraphs.length <= 2) return [content];

  const sections: string[] = [];
  for (let i = 0; i < paragraphs.length; i += 2) {
    sections.push(paragraphs.slice(i, i + 2).join('\n\n'));
  }
  return sections;
}

function distributeImages(images: Source[], numSections: number): Source[][] {
  const groups: Source[][] = Array.from({ length: numSections }, () => []);
  if (numSections === 0 || images.length === 0) return groups;

  const sorted = [...images].sort((a, b) => (a.page ?? 0) - (b.page ?? 0));
  sorted.forEach((img, i) => {
    const idx = Math.min(
      Math.floor((i * numSections) / sorted.length),
      numSections - 1,
    );
    groups[idx].push(img);
  });
  return groups;
}

// ── Main component ────────────────────────────────────────────────────────────

export default function MessageBubble({ message }: Props) {
  const [lightboxSource, setLightboxSource] = useState<Source | null>(null);

  const openLightbox = useCallback((source: Source) => setLightboxSource(source), []);
  const closeLightbox = useCallback(() => setLightboxSource(null), []);

  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end animate-slide-up">
        <div
          className="max-w-[78%] rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap"
          style={{
            background: 'var(--gold-subtle)',
            border: '1px solid var(--border-gold)',
            color: 'var(--text-primary)',
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  // Assistant bubble
  const imageSources = message.sources.filter((s) => s.type === 'image' && s.image_id);
  const textSources = message.sources.filter((s) => s.type === 'text');

  const pageCitations = message.isStreaming ? [] : buildPageCitations(textSources);
  const showInlineImages = imageSources.length > 0 && !message.isStreaming;
  const showInlineCitations = pageCitations.length > 0;
  const useInterleavedLayout = showInlineImages || showInlineCitations;

  const sections = useInterleavedLayout
    ? splitIntoSections(message.content)
    : [message.content];
  const imageGroups = showInlineImages
    ? distributeImages(imageSources, sections.length)
    : [];
  const citationGroups = showInlineCitations
    ? distributePageCitations(pageCitations, sections.length)
    : [];

  return (
    <div className="flex justify-start animate-slide-up">
      <div className="max-w-[88%] w-full">
        {/* Message bubble */}
        <div
          className="rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed shadow-sm"
          style={{
            background: 'var(--bg-elevated)',
            borderTop: '1px solid var(--border-subtle)',
            borderRight: '1px solid var(--border-subtle)',
            borderBottom: '1px solid var(--border-subtle)',
            borderLeft: '2px solid var(--gold-bright)',
            color: 'var(--text-primary)',
          }}
        >
          {message.isStreaming && !message.content ? (
            <span className="flex items-center gap-1.5">
              <span
                className="w-1.5 h-1.5 rounded-full animate-bounce [animation-delay:0ms]"
                style={{ background: 'var(--gold-bright)' }}
              />
              <span
                className="w-1.5 h-1.5 rounded-full animate-bounce [animation-delay:150ms]"
                style={{ background: 'var(--gold-bright)' }}
              />
              <span
                className="w-1.5 h-1.5 rounded-full animate-bounce [animation-delay:300ms]"
                style={{ background: 'var(--gold-bright)' }}
              />
            </span>
          ) : useInterleavedLayout ? (
            <>
              {sections.map((section, i) => (
                <div key={i}>
                  <MarkdownSection content={section} />
                  {imageGroups[i]?.length > 0 && (
                    <div
                      className="grid gap-3 my-3"
                      style={{
                        gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                        maxWidth: imageGroups[i].length === 1 ? '260px' : undefined,
                      }}
                    >
                      {imageGroups[i].map((src) => (
                        <InlineImageCard
                          key={src.image_id}
                          source={src}
                          onOpen={openLightbox}
                        />
                      ))}
                    </div>
                  )}
                  <InlinePageCitations citations={citationGroups[i] ?? []} />
                </div>
              ))}
            </>
          ) : (
            <MarkdownSection content={message.content} />
          )}
        </div>

      </div>

      <ImageLightbox source={lightboxSource} onClose={closeLightbox} />
    </div>
  );
}

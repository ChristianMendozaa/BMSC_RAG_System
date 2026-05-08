'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message } from '@/types';
import SourceImages from './SourceImages';

interface Props {
  message: Message;
}

export default function MessageBubble({ message }: Props) {
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

  return (
    <div className="flex justify-start animate-slide-up">
      <div className="max-w-[88%]">
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
          ) : (
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
              {message.content}
            </ReactMarkdown>
          )}
        </div>
        {message.sources.length > 0 && !message.isStreaming && (
          <SourceImages sources={message.sources} />
        )}
      </div>
    </div>
  );
}

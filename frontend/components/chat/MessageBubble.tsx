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
      <div className="flex justify-end">
        <div className="max-w-[75%] bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%]">
        <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-gray-900 leading-relaxed shadow-sm">
          {message.isStreaming && !message.content ? (
            <span className="flex items-center gap-1.5 text-gray-400">
              <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
            </span>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-0.5">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-0.5">{children}</ol>,
                li: ({ children }) => <li className="text-sm">{children}</li>,
                h1: ({ children }) => <h1 className="text-base font-bold mb-1">{children}</h1>,
                h2: ({ children }) => <h2 className="text-sm font-bold mb-1">{children}</h2>,
                h3: ({ children }) => <h3 className="text-sm font-semibold mb-1">{children}</h3>,
                code: ({ children }) => (
                  <code className="bg-gray-100 text-gray-800 px-1 py-0.5 rounded text-xs font-mono">
                    {children}
                  </code>
                ),
                pre: ({ children }) => (
                  <pre className="bg-gray-100 rounded-md p-3 overflow-x-auto text-xs font-mono mb-2">
                    {children}
                  </pre>
                ),
                blockquote: ({ children }) => (
                  <blockquote className="border-l-4 border-gray-300 pl-3 italic text-gray-600 mb-2">
                    {children}
                  </blockquote>
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

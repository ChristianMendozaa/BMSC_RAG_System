'use client';

import { useEffect, useState } from 'react';

const STATUS_MESSAGES = [
  'Pensando…',
  'Consultando los documentos…',
  'Conectando ideas…',
  'Revisando el archivo…',
  'Afinando los detalles…',
  'Casi listo…',
  'Procesando con cuidado…',
  'Buscando en las páginas…',
];

export default function ThinkingIndicator({ message }: { message?: string }) {
  const [msgIndex, setMsgIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setMsgIndex((i) => (i + 1) % STATUS_MESSAGES.length);
    }, 2000);
    return () => clearInterval(id);
  }, []);

  return (
    <span className="flex items-center gap-3">
      {/* Morph squares */}
      <span className="relative w-8 h-8 flex-shrink-0">
        {[0, 1, 2, 3].map((i) => (
          <span
            key={i}
            className="absolute w-2.5 h-2.5"
            style={{
              top: '50%',
              left: '50%',
              marginTop: '-5px',
              marginLeft: '-5px',
              background: 'var(--gold-bright)',
              animation: `morph-${i} 2s infinite ease-in-out`,
              animationDelay: `${i * 0.18}s`,
            }}
          />
        ))}
      </span>

      {/* Rotating status text */}
      <span
        className="text-xs whitespace-nowrap"
        style={{
          color: 'var(--gold-muted)',
          fontFamily: 'DM Sans, sans-serif',
          animation: 'thinking-fade 2s infinite ease-in-out',
          animationDelay: '0.2s',
        }}
      >
        {message || STATUS_MESSAGES[msgIndex]}
      </span>
    </span>
  );
}

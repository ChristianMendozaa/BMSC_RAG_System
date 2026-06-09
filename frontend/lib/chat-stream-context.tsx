'use client';

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react';
import { v4 as uuidv4 } from 'uuid';
import type { ChatRequest, Source } from '@/types';
import {
  getActiveGeneration,
  resumeStream,
  stopChat,
  streamChat,
} from './api';

export interface StreamEntry {
  content: string;
  sources: Source[];
  status: 'streaming' | 'done' | 'stopped' | 'error';
  error?: string;
}

interface ChatStreamCtx {
  /** Start a new chat POST stream. Returns the temp key used before session_id is known. */
  startStream: (
    request: ChatRequest,
    opts: { onNewSession: (realSessionId: string, tempKey: string) => void },
  ) => string;
  stopStream: (sessionId: string) => void;
  getStream: (sessionId: string) => StreamEntry | undefined;
  clearStream: (sessionId: string) => void;
  /** If a generation is running server-side but not tracked here (e.g. after reload), subscribe. */
  attachIfActive: (sessionId: string) => Promise<void>;
}

const ChatStreamContext = createContext<ChatStreamCtx | null>(null);

export function useChatStream(): ChatStreamCtx {
  const ctx = useContext(ChatStreamContext);
  if (!ctx) throw new Error('useChatStream must be used inside ChatStreamProvider');
  return ctx;
}

export function ChatStreamProvider({ children }: { children: React.ReactNode }) {
  const [streams, setStreams] = useState<Map<string, StreamEntry>>(new Map());
  const abortRefs = useRef<Map<string, AbortController>>(new Map());
  // Tracks keys currently being attached to avoid duplicate fetches
  const attachingRef = useRef<Set<string>>(new Set());

  const _update = useCallback((key: string, patch: Partial<StreamEntry>) => {
    setStreams((prev) => {
      const entry = prev.get(key);
      if (!entry) return prev;
      const next = new Map(prev);
      next.set(key, { ...entry, ...patch });
      return next;
    });
  }, []);

  const _upsert = useCallback((key: string, entry: StreamEntry) => {
    setStreams((prev) => {
      const next = new Map(prev);
      next.set(key, entry);
      return next;
    });
  }, []);

  const clearStream = useCallback((sessionId: string) => {
    setStreams((prev) => {
      if (!prev.has(sessionId)) return prev;
      const next = new Map(prev);
      next.delete(sessionId);
      return next;
    });
    const ctrl = abortRefs.current.get(sessionId);
    ctrl?.abort();
    abortRefs.current.delete(sessionId);
  }, []);

  const startStream = useCallback(
    (
      request: ChatRequest,
      opts: { onNewSession: (realSessionId: string, tempKey: string) => void },
    ): string => {
      const tempKey = request.session_id ?? uuidv4();
      const ctrl = new AbortController();
      abortRefs.current.set(tempKey, ctrl);

      _upsert(tempKey, { content: '', sources: [], status: 'streaming' });

      let resolvedKey = tempKey;

      streamChat(request, {
        signal: ctrl.signal,
        onSession: (realId) => {
          if (realId !== tempKey) {
            // Re-key the entry
            setStreams((prev) => {
              const entry = prev.get(tempKey);
              if (!entry) return prev;
              const next = new Map(prev);
              next.delete(tempKey);
              next.set(realId, entry);
              return next;
            });
            const existing = abortRefs.current.get(tempKey);
            if (existing) {
              abortRefs.current.delete(tempKey);
              abortRefs.current.set(realId, existing);
            }
            resolvedKey = realId;
            opts.onNewSession(realId, tempKey);
          }
        },
        onToken: (token) => {
          setStreams((prev) => {
            const entry = prev.get(resolvedKey);
            if (!entry) return prev;
            const next = new Map(prev);
            next.set(resolvedKey, { ...entry, content: entry.content + token });
            return next;
          });
        },
        onDone: (sessionId, sources, opts2) => {
          const key = sessionId || resolvedKey;
          _update(key, {
            sources,
            status: opts2?.stopped ? 'stopped' : 'done',
          });
          abortRefs.current.delete(key);
        },
        onError: (err) => {
          _update(resolvedKey, { status: 'error', error: err.message });
          abortRefs.current.delete(resolvedKey);
        },
      });

      return tempKey;
    },
    [_upsert, _update],
  );

  const stopStream = useCallback((sessionId: string) => {
    stopChat(sessionId).catch(() => {});
    // The SSE stream will deliver a `stopped` event from the server which
    // updates status; no need to abort the local reader.
  }, []);

  const getStream = useCallback(
    (sessionId: string): StreamEntry | undefined => streams.get(sessionId),
    [streams],
  );

  const attachIfActive = useCallback(
    async (sessionId: string) => {
      if (streams.has(sessionId)) return;
      if (attachingRef.current.has(sessionId)) return;
      attachingRef.current.add(sessionId);

      try {
        const info = await getActiveGeneration(sessionId);
        if (!info.active && info.status !== 'running') return;

        _upsert(sessionId, {
          content: info.text,
          sources: [],
          status: 'streaming',
        });

        const ctrl = new AbortController();
        abortRefs.current.set(sessionId, ctrl);

        resumeStream(sessionId, {
          signal: ctrl.signal,
          onSession: () => {},
          onToken: (token) => {
            setStreams((prev) => {
              const entry = prev.get(sessionId);
              if (!entry) return prev;
              const next = new Map(prev);
              next.set(sessionId, { ...entry, content: entry.content + token });
              return next;
            });
          },
          onDone: (_id, sources, opts2) => {
            _update(sessionId, {
              sources,
              status: opts2?.stopped ? 'stopped' : 'done',
            });
            abortRefs.current.delete(sessionId);
          },
          onError: (err) => {
            _update(sessionId, { status: 'error', error: err.message });
            abortRefs.current.delete(sessionId);
          },
        });
      } catch {
        // generation not active or network error — silently skip
      } finally {
        attachingRef.current.delete(sessionId);
      }
    },
    [streams, _upsert, _update],
  );

  const ctxValue = useMemo(
    () => ({ startStream, stopStream, getStream, clearStream, attachIfActive }),
    [startStream, stopStream, getStream, clearStream, attachIfActive],
  );

  return (
    <ChatStreamContext.Provider value={ctxValue}>
      {children}
    </ChatStreamContext.Provider>
  );
}

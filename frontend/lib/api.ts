import type {
  ChatRequest,
  DocumentDetail,
  DocumentsListResponse,
  IngestResponse,
  Message,
  Source,
} from '@/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export { API_URL };

function getAuthHeaders(isFormData = false): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (!isFormData) headers['Content-Type'] = 'application/json';
  return headers;
}

// ── Documents ──────────────────────────────────────────────────────────────

export async function getDocuments(skip = 0, limit = 50): Promise<DocumentsListResponse> {
  const res = await fetch(`${API_URL}/api/documents?skip=${skip}&limit=${limit}`, {
    headers: getAuthHeaders()
  });
  if (!res.ok) throw new Error(`Failed to fetch documents: ${res.status}`);
  return res.json() as Promise<DocumentsListResponse>;
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  const res = await fetch(`${API_URL}/api/documents/${id}`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch document: ${res.status}`);
  return res.json() as Promise<DocumentDetail>;
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/documents/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
  if (!res.ok && res.status !== 204) {
    throw new Error(`Failed to delete document: ${res.status}`);
  }
}

export async function uploadDocument(file: File, roleId?: string): Promise<IngestResponse> {
  const form = new FormData();
  form.append('file', file);
  if (roleId) form.append('role_id', roleId);
  const res = await fetch(`${API_URL}/api/ingest`, { method: 'POST', body: form, headers: getAuthHeaders(true) });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail: string }).detail ?? `Upload failed: ${res.status}`);
  }
  return res.json() as Promise<IngestResponse>;
}

export function getImageUrl(imageId: string): string {
  return `${API_URL}/api/images/${imageId}`;
}

export async function getConversationHistory(conversationId: string): Promise<Message[]> {
  const res = await fetch(`${API_URL}/api/chat/history/${conversationId}`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch history: ${res.status}`);
  const turns = await res.json() as { role: string; content: string; sources: Source[] }[];
  return turns.map((t) => ({
    id: crypto.randomUUID(),
    role: t.role as Message['role'],
    content: t.content,
    sources: t.sources ?? [],
  }));
}

// ── Chat (SSE via fetch) ────────────────────────────────────────────────────

export async function streamChat(
  request: ChatRequest,
  onToken: (token: string) => void,
  onDone: (conversationId: string, sources: Source[]) => void,
  onError: (err: Error) => void,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/chat`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(request),
    });
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)));
    return;
  }

  if (!response.ok) {
    onError(new Error(`Chat request failed: ${response.status}`));
    return;
  }

  if (!response.body) {
    onError(new Error('No response body for SSE stream'));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        const raw = trimmed.slice(5).trim();
        if (!raw || raw === '[DONE]') continue;

        try {
          const payload = JSON.parse(raw) as {
            type: string;
            content?: string;
            conversation_id?: string;
            sources?: Source[];
            message?: string;
          };

          if (payload.type === 'token' && payload.content) {
            onToken(payload.content);
          } else if (payload.type === 'done') {
            onDone(payload.conversation_id ?? '', payload.sources ?? []);
          } else if (payload.type === 'error') {
            onError(new Error(payload.message ?? 'Unknown stream error'));
          }
        } catch {
          // malformed SSE line — skip
        }
      }
    }
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)));
  } finally {
    reader.releaseLock();
  }
}

// ── Admin Endpoints ─────────────────────────────────────────────────────────

export async function getRoles() {
  const res = await fetch(`${API_URL}/api/admin/roles`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Failed to fetch roles');
  return res.json();
}

export async function createRole(name: string) {
  const res = await fetch(`${API_URL}/api/admin/roles`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ name })
  });
  if (!res.ok) throw new Error('Failed to create role');
  return res.json();
}

export async function getUsers() {
  const res = await fetch(`${API_URL}/api/admin/users`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Failed to fetch users');
  return res.json();
}

export async function createUser(data: any) {
  const res = await fetch(`${API_URL}/api/admin/users`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!res.ok) throw new Error('Failed to create user');
  return res.json();
}

export async function getIncidents() {
  const res = await fetch(`${API_URL}/api/admin/incidents`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Failed to fetch incidents');
  return res.json();
}

export async function createIncident(data: any) {
  const res = await fetch(`${API_URL}/api/admin/incidents`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!res.ok) throw new Error('Failed to create incident');
  return res.json();
}

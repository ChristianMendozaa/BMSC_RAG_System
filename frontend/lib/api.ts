import type {
  BlockerItem,
  ChatRequest,
  ChatSessionDetail,
  ChatSessionListItem,
  DocumentDetail,
  DocumentsListResponse,
  IngestResponse,
  Message,
  ResumeCheckOut,
  Source,
} from '@/types';

export type { BlockerItem, ChatSessionDetail, ChatSessionListItem, ResumeCheckOut };

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export { API_URL };

// ── Auth types ─────────────────────────────────────────────────────────────

export interface RoleInfo {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  can_manage_users: boolean;
  can_manage_collections: boolean;
  can_upload_documents: boolean;
  can_delete_documents: boolean;
}

export interface UserInfo {
  id: string;
  username: string;
  is_active: boolean;
  role: RoleInfo | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserInfo;
}

export interface UserOut {
  id: string;
  username: string;
  is_active: boolean;
  is_system: boolean;
  role_id: string | null;
  role: RoleInfo | null;
  created_at: string;
}

export interface UsersListResponse {
  items: UserOut[];
  total: number;
  skip: number;
  limit: number;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function getAuthHeaders(isFormData = false): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (!isFormData) headers['Content-Type'] = 'application/json';
  return headers;
}

function handle401(): never {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    window.location.href = '/login';
  }
  throw new Error('Unauthorized');
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 401) handle401();
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Auth ───────────────────────────────────────────────────────────────────

export async function login(username: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '' }));
    const detail = (err as { detail?: string }).detail;
    if (res.status === 401) throw new Error(detail || 'Credenciales incorrectas');
    if (res.status === 403) throw new Error(detail || 'Acceso denegado');
    throw new Error(detail || `Error al iniciar sesión: ${res.status}`);
  }
  return res.json() as Promise<LoginResponse>;
}

export async function logout(): Promise<void> {
  try {
    await fetch(`${API_URL}/api/auth/logout`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
  } catch {
    // ignorar errores de red en logout
  } finally {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
    }
  }
}

export async function getMe(): Promise<UserInfo> {
  const res = await fetch(`${API_URL}/api/auth/me`, { headers: getAuthHeaders() });
  return handleResponse<UserInfo>(res);
}

// ── Users CRUD ─────────────────────────────────────────────────────────────

export async function getUsers(skip = 0, limit = 50): Promise<UsersListResponse> {
  const res = await fetch(`${API_URL}/api/users?skip=${skip}&limit=${limit}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<UsersListResponse>(res);
}

export async function createUser(data: {
  username: string;
  password: string;
  role_id: string;
  is_active?: boolean;
}): Promise<UserOut> {
  const res = await fetch(`${API_URL}/api/users`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<UserOut>(res);
}

export async function updateUser(
  id: string,
  data: { username?: string; password?: string; role_id?: string; is_active?: boolean },
): Promise<UserOut> {
  const res = await fetch(`${API_URL}/api/users/${id}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<UserOut>(res);
}

export async function deactivateUser(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/users/${id}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  return handleResponse<void>(res);
}

export async function activateUser(id: string): Promise<UserOut> {
  const res = await fetch(`${API_URL}/api/users/${id}/activate`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  return handleResponse<UserOut>(res);
}

export async function resetUserPassword(id: string, newPassword: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/users/${id}/reset-password`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ new_password: newPassword }),
  });
  return handleResponse<void>(res);
}

export async function assignUserRole(id: string, roleId: string | null): Promise<UserOut> {
  const res = await fetch(`${API_URL}/api/users/${id}/role`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ role_id: roleId }),
  });
  return handleResponse<UserOut>(res);
}

export async function renameUser(id: string, username: string): Promise<UserOut> {
  const res = await fetch(`${API_URL}/api/users/${id}/username`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ username }),
  });
  return handleResponse<UserOut>(res);
}

// ── Roles CRUD ─────────────────────────────────────────────────────────────

export async function getRoles(): Promise<RoleInfo[]> {
  const res = await fetch(`${API_URL}/api/roles`, { headers: getAuthHeaders() });
  return handleResponse<RoleInfo[]>(res);
}

export async function createRole(data: {
  name: string;
  description?: string;
  can_manage_users?: boolean;
  can_manage_collections?: boolean;
  can_upload_documents?: boolean;
  can_delete_documents?: boolean;
}): Promise<RoleInfo> {
  const res = await fetch(`${API_URL}/api/roles`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<RoleInfo>(res);
}

export async function updateRole(
  id: string,
  data: Partial<{
    name: string;
    description: string;
    can_manage_users: boolean;
    can_manage_collections: boolean;
    can_upload_documents: boolean;
    can_delete_documents: boolean;
  }>,
): Promise<RoleInfo> {
  const res = await fetch(`${API_URL}/api/roles/${id}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<RoleInfo>(res);
}

export async function deleteRole(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/roles/${id}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  return handleResponse<void>(res);
}

// ── Collections ────────────────────────────────────────────────────

export interface CollectionOut {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
}

export async function getCollections(): Promise<CollectionOut[]> {
  const res = await fetch(`${API_URL}/api/collections`, { headers: getAuthHeaders() });
  return handleResponse<CollectionOut[]>(res);
}

export async function createCollection(data: {
  name: string;
  description?: string;
}): Promise<CollectionOut> {
  const res = await fetch(`${API_URL}/api/collections`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<CollectionOut>(res);
}

export async function updateCollection(
  id: string,
  data: Partial<{ name: string; description: string; is_active: boolean }>,
): Promise<CollectionOut> {
  const res = await fetch(`${API_URL}/api/collections/${id}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<CollectionOut>(res);
}

export interface DeleteCollectionResult {
  deleted: boolean;
  has_documents: boolean;
  document_count: number;
  obsoleted?: number;
  purged?: number;
}

export class CollectionHasDocumentsError extends Error {
  document_count: number;
  constructor(count: number, message?: string) {
    super(message || 'La colección tiene documentos');
    this.name = 'CollectionHasDocumentsError';
    this.document_count = count;
  }
}

export async function deleteCollection(
  id: string,
  action: 'auto' | 'obsolete' | 'delete' = 'auto',
): Promise<DeleteCollectionResult> {
  const res = await fetch(`${API_URL}/api/collections/${id}?action=${action}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (res.status === 409) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: { document_count?: number } }).detail;
    throw new CollectionHasDocumentsError(detail?.document_count ?? 0);
  }
  return handleResponse<DeleteCollectionResult>(res);
}

// ── PG Documents ───────────────────────────────────────────────────

export interface PgDocumentOut {
  doc_id: string;
  title: string;
  collection_id: string | null;
  collection_name: string | null;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  pg_status: string;
  rag_status: string;
  rag_chunk_count: number;
  rag_image_count: number;
  created_at: string;
  updated_at: string;
}

export interface PgDocumentsFilters {
  search?: string;
  collection_id?: string;
  status?: 'ACTIVE' | 'OBSOLETE';
  uncategorized?: boolean;
  sort?: 'newest' | 'oldest_obsolete' | 'name';
}

export async function getPgDocuments(filters: PgDocumentsFilters = {}): Promise<PgDocumentOut[]> {
  const params = new URLSearchParams();
  if (filters.search) params.set('search', filters.search);
  if (filters.uncategorized) params.set('uncategorized', 'true');
  else if (filters.collection_id) params.set('collection_id', filters.collection_id);
  if (filters.status) params.set('status', filters.status);
  if (filters.sort) params.set('sort', filters.sort);
  const qs = params.toString();
  const res = await fetch(`${API_URL}/api/pg-documents${qs ? `?${qs}` : ''}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<PgDocumentOut[]>(res);
}

export async function uploadToCollection(
  collectionId: string,
  file: File,
): Promise<{ doc_id: string; filename: string; collection_id: string | null; status: string }> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_URL}/api/collections/${collectionId}/upload`, {
    method: 'POST',
    headers: getAuthHeaders(true),
    body: form,
  });
  return handleResponse<{ doc_id: string; filename: string; collection_id: string | null; status: string }>(res);
}

export async function uploadPgDocument(
  file: File,
  collectionId: string | null,
): Promise<{ doc_id: string; filename: string; collection_id: string | null; status: string }> {
  const form = new FormData();
  form.append('file', file);
  if (collectionId) form.append('collection_id', collectionId);
  const res = await fetch(`${API_URL}/api/pg-documents/upload`, {
    method: 'POST',
    headers: getAuthHeaders(true),
    body: form,
  });
  return handleResponse<{ doc_id: string; filename: string; collection_id: string | null; status: string }>(res);
}

export async function updatePgDocument(
  docId: string,
  patch: { title?: string; collection_id?: string | null },
): Promise<PgDocumentOut> {
  const body: { title?: string; collection_id?: string; clear_collection?: boolean } = {};
  if (patch.title !== undefined) body.title = patch.title;
  if (patch.collection_id === null) body.clear_collection = true;
  else if (patch.collection_id !== undefined) body.collection_id = patch.collection_id;
  const res = await fetch(`${API_URL}/api/pg-documents/${docId}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse<PgDocumentOut>(res);
}

export async function reactivatePgDocument(docId: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/pg-documents/${docId}/reactivate`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  return handleResponse<void>(res);
}

export async function permanentDeletePgDocument(docId: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/pg-documents/${docId}/permanent`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  return handleResponse<void>(res);
}

export async function downloadDocument(docId: string, filename: string): Promise<void> {
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch(`${API_URL}/api/pg-documents/${docId}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Error al descargar: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function deletePgDocument(docId: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/pg-documents/${docId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  return handleResponse<void>(res);
}

// ── Collection Permissions ─────────────────────────────────────────

export interface RolePermEntry {
  role_id: string;
  role_name: string;
  can_view: boolean;
  can_download: boolean;
  can_chat: boolean;
}

export interface UserPermEntry {
  id: string;
  user_id: string;
  collection_id: string;
  can_view: boolean;
  can_download: boolean;
  can_chat: boolean;
}

export async function getCollectionRolePerms(collectionId: string): Promise<RolePermEntry[]> {
  const res = await fetch(`${API_URL}/api/collections/${collectionId}/permissions/roles`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<RolePermEntry[]>(res);
}

export async function updateCollectionRolePerm(
  collectionId: string,
  roleId: string,
  perms: { can_view: boolean; can_download: boolean; can_chat: boolean },
): Promise<void> {
  const res = await fetch(
    `${API_URL}/api/collections/${collectionId}/permissions/roles/${roleId}`,
    { method: 'PUT', headers: getAuthHeaders(), body: JSON.stringify(perms) },
  );
  return handleResponse<void>(res);
}

export async function getCollectionUserPerms(collectionId: string): Promise<UserPermEntry[]> {
  const res = await fetch(`${API_URL}/api/collections/${collectionId}/permissions/users`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<UserPermEntry[]>(res);
}

export async function updateCollectionUserPerm(
  collectionId: string,
  userId: string,
  perms: { can_view: boolean; can_download: boolean; can_chat: boolean },
): Promise<void> {
  const res = await fetch(
    `${API_URL}/api/collections/${collectionId}/permissions/users/${userId}`,
    { method: 'PUT', headers: getAuthHeaders(), body: JSON.stringify(perms) },
  );
  return handleResponse<void>(res);
}

export async function deleteCollectionUserPerm(
  collectionId: string,
  userId: string,
): Promise<void> {
  const res = await fetch(
    `${API_URL}/api/collections/${collectionId}/permissions/users/${userId}`,
    { method: 'DELETE', headers: getAuthHeaders() },
  );
  return handleResponse<void>(res);
}

// ── Accessible collections (chat scope) ───────────────────────────────────

export interface AccessibleDocumentOut {
  doc_id: string;
  title: string;
  original_filename: string;
  mime_type: string;
}

export interface AccessibleCollectionOut {
  id: string;
  name: string;
  description: string | null;
  documents: AccessibleDocumentOut[];
}

export async function getAccessibleCollections(): Promise<AccessibleCollectionOut[]> {
  const res = await fetch(`${API_URL}/api/collections/accessible`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<AccessibleCollectionOut[]>(res);
}

// ── Document permissions ────────────────────────────────────────────────────

export interface DocRolePermEntry {
  id: string;
  role_id: string;
  role_name: string;
  document_id: string;
  can_view: boolean;
  can_download: boolean;
  can_chat: boolean;
}

export interface DocUserPermEntry {
  id: string;
  user_id: string;
  username: string;
  document_id: string;
  can_view: boolean;
  can_download: boolean;
  can_chat: boolean;
}

export async function getDocumentRolePerms(docId: string): Promise<DocRolePermEntry[]> {
  const res = await fetch(`${API_URL}/api/documents/${docId}/permissions/roles`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<DocRolePermEntry[]>(res);
}

export async function updateDocumentRolePerm(
  docId: string,
  roleId: string,
  perms: { can_view: boolean; can_download: boolean; can_chat: boolean },
): Promise<void> {
  const res = await fetch(
    `${API_URL}/api/documents/${docId}/permissions/roles/${roleId}`,
    { method: 'PUT', headers: getAuthHeaders(), body: JSON.stringify(perms) },
  );
  return handleResponse<void>(res);
}

export async function getDocumentUserPerms(docId: string): Promise<DocUserPermEntry[]> {
  const res = await fetch(`${API_URL}/api/documents/${docId}/permissions/users`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<DocUserPermEntry[]>(res);
}

export async function updateDocumentUserPerm(
  docId: string,
  userId: string,
  perms: { can_view: boolean; can_download: boolean; can_chat: boolean },
): Promise<void> {
  const res = await fetch(
    `${API_URL}/api/documents/${docId}/permissions/users/${userId}`,
    { method: 'PUT', headers: getAuthHeaders(), body: JSON.stringify(perms) },
  );
  return handleResponse<void>(res);
}

export async function deleteDocumentUserPerm(docId: string, userId: string): Promise<void> {
  const res = await fetch(
    `${API_URL}/api/documents/${docId}/permissions/users/${userId}`,
    { method: 'DELETE', headers: getAuthHeaders() },
  );
  return handleResponse<void>(res);
}

// ── Incidents (endpoint legacy SQLite) ────────────────────────────────────

export async function getIncidents() {
  const res = await fetch(`${API_URL}/api/admin/incidents`, { headers: getAuthHeaders() });
  return handleResponse<unknown[]>(res);
}

export async function createIncident(data: {
  description: string;
  solution: string;
  resolved_by: string;
}) {
  const res = await fetch(`${API_URL}/api/admin/incidents`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<unknown>(res);
}

// ── Documents ──────────────────────────────────────────────────────────────

export async function getDocuments(skip = 0, limit = 50): Promise<DocumentsListResponse> {
  const res = await fetch(`${API_URL}/api/documents?skip=${skip}&limit=${limit}`, {
    headers: getAuthHeaders(),
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
  const res = await fetch(`${API_URL}/api/documents/${id}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!res.ok && res.status !== 204) {
    throw new Error(`Failed to delete document: ${res.status}`);
  }
}

export async function uploadDocument(file: File, roleId?: string): Promise<IngestResponse> {
  const form = new FormData();
  form.append('file', file);
  if (roleId) form.append('role_id', roleId);
  const res = await fetch(`${API_URL}/api/ingest`, {
    method: 'POST',
    body: form,
    headers: getAuthHeaders(true),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail: string }).detail ?? `Upload failed: ${res.status}`);
  }
  return res.json() as Promise<IngestResponse>;
}

export function getImageUrl(imageId: string): string {
  return `${API_URL}/api/images/${imageId}`;
}

export function getDocumentDownloadUrl(docId: string, forceDownload = false): string {
  return `${API_URL}/api/documents/${docId}/download${forceDownload ? '?dl=1' : ''}`;
}

// ── Chat sessions (history) ────────────────────────────────────────────────

export async function listChatSessions(): Promise<ChatSessionListItem[]> {
  const res = await fetch(`${API_URL}/api/conversations`, { headers: getAuthHeaders() });
  return handleResponse<ChatSessionListItem[]>(res);
}

export async function getChatSession(id: string): Promise<ChatSessionDetail> {
  const res = await fetch(`${API_URL}/api/conversations/${id}`, { headers: getAuthHeaders() });
  return handleResponse<ChatSessionDetail>(res);
}

export async function resumeCheckSession(id: string): Promise<ResumeCheckOut> {
  const res = await fetch(`${API_URL}/api/conversations/${id}/resume-check`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  return handleResponse<ResumeCheckOut>(res);
}

export async function deleteChatSession(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/conversations/${id}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  return handleResponse<void>(res);
}

/** @deprecated Use getChatSession instead */
export async function getConversationHistory(sessionId: string): Promise<Message[]> {
  const detail = await getChatSession(sessionId);
  return detail.messages.map((m) => ({
    id: crypto.randomUUID(),
    role: m.role as Message['role'],
    content: m.content,
    sources: m.sources ?? [],
  }));
}

// ── Chat (SSE via fetch) ────────────────────────────────────────────────────

export async function streamChat(
  request: ChatRequest,
  onToken: (token: string) => void,
  onDone: (sessionId: string, sources: Source[]) => void,
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
    if (response.status === 401) handle401();
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
            session_id?: string;
            sources?: Source[];
            message?: string;
          };

          if (payload.type === 'token' && payload.content) {
            onToken(payload.content);
          } else if (payload.type === 'done') {
            onDone(payload.session_id ?? '', payload.sources ?? []);
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

export type DocumentStatus = 'pending' | 'processing' | 'indexing_images' | 'ready' | 'error';

export interface DocumentSummary {
  id: string;
  filename: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
  error_message: string | null;
  chunk_count: number;
  image_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChunkOut {
  id: string;
  content: string;
  chunk_index: number;
  page_number: number | null;
  chunk_type: 'text' | 'image_description';
}

export interface DocumentImageOut {
  id: string;
  minio_path: string;
  page_number: number | null;
  image_index: number;
  description: string | null;
}

export interface DocumentDetail extends DocumentSummary {
  chunks: ChunkOut[];
  images: DocumentImageOut[];
}

export interface DocumentsListResponse {
  items: DocumentSummary[];
  total: number;
  skip: number;
  limit: number;
}

export interface DocumentStatusResponse {
  id: string;
  status: DocumentStatus;
  error_message: string | null;
  chunk_count: number;
  image_count: number;
}

export interface Source {
  type: 'text' | 'image';
  doc_id: string;
  filename: string;
  page: number | null;
  image_id: string | null;
  score: number;
}

export type MessageRole = 'user' | 'assistant';

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  sources: Source[];
  isStreaming?: boolean;
  statusMessage?: string;
  traceEvents?: AgentTraceEvent[];
  mode?: ChatMode;
}

export type ChatMode = 'fast' | 'agentic';

export interface AgentTraceEvent {
  id: string;
  stage: string;
  title: string;
  detail?: string | null;
  status: 'running' | 'completed' | 'error';
}

export type ChatStatusStage =
  | 'preparing'
  | 'retrieving'
  | 'reranking'
  | 'agent_searching'
  | 'agent_assessing'
  | 'agent_expanding'
  | 'agent_finalizing'
  | 'queued'
  | 'prefilling'
  | 'generating'
  | 'cache_hit';

export interface ChatRequest {
  message: string;
  session_id: string | null;
  collection_id: string | null;
  document_ids: string[] | null;
  mode?: ChatMode;
}

export interface ChatSessionListItem {
  id: string;
  title: string;
  collection_id: string | null;
  document_ids: string[];
  updated_at: string;
  document_count: number;
}

export interface ChatMessageOut {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources: Source[];
}

export interface ChatSessionDetail {
  id: string;
  title: string;
  collection_id: string | null;
  document_ids: string[];
  created_at: string;
  updated_at: string;
  messages: ChatMessageOut[];
}

export interface BlockerItem {
  doc_id: string | null;
  doc_title_snapshot: string;
  reason: string;
}

export interface ResumeCheckOut {
  can_resume: boolean;
  blockers: BlockerItem[];
  collection_id: string | null;
  document_ids: string[];
}

export interface IngestResponse {
  doc_id: string;
  filename: string;
  status: string;
}

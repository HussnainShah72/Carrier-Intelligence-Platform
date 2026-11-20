/**
 * API client.
 *
 * One place that knows how to talk to the backend, so components never build
 * URLs or parse errors themselves. Two things it does that matter:
 *
 *  1. `ApiFailure` carries the backend's own error `code` and user-safe
 *     `message`, so every screen can show something useful instead of
 *     "Request failed".
 *  2. `streamTurn()` reads the Server-Sent Events stream for an interview turn
 *     and invokes a callback per event, which is what lets audio start playing
 *     before the reply has finished generating.
 */

import type {
  CVListItem,
  CVUploadResponse,
  DashboardResponse,
  GapResponse,
  HealthResponse,
  ImproveResponse,
  Interview,
  InterviewMetrics,
  InterviewReport,
  InterviewTurn,
  MetricsOverview,
  RoleAnalysisResponse,
  RoleListItem,
  RoleRequirements,
  Rubric,
  SettingsResponse,
  SpeechDescribe,
  StageInfo,
  TranscriptionInfo,
  TurnEvent,
} from './types';

const BASE = '/api';

export class ApiFailure extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(message: string, code = 'unknown', status = 0, details?: unknown) {
    super(message);
    this.name = 'ApiFailure';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function toFailure(response: Response): Promise<ApiFailure> {
  let message = `The server returned ${response.status}.`;
  let code = `http_${response.status}`;
  let details: unknown;

  try {
    const body = await response.json();
    if (body?.error) {
      message = body.error.message || message;
      code = body.error.code || code;
      details = body.error.details;
    } else if (typeof body?.detail === 'string') {
      message = body.detail;
    }
  } catch {
    /* body was not JSON; keep the generic message */
  }
  return new ApiFailure(message, code, response.status, details);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiFailure(
      'Could not reach the backend. Make sure it is running on port 8000 (see the README).',
      'network_error',
    );
  }

  if (!response.ok) throw await toFailure(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });
const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
const del = <T>(path: string) => request<T>(path, { method: 'DELETE' });

/* ========================================================== Module 1: CV === */

export const cvApi = {
  upload(file: File): Promise<CVUploadResponse> {
    const form = new FormData();
    form.append('file', file);
    return request<CVUploadResponse>('/cv/upload', { method: 'POST', body: form });
  },
  list: (limit = 25) => get<{ items: CVListItem[]; count: number }>(`/cv?limit=${limit}`),
  get: (id: string) => get<CVUploadResponse>(`/cv/${id}`),
  text: (id: string) =>
    get<{ cv_id: string; filename: string; char_count: number; text: string }>(`/cv/${id}/text`),
  remove: (id: string) => del<{ deleted: boolean }>(`/cv/${id}`),
  limits: () =>
    get<{
      max_upload_bytes: number;
      max_upload_mb: number;
      allowed_suffixes: string[];
      max_cv_characters: number;
      notes: string[];
    }>('/cv/limits'),
};

/* ====================================================== Module 2: roles ==== */

export interface RoleAnalysisInput {
  role_title: string;
  location?: string;
  seniority?: string;
  use_scraping?: boolean;
  use_llm?: boolean;
  max_postings?: number;
}

export const roleApi = {
  analyse: (input: RoleAnalysisInput) => post<RoleAnalysisResponse>('/roles/analyse', input),
  list: (limit = 25) => get<{ items: RoleListItem[]; count: number }>(`/roles?limit=${limit}`),
  get: (id: string) =>
    get<{
      role_analysis_id: string;
      role_title: string;
      location: string;
      seniority: string;
      requirements: RoleRequirements;
      source_reports: RoleRequirements['source_reports'];
      llm_raw: Record<string, unknown>;
      created_at: string;
    }>(`/roles/${id}`),
  postings: (id: string) =>
    get<{ role_analysis_id: string; postings: RoleRequirements['postings']; count: number }>(
      `/roles/${id}/postings`,
    ),
  sources: () =>
    get<{
      sources: Array<{ name: string; source_type: string; homepage: string; attribution: string }>;
      cache: { entries: number; size_bytes: number; ttl_seconds: number; directory: string };
      compliance: Record<string, string>;
    }>('/roles/sources'),
  sourcesHealth: () =>
    get<{
      sources: Array<{
        name: string;
        source_type: string;
        reachable: boolean;
        status: string;
        http_status?: number;
        detail: string;
        elapsed_ms: number;
        robots?: string;
      }>;
      reachable: number;
      total: number;
    }>('/roles/sources/health'),
  clearCache: () => del<{ cleared: number }>('/roles/cache'),
  remove: (id: string) => del<{ deleted: boolean }>(`/roles/${id}`),
};

/* ================================================== Module 3 & 4: gap ====== */

export const gapApi = {
  analyse: (cvId: string, roleAnalysisId: string, withAdvice = true) =>
    post<GapResponse>('/gap/analyse', {
      cv_id: cvId,
      role_analysis_id: roleAnalysisId,
      with_advice: withAdvice,
    }),
  list: (limit = 25) =>
    get<{
      items: Array<{
        gap_analysis_id: string;
        cv_id: string;
        cv_filename: string;
        role_analysis_id: string;
        role_title: string;
        match_percent: number;
        created_at: string;
      }>;
      count: number;
    }>(`/gap?limit=${limit}`),
  get: (id: string) => get<GapResponse>(`/gap/${id}`),
};

export const improveApi = {
  bullets: (bullets: string[], roleTitle = '', cvId = '') =>
    post<ImproveResponse>('/improve/bullets', { bullets, role_title: roleTitle, cv_id: cvId }),
  rank: (bullets: string[]) =>
    post<{ ranking: Array<{ index: number; text: string; weakness_signals: string[]; weakness_score: number; word_count: number }> }>(
      '/improve/rank',
      { bullets },
    ),
  decide: (id: string, decision: 'accepted' | 'rejected' | 'pending') =>
    post<{ id: string; decision: string }>(`/improve/bullets/${id}/decision`, { decision }),
  history: (cvId = '', limit = 100) =>
    get<{ items: Array<Record<string, unknown>>; count: number }>(
      `/improve/history?cv_id=${encodeURIComponent(cvId)}&limit=${limit}`,
    ),
};

/* ============================================= Module 5 & 6: interview ===== */

export interface StartInterviewInput {
  role_title: string;
  difficulty?: 'easy' | 'medium' | 'hard';
  mode?: 'voice' | 'text';
  cv_id?: string;
  role_analysis_id?: string;
}

export const interviewApi = {
  rubric: (difficulty = 'medium') => get<Rubric>(`/interview/rubric?difficulty=${difficulty}`),
  stages: (difficulty = 'medium') =>
    get<{ stages: Omit<StageInfo, 'status'>[]; difficulty: string }>(
      `/interview/stages?difficulty=${difficulty}`,
    ),
  speechHealth: () =>
    get<{ stt: SpeechDescribe; tts: SpeechDescribe; voice_ready: boolean; note: string }>(
      '/interview/speech/health',
    ),
  warmUp: () =>
    post<{
      stt: { loaded: boolean; model_size?: string; load_ms?: number; detail?: string };
      tts: { ready: boolean; engine?: string; voice?: string; processing_ms?: number; detail?: string };
    }>('/interview/speech/warmup'),

  start: (input: StartInterviewInput) =>
    post<{
      interview: Interview;
      rubric: Rubric;
      stages: Omit<StageInfo, 'status'>[];
      has_cv: boolean;
      has_role_requirements: boolean;
      speech: { stt: SpeechDescribe; tts: SpeechDescribe } | null;
    }>('/interview/start', input),

  list: (limit = 25) =>
    get<{
      items: Array<{
        id: string;
        role_title: string;
        difficulty: string;
        mode: string;
        stage: string;
        status: string;
        started_at: string;
        ended_at: string;
        total_questions: number;
        has_report: boolean;
        overall_score: number | null;
      }>;
      count: number;
    }>(`/interview?limit=${limit}`),

  get: (id: string) =>
    get<{
      interview: Interview;
      turns: InterviewTurn[];
      rubric: Rubric;
      performance: InterviewMetrics;
      has_report: boolean;
    }>(`/interview/${id}`),

  end: (id: string) => post<{ interview: Interview }>(`/interview/${id}/end`),
  score: (id: string) => post<InterviewReport>(`/interview/${id}/score`),
  report: (id: string) =>
    get<{ available: boolean; report?: InterviewReport; message?: string }>(`/interview/${id}/report`),
  transcript: (id: string) =>
    get<{
      interview_id: string;
      role_title: string;
      difficulty: string;
      turns: InterviewTurn[];
      plain_text: string;
    }>(`/interview/${id}/transcript`),

  transcribeOnly(blob: Blob): Promise<TranscriptionInfo & { text: string }> {
    const form = new FormData();
    form.append('audio', blob, 'recording.webm');
    return request('/interview/transcribe', { method: 'POST', body: form });
  },

  speak(text: string, voice = ''): Promise<Blob> {
    return fetch(`${BASE}/interview/speak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice }),
    }).then(async (response) => {
      if (!response.ok) throw await toFailure(response);
      return response.blob();
    });
  },
};

/* ================================================ SSE turn streaming ======= */

export interface StreamOptions {
  onEvent: (event: TurnEvent) => void;
  signal?: AbortSignal;
}

/**
 * POST a turn and consume the SSE response.
 *
 * `fetch` is used rather than `EventSource` because EventSource cannot issue a
 * POST, and a turn has to carry either the recorded audio or the typed answer.
 */
async function consumeStream(response: Response, { onEvent }: StreamOptions): Promise<void> {
  if (!response.ok) throw await toFailure(response);
  if (!response.body) throw new ApiFailure('The server sent no response body.', 'empty_stream');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      const payload = frame
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim())
        .join('');

      if (payload) {
        try {
          onEvent(JSON.parse(payload) as TurnEvent);
        } catch {
          /* ignore a partial/garbled frame rather than killing the turn */
        }
      }
      boundary = buffer.indexOf('\n\n');
    }
  }
}

export async function streamTextTurn(
  interviewId: string,
  text: string,
  speak: boolean,
  options: StreamOptions,
): Promise<void> {
  const response = await fetch(`${BASE}/interview/${interviewId}/turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, speak }),
    signal: options.signal,
  });
  await consumeStream(response, options);
}

export async function streamVoiceTurn(
  interviewId: string,
  audio: Blob,
  speak: boolean,
  options: StreamOptions,
): Promise<void> {
  const form = new FormData();
  form.append('audio', audio, 'recording.webm');
  form.append('speak', String(speak));

  const response = await fetch(`${BASE}/interview/${interviewId}/voice-turn`, {
    method: 'POST',
    body: form,
    signal: options.signal,
  });
  await consumeStream(response, options);
}

/* ====================================================== Module 7: metrics == */

export const metricsApi = {
  overview: (voiceOnly = false) => get<MetricsOverview>(`/metrics?voice_only=${voiceOnly}`),
  forInterview: (id: string) => get<InterviewMetrics>(`/metrics/interview/${id}`),
  exportUrl: () => `${BASE}/metrics/export`,
  exportCsvUrl: () => `${BASE}/metrics/export.csv`,
  clear: () => del<{ cleared: number }>('/metrics'),
};

/* ========================================================== System ========= */

export const systemApi = {
  health: (deep = false) => get<HealthResponse>(`/system/health?deep=${deep}`),
  dashboard: () => get<DashboardResponse>('/system/dashboard'),
  settings: () => get<SettingsResponse>('/system/settings'),
  updateSettings: (changes: Record<string, unknown>) =>
    patch<{ updated: Record<string, unknown>; message: string; llm: Record<string, unknown> }>(
      '/system/settings',
      changes,
    ),
  taxonomy: () =>
    get<{
      stats: { canonical_skills: number; alias_entries: number; categories: number; implication_edges: number };
      categories: string[];
      skills: Array<{ canonical: string; category: string; aliases: string[]; implies: string[] }>;
    }>('/system/taxonomy'),
  normalise: (skills: string | string[]) =>
    post<{
      input: string[];
      input_count: number;
      output: Array<{ canonical: string; category: string; surface_forms: string[]; stage: string; confidence: number }>;
      output_count: number;
      merge_evidence: Array<{ canonical: string; variants: string[]; stage: string; confidence: number }>;
      lookup_keys: Record<string, string>;
    }>('/system/normalise', { skills }),
  storage: () =>
    get<{
      path: string;
      size_bytes: number;
      row_counts: Record<string, number>;
      scrape_cache: { entries: number; size_bytes: number };
      model_cache: { path: string; exists: boolean; size_bytes: number; files: number };
    }>('/system/storage'),
  clearStorage: () =>
    del<{
      cleared: boolean;
      rows_before: Record<string, number>;
      rows_after: Record<string, number>;
      scrape_cache_entries_cleared: number;
      note: string;
    }>('/system/storage'),
};

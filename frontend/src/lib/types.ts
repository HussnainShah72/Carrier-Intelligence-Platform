/**
 * Shared types mirroring the backend payloads.
 *
 * Hand-written rather than generated: the surface is small enough that an
 * explicit contract is clearer than a build step, and it documents what each
 * screen is allowed to rely on.
 */

/* ------------------------------------------------------------------ Module 1 */

export interface NormalisedSkill {
  canonical: string;
  category: string;
  surface_forms: string[];
  stage: string;
  confidence: number;
  in_taxonomy: boolean;
  matched_against: string;
}

export interface EducationEntry {
  degree: string;
  field: string;
  institution: string;
  start: string;
  end: string;
  grade: string;
}

export interface ExperienceEntry {
  job_title: string;
  company: string;
  location: string;
  start: string;
  end: string;
  bullets: string[];
}

export interface ProjectEntry {
  name: string;
  description: string;
  technologies: string[];
  link: string;
}

export interface CertificationEntry {
  name: string;
  issuer: string;
  year: string;
}

export interface RejectedClaim {
  field: string;
  value: string;
  reason: string;
}

export interface CVProfile {
  full_name: string;
  email: string;
  phone: string;
  location: string;
  links: string[];
  headline: string;
  total_years_experience: number | null;
  skills: NormalisedSkill[];
  education: EducationEntry[];
  experience: ExperienceEntry[];
  projects: ProjectEntry[];
  certifications: CertificationEntry[];
  languages: string[];
  job_roles: string[];
  all_bullets: string[];
  sections_found: string[];
  rejected_claims: RejectedClaim[];
  parse_mode: string;
  warnings: string[];
  skill_count: number;
}

export interface BulletRank {
  index: number;
  text: string;
  weakness_signals: string[];
  weakness_score: number;
  word_count: number;
}

export interface CVUploadResponse {
  cv_id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  char_count: number;
  page_count: number;
  extractor: string;
  extraction_warnings: string[];
  profile: CVProfile;
  bullet_ranking: BulletRank[];
  llm_usage: LLMUsage | null;
  created_at: string;
}

export interface CVListItem {
  cv_id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  char_count: number;
  parse_mode: string;
  created_at: string;
  full_name: string;
  skill_count: number;
  experience_count: number;
  project_count: number;
}

export interface LLMUsage {
  provider: string;
  model: string;
  prompt_chars: number;
  completion_chars: number;
  total_ms: number;
  ttft_ms: number | null;
  degraded: boolean;
}

/* ------------------------------------------------------------------ Module 2 */

export type Provenance = 'scraped' | 'llm' | 'both';

export interface CombinedSkill {
  canonical: string;
  category: string;
  provenance: Provenance;
  importance: number;
  posting_count: number;
  posting_frequency: number;
  llm_tiers: string[];
  surface_forms: string[];
  example_sources: string[];
  normalisation_stage: string;
  essential: boolean;
}

export interface JobPosting {
  source: string;
  source_type: string;
  title: string;
  company: string;
  location: string;
  url: string;
  posted_at: string;
  description: string;
  description_excerpt: string;
  tags: string[];
  skills: string[];
}

export interface SourceReport {
  name: string;
  source_type: string;
  url: string;
  status: string;
  postings_found: number;
  postings_kept: number;
  elapsed_ms: number;
  from_cache: boolean;
  detail: string;
  attribution: string;
}

export interface RoleStats {
  total_skills: number;
  from_scraping_only: number;
  from_llm_only: number;
  confirmed_by_both: number;
  essential_skills: number;
  postings_collected: number;
  sources_attempted: number;
  sources_succeeded: number;
  agreement_rate: number;
  dropped_uncorroborated: number;
}

export interface RequirementFiltering {
  candidates_considered: number;
  requirements_kept: number;
  dropped_uncorroborated: number;
  min_posting_support: number;
  max_requirements: number;
  dropped_examples: string[];
  rule: string;
}

export interface RoleRequirements {
  role_title: string;
  normalised_title: string;
  title_assessment: string;
  seniority: string;
  role_summary: string;
  responsibilities: string[];
  interview_focus_areas: string[];
  combined_skills: CombinedSkill[];
  postings: JobPosting[];
  source_reports: SourceReport[];
  merge_evidence: Array<{
    canonical: string;
    variants: string[];
    stage: string;
    provenance: string;
    posting_count: number;
  }>;
  filtering: RequirementFiltering;
  warnings: string[];
  timings: Record<string, number>;
  llm_available: boolean;
  llm_degraded: boolean;
  stats: RoleStats;
  core_technical_skills: string[];
  desirable_technical_skills: string[];
  soft_skills: string[];
  qualifications: string[];
  tools_and_platforms: string[];
}

export interface RoleAnalysisResponse {
  role_analysis_id: string;
  requirements: RoleRequirements;
  llm_usage: {
    calls: number;
    total_ms: number;
    providers: string[];
    models: string[];
    degraded: boolean;
  };
  created_at: string;
}

export interface RoleListItem {
  role_analysis_id: string;
  role_title: string;
  location: string;
  seniority: string;
  stats: Partial<RoleStats>;
  created_at: string;
}

/* ------------------------------------------------------------------ Module 3 */

export type MatchStatus = 'matched' | 'partial' | 'missing';
export type Severity = 'critical' | 'high' | 'medium' | 'low';

export interface SkillComparison {
  requirement: string;
  category: string;
  status: MatchStatus;
  importance: number;
  provenance: Provenance;
  posting_count: number;
  essential: boolean;
  credit: number;
  severity: Severity;
  evidence: string;
  matched_via: string;
  cv_skill: string;
  confidence: number;
}

export interface CategoryBreakdown {
  category: string;
  matched: number;
  partial: number;
  missing: number;
  total: number;
  coverage_percent: number;
}

export interface GapAdvice {
  available: boolean;
  detail?: string;
  headline?: string;
  priority_gaps?: Array<{
    skill: string;
    why_it_matters: string;
    how_to_close: string;
    estimated_effort: string;
  }>;
  quick_wins?: string[];
  strengths_to_lead_with?: string[];
  learning_sequence?: string[];
  caveat?: string;
  filtered_out?: number;
}

export interface GapResult {
  role_title: string;
  match_percent: number;
  unweighted_percent: number;
  readiness_label: string;
  comparisons: SkillComparison[];
  matched: SkillComparison[];
  partial: SkillComparison[];
  missing: SkillComparison[];
  priority_gaps: SkillComparison[];
  extra_skills: Array<{ canonical: string; category: string }>;
  category_breakdown: CategoryBreakdown[];
  essential_coverage: {
    total: number;
    matched: number;
    partial: number;
    missing: number;
    coverage_percent: number;
    missing_names: string[];
  };
  advice: GapAdvice;
  warnings: string[];
  stats: {
    requirements_total: number;
    matched: number;
    partial: number;
    missing: number;
    extra_skills: number;
  };
  disclaimer: string;
}

export interface GapResponse {
  gap_analysis_id: string;
  cv_id: string;
  cv_filename: string;
  role_analysis_id: string;
  role_title: string;
  result: GapResult;
  created_at: string;
}

/* ------------------------------------------------------------------ Module 4 */

export interface BulletFlag {
  type: string;
  severity: 'blocking' | 'warning';
  detail: string;
}

export interface BulletImprovement {
  id: string;
  original: string;
  improved: string;
  explanation: string;
  changes: string[];
  flags: BulletFlag[];
  accepted: boolean;
  rejection_reason: string;
  already_strong: boolean;
  metrics_preserved: string[];
  weakness_signals: string[];
  decision: 'pending' | 'accepted' | 'rejected';
  word_count_before: number;
  word_count_after: number;
}

export interface ImproveResponse {
  results: BulletImprovement[];
  summary: {
    requested: number;
    returned_by_model: number;
    accepted: number;
    rejected: number;
    already_strong: number;
    with_warnings: number;
    rejections_by_reason: Record<string, number>;
    elapsed_ms: number;
    engine: string;
    degraded: boolean;
    guard_note: string;
  };
  llm_usage: LLMUsage | null;
}

/* ------------------------------------------------------------------ Module 5 */

export type Difficulty = 'easy' | 'medium' | 'hard';
export type InterviewMode = 'voice' | 'text';

export interface StageInfo {
  key: string;
  name: string;
  goal: string;
  budget: number;
  scored: boolean;
  status: 'done' | 'active' | 'pending';
}

export interface InterviewProgress {
  stage: string;
  stage_name: string;
  stage_index: number;
  stage_total: number;
  stage_question_count: number;
  stage_budget: number;
  total_questions: number;
  percent: number;
  effective_difficulty: string;
  stages: StageInfo[];
}

export interface InterviewPlan {
  interviewer_name: string;
  interviewer_persona: string;
  opening_line_hint: string;
  cv_talking_points: string[];
  technical_topics: string[];
  behavioural_themes: string[];
  gap_probes: string[];
  red_flag_checks: string[];
  rubric_version: string;
  llm_degraded: boolean;
}

export interface Interview {
  id: string;
  role_title: string;
  cv_id: string;
  difficulty: Difficulty;
  mode: InterviewMode;
  stage: string;
  status: 'active' | 'complete' | 'abandoned';
  plan: InterviewPlan;
  progress: InterviewProgress;
  started_at: string;
  ended_at: string;
}

export interface TurnTimings {
  stt_ms: number | null;
  llm_ttft_ms: number | null;
  llm_total_ms: number | null;
  tts_first_ms: number | null;
  tts_total_ms: number | null;
  e2e_first_audio_ms: number | null;
  total_ms: number | null;
  audio_seconds: number | null;
  chars_out: number;
  tts_engine: string;
  stt_engine: string;
  llm_provider: string;
  llm_model: string;
}

export interface AnswerAnalysis {
  word_count: number;
  quality_score: number;
  quality_band: 'weak' | 'adequate' | 'strong';
  specificity_hits: number;
  structure_hits: number;
  hedge_hits: number;
  metric_hits: number;
  first_person: boolean;
  team_only: boolean;
  is_non_answer: boolean;
  is_question: boolean;
  skills_mentioned: string[];
  role_skills_mentioned: string[];
  salient_terms: string[];
  signals: string[];
}

export interface TranscriptionInfo {
  text: string;
  language: string;
  duration_seconds: number;
  processing_ms: number;
  real_time_factor: number;
  avg_logprob: number;
  no_speech_prob: number;
  confidence: 'none' | 'low' | 'medium' | 'high' | 'unknown';
  segment_count: number;
  engine: string;
  model_size: string;
  warnings: string[];
  has_speech: boolean;
}

export interface InterviewTurn {
  id: string;
  turn_index: number;
  speaker: 'interviewer' | 'candidate';
  stage: string;
  text: string;
  meta: {
    analysis?: AnswerAnalysis;
    timings?: TurnTimings;
    follow_up?: boolean;
    effective_difficulty?: string;
    stt_ms?: number;
    stt_engine?: string;
    audio_seconds?: number;
  };
  created_at: string;
}

/** One Server-Sent Event from a turn. */
export type TurnEvent =
  | { type: 'transcript'; text: string; stt: TranscriptionInfo }
  | { type: 'no_speech'; message: string; stt: TranscriptionInfo }
  | { type: 'analysis'; analysis: AnswerAnalysis }
  | { type: 'stage'; stage: string; stage_name: string; previous_stage: string; progress: InterviewProgress }
  | { type: 'text'; delta: string }
  | {
      type: 'audio';
      index: number;
      text: string;
      audio_base64: string;
      mime: string;
      engine: string;
      voice: string;
      audio_seconds: number;
      synthesis_ms: number;
      since_speech_end_ms: number;
    }
  | { type: 'tts_error'; message: string; text: string }
  | { type: 'metrics'; timings: TurnTimings }
  | {
      type: 'done';
      finished: boolean;
      reply: string;
      stage: string;
      turn_index?: number;
      progress: InterviewProgress;
      timings?: TurnTimings;
      effective_difficulty?: string;
      follow_up?: boolean;
      audio_chunks?: number;
      message?: string;
    }
  | { type: 'error'; code: string; message: string; fallback?: string; stage?: string };

/* ------------------------------------------------------------------ Module 6 */

export interface RubricCategory {
  key: string;
  name: string;
  description: string;
  what_good_looks_like: string;
  weight: number;
  weight_percent: number;
}

export interface Rubric {
  version: string;
  difficulty: string;
  scale: Array<{ score: number; label: string; descriptor: string }>;
  categories: RubricCategory[];
  overall_bands: Array<{ min: number; label: string; summary: string }>;
  calibration_rules?: string[];
  disclaimer: string;
  defined_in_advance: boolean;
  note: string;
}

export interface CategoryScore {
  key: string;
  name: string;
  description: string;
  weight: number;
  weight_percent: number;
  score: number | null;
  score_label: string;
  justification: string;
  evidence_quote: string;
}

export interface InterviewReport {
  interview_id: string;
  role_title: string;
  difficulty: Difficulty;
  mode: InterviewMode;
  started_at: string;
  ended_at: string;
  rubric: Rubric;
  overall_score: number | null;
  overall_out_of: number;
  overall_percent: number | null;
  overall_band: string;
  overall_band_summary: string;
  categories_scored: number;
  categories_not_tested: string[];
  category_scores: CategoryScore[];
  strengths: string[];
  weaknesses: string[];
  answers_to_improve: Array<{
    question: string;
    candidate_answer_summary: string;
    why_it_fell_short: string;
    stronger_answer_outline: string;
  }>;
  recommended_topics: string[];
  improvement_plan: Array<{ timeframe: string; focus: string; actions: string[] }>;
  overall_comment: string;
  transcript: InterviewTurn[];
  transcript_stats: {
    total_turns: number;
    interviewer_questions: number;
    candidate_answers: number;
    candidate_total_words: number;
    candidate_mean_words: number;
    shortest_answer_words: number;
    longest_answer_words: number;
  };
  stage_history: Array<{ stage: string; questions: number; ended_at: string }>;
  stages_completed: string[];
  demonstrated_skills: string[];
  answer_quality_series: number[];
  performance: InterviewMetrics;
  assessor: { engine: string; degraded: boolean; note: string };
  disclaimer: string;
  scoring_ms: number;
}

/* ------------------------------------------------------------------ Module 7 */

export interface MetricSummary {
  samples: number;
  mean_ms: number | null;
  median_ms: number | null;
  p90_ms: number | null;
  min_ms: number | null;
  max_ms: number | null;
}

export type MetricField =
  | 'stt_ms'
  | 'llm_ttft_ms'
  | 'llm_total_ms'
  | 'tts_first_ms'
  | 'tts_total_ms'
  | 'e2e_first_audio_ms'
  | 'total_ms';

export interface InterviewMetrics {
  interview_id: string;
  turns: Array<{ turn_index: number } & Partial<Record<MetricField, number | null>> & {
    audio_seconds: number | null;
    chars_out: number;
    stt_engine: string;
    tts_engine: string;
    llm_provider: string;
    llm_model: string;
    mode: string;
  }>;
  aggregates: Record<MetricField, MetricSummary>;
  engines: { stt: string[]; tts: string[]; llm_providers: string[]; llm_models: string[] };
  metric_labels: Record<string, string>;
  headline_metric: MetricField;
  voice_turns: number;
  text_turns: number;
}

export interface GlobalMetrics {
  total_turns: number;
  total_interviews: number;
  roles_tested: number;
  aggregates: Record<MetricField, MetricSummary>;
  by_role: Array<{
    role_title: string;
    turns: number;
    interviews: number;
    aggregates: Record<MetricField, MetricSummary>;
  }>;
  engines: { stt: string[]; tts: string[]; llm_providers: string[]; llm_models: string[] };
  metric_labels: Record<string, string>;
  headline_metric: MetricField;
  meets_three_role_requirement: boolean;
  notes: string[];
}

export interface MetricsOverview {
  summary: GlobalMetrics;
  timeline: Array<{
    index: number;
    role_title: string;
    e2e_first_audio_ms: number | null;
    llm_ttft_ms: number | null;
    stt_ms: number | null;
    tts_first_ms: number | null;
    total_ms: number | null;
    created_at: string;
  }>;
  stage_breakdown: Array<{ stage: string; mean_ms: number }>;
}

/* ------------------------------------------------------------------- System */

export interface SpeechDescribe {
  engine?: string;
  runs_locally: boolean;
  installed?: boolean;
  enabled: boolean;
  model_size?: string;
  loaded_model?: string | null;
  device?: string;
  compute_type?: string;
  beam_size?: number;
  model_cache?: string;
  load_ms?: number | null;
  last_error?: string | null;
  available_sizes?: string[];
  configured_engine?: string;
  active_engine?: string;
  piper?: {
    installed: boolean;
    voices_on_disk: Array<{ name: string; model_path: string; has_config: boolean; size_bytes: number; ready: boolean }>;
    voice_dir: string;
    selected_voice: string;
    loaded_voice: string | null;
    load_ms: number | null;
    last_error: string | null;
    download_hint: string;
  };
  sapi?: { installed: boolean; note: string; last_error: string | null };
  sample_rate?: number;
  speed?: number;
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  app: string;
  version: string;
  uptime_seconds: number;
  environment: string;
  components: {
    database: { ok: boolean; schema_version?: string; path?: string; size_bytes?: number; row_counts?: Record<string, number>; detail?: string };
    llm: { provider: string; model: string; streaming: boolean; degraded: boolean; reachable: boolean | null; latency_ms?: number; detail?: string };
    speech_recognition: SpeechDescribe;
    text_to_speech: SpeechDescribe;
    job_sources: { checked: boolean; configured?: number; enabled?: boolean; results?: Array<Record<string, unknown>> };
    skill_taxonomy: { canonical_skills: number; alias_entries: number; categories: number; implication_edges: number };
    scrape_cache: { entries: number; size_bytes: number; ttl_seconds: number; directory: string };
  };
  degradations: string[];
  runtime: { python: string; platform: string; machine: string };
  privacy: Record<string, string>;
}

export interface DashboardResponse {
  latest_cv: {
    cv_id: string;
    filename: string;
    created_at: string;
    full_name: string;
    headline: string;
    skill_count: number;
    experience_count: number;
    project_count: number;
    education_count: number;
    certification_count: number;
    top_skills: string[];
    warnings: string[];
  } | null;
  cv_count: number;
  recent_gaps: Array<{
    gap_analysis_id: string;
    role_title: string;
    match_percent: number;
    matched: number;
    partial: number;
    missing: number;
    created_at: string;
  }>;
  recent_interviews: Array<{
    interview_id: string;
    role_title: string;
    difficulty: string;
    status: string;
    started_at: string;
    overall_score: number | null;
    overall_band: string | null;
  }>;
  recent_roles: RoleListItem[];
  activity: Array<{ kind: string; title: string; detail: string; ref_id: string; created_at: string }>;
  counts: Record<string, number>;
  performance: GlobalMetrics;
  preparation_progress: {
    steps: Array<{ key: string; label: string; done: boolean; href: string }>;
    completed: number;
    total: number;
    percent: number;
    best_match_percent: number;
    best_interview_score: number | null;
    interviews_completed: number;
  };
  engine_status: {
    llm: { provider: string; model: string; streaming: boolean; degraded: boolean; temperature: number };
    stt_ready: boolean;
    tts_engine: string;
    scraping_enabled: boolean;
  };
}

export interface SettingsResponse {
  llm: {
    provider: string;
    model: string;
    fast_model: string;
    temperature: number;
    max_tokens: number;
    configured: boolean;
    available_providers: string[];
    keys_present: Record<string, boolean>;
    ollama_base_url: string;
  };
  speech: { stt: SpeechDescribe; tts: SpeechDescribe };
  scraping: {
    enabled: boolean;
    max_postings: number;
    per_source_limit: number;
    min_interval_seconds: number;
    cache_ttl_seconds: number;
    user_agent: string;
    sources: Array<{ name: string; source_type: string; homepage: string; attribution: string }>;
  };
  uploads: { max_bytes: number; allowed_suffixes: string[]; max_cv_characters: number };
  rubric: Rubric;
  storage: { path: string; size_bytes: number; row_counts: Record<string, number> };
  writable: string[];
  env_file: string;
  env_file_exists: boolean;
  note: string;
}

export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
}

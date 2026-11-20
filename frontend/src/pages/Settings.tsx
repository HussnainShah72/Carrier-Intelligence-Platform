/**
 * Page 9 - Settings.
 *
 * Model configuration, privacy controls, storage management and system health.
 * Two things are deliberate here:
 *   - API keys are never shown, only reported as present or absent, and they
 *     can only be set in backend/.env by hand.
 *   - The skill-normalisation playground is on this page because it is the
 *     clearest single demonstration that "React"/"ReactJS"/"React.js" really do
 *     collapse to one skill, and which stage of the cascade decided it.
 */

import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  Database,
  Globe,
  HardDrive,
  Info,
  Key,
  Layers,
  Lock,
  Mic,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  Volume2,
  XCircle,
} from 'lucide-react';
import { useCallback, useState } from 'react';

import {
  Badge,
  Button,
  Card,
  CardHeader,
  Collapsible,
  ErrorState,
  Field,
  Loading,
  Modal,
  Notice,
  PageHeader,
  Select,
  StatTile,
  Table,
  Td,
  Toggle,
} from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { ApiFailure, roleApi, systemApi } from '../lib/api';
import { bytes, ms, titleCase } from '../lib/format';
import { useApp } from '../lib/store';

const PROVIDER_LABELS: Record<string, string> = {
  ollama: 'Ollama — a model running locally (no API key, nothing leaves this machine)',
  offline: 'Offline — deterministic rules, no language model at all',
  anthropic: 'Anthropic Claude API (needs ANTHROPIC_API_KEY)',
  openai: 'OpenAI API (needs OPENAI_API_KEY)',
  gemini: 'Google Gemini API (needs GEMINI_API_KEY)',
  groq: 'Groq API (needs GROQ_API_KEY)',
};

export default function SettingsPage() {
  const { notify } = useApp();

  const settings = useAsync(() => systemApi.settings(), []);
  const health = useAsync(() => systemApi.health(false), []);
  const storage = useAsync(() => systemApi.storage(), []);

  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [deepChecking, setDeepChecking] = useState(false);
  const [deepResult, setDeepResult] = useState<Awaited<ReturnType<typeof systemApi.health>> | null>(null);
  const [sourceResult, setSourceResult] = useState<Awaited<ReturnType<typeof roleApi.sourcesHealth>> | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearing, setClearing] = useState(false);

  // normalisation playground
  const [probe, setProbe] = useState('React, ReactJS, React.js, Node.js, NodeJS, Postgres, PostgreSQL, k8s, Kubernetes');
  const [probeResult, setProbeResult] = useState<Awaited<ReturnType<typeof systemApi.normalise>> | null>(null);
  const [probing, setProbing] = useState(false);

  const value = useCallback(
    <T,>(key: string, current: T): T => (key in draft ? (draft[key] as T) : current),
    [draft],
  );

  const set = useCallback((key: string, next: unknown) => {
    setDraft((current) => ({ ...current, [key]: next }));
  }, []);

  const save = useCallback(async () => {
    if (!Object.keys(draft).length) return;
    setSaving(true);
    try {
      const result = await systemApi.updateSettings(draft);
      notify({ tone: 'ok', title: 'Settings saved', message: result.message });
      setDraft({});
      settings.reload();
      health.reload();
    } catch (caught: unknown) {
      notify({
        tone: 'danger',
        title: 'Could not save settings',
        message: caught instanceof ApiFailure ? caught.message : undefined,
      });
    } finally {
      setSaving(false);
    }
  }, [draft, notify, settings, health]);

  const runDeepCheck = useCallback(async () => {
    setDeepChecking(true);
    setDeepResult(null);
    setSourceResult(null);
    try {
      const [healthResult, sources] = await Promise.all([
        systemApi.health(true),
        roleApi.sourcesHealth(),
      ]);
      setDeepResult(healthResult);
      setSourceResult(sources);
      notify({
        tone: healthResult.status === 'ok' ? 'ok' : 'warn',
        title: `System check: ${healthResult.status}`,
        message: `${sources.reachable} of ${sources.total} job sources reachable.`,
      });
    } catch (caught: unknown) {
      notify({
        tone: 'danger',
        title: 'System check failed',
        message: caught instanceof ApiFailure ? caught.message : undefined,
      });
    } finally {
      setDeepChecking(false);
    }
  }, [notify]);

  const runProbe = useCallback(async () => {
    setProbing(true);
    try {
      setProbeResult(await systemApi.normalise(probe));
    } catch {
      notify({ tone: 'danger', title: 'Could not run the normaliser' });
    } finally {
      setProbing(false);
    }
  }, [probe, notify]);

  const clearAll = useCallback(async () => {
    setClearing(true);
    try {
      const result = await systemApi.clearStorage();
      notify({
        tone: 'ok',
        title: 'All stored data deleted',
        message: `${Object.values(result.rows_before).reduce((a, b) => a + b, 0)} records removed. ${result.note}`,
      });
      setConfirmClear(false);
      storage.reload();
      settings.reload();
    } catch (caught: unknown) {
      notify({
        tone: 'danger',
        title: 'Could not clear storage',
        message: caught instanceof ApiFailure ? caught.message : undefined,
      });
    } finally {
      setClearing(false);
    }
  }, [notify, storage, settings]);

  if (settings.loading) return <Loading label="Loading settings…" />;
  if (settings.error || !settings.data) {
    return <ErrorState title="Could not load settings" message={settings.error ?? undefined} onRetry={settings.reload} />;
  }

  const data = settings.data;
  const dirty = Object.keys(draft).length > 0;
  const shownHealth = deepResult ?? health.data;

  return (
    <>
      <PageHeader
        title="Settings"
        description="Model configuration, local speech engines, privacy controls, storage management and system health checks."
        actions={
          <>
            <Button variant="secondary" icon={RefreshCw} loading={deepChecking} onClick={() => void runDeepCheck()}>
              Run system check
            </Button>
            <Button variant="primary" icon={Save} loading={saving} disabled={!dirty} onClick={() => void save()}>
              {dirty ? `Save ${Object.keys(draft).length} change${Object.keys(draft).length === 1 ? '' : 's'}` : 'Saved'}
            </Button>
          </>
        }
      />

      {shownHealth && shownHealth.degradations.length > 0 && (
        <Notice tone="warn" title={`${shownHealth.degradations.length} degradation(s) detected`} className="mb-6">
          <ul className="mt-1 space-y-1">
            {shownHealth.degradations.map((item, index) => (
              <li key={index} className="flex gap-1.5">
                <span aria-hidden>·</span>
                {item}
              </li>
            ))}
          </ul>
        </Notice>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        {/* ------------------------------------------------------- LLM -- */}
        <Card>
          <CardHeader
            title="Language model"
            subtitle="Used for CV parsing, role skills, rewriting, interview questions and scoring"
            icon={Brain}
            actions={
              <Badge tone={data.llm.provider === 'offline' ? 'warn' : data.llm.configured ? 'ok' : 'danger'}>
                {data.llm.provider}
              </Badge>
            }
          />
          <div className="card-pad space-y-4">
            <Field label="Provider" hint="Changing this takes effect on the next request">
              <Select
                value={value('llm_provider', data.llm.provider)}
                onChange={(next) => set('llm_provider', next)}
                ariaLabel="LLM provider"
                options={data.llm.available_providers.map((provider) => ({
                  value: provider,
                  label: PROVIDER_LABELS[provider] ?? provider,
                }))}
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Main model" hint="Heavy JSON tasks">
                <input
                  value={String(value('llm_model', data.llm.model))}
                  onChange={(event) => set('llm_model', event.target.value)}
                  className="input mono"
                  placeholder="provider default"
                  maxLength={120}
                />
              </Field>
              <Field label="Fast model" hint="Live interview turns">
                <input
                  value={String(value('llm_fast_model', data.llm.fast_model))}
                  onChange={(event) => set('llm_fast_model', event.target.value)}
                  className="input mono"
                  placeholder="provider default"
                  maxLength={120}
                />
              </Field>
            </div>

            <div>
              <p className="label flex items-center gap-1.5">
                <Key size={12} aria-hidden /> API keys
              </p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(data.llm.keys_present).map(([provider, present]) => (
                  <Badge key={provider} tone={present ? 'ok' : 'neutral'}>
                    {present ? <CheckCircle2 size={10} aria-hidden /> : <XCircle size={10} aria-hidden />}
                    {provider}
                  </Badge>
                ))}
              </div>
              <p className="mt-2 text-xs leading-relaxed text-ink-faint">
                {data.note} To add one, edit <span className="mono">{data.env_file}</span> and restart the
                backend. Keys are never sent to the browser and never committed.
              </p>
            </div>

            {shownHealth?.components.llm.reachable === false && (
              <Notice tone="danger" title="The configured model did not respond">
                {shownHealth.components.llm.detail}
              </Notice>
            )}
            {shownHealth?.components.llm.reachable === true && !shownHealth.components.llm.degraded && (
              <Notice tone="ok">
                Model responded in {ms(shownHealth.components.llm.latency_ms)}.
              </Notice>
            )}
          </div>
        </Card>

        {/* --------------------------------------------- local speech -- */}
        <Card>
          <CardHeader
            title="Local speech engines"
            subtitle="Both run on this machine — no audio is sent anywhere"
            icon={Mic}
            actions={<Badge tone="ok">100% local</Badge>}
          />
          <div className="card-pad space-y-5">
            <div>
              <p className="label flex items-center gap-1.5">
                <Mic size={12} aria-hidden /> Speech recognition (faster-whisper)
              </p>
              <div className="space-y-3">
                <Toggle
                  checked={Boolean(value('stt_enabled', data.speech.stt.enabled))}
                  onChange={(next) => set('stt_enabled', next)}
                  label="Enable speech recognition"
                  description="Turning this off forces the interview into text mode"
                />
                <Field label="Model size" hint="Larger is more accurate but slower on CPU">
                  <Select
                    value={String(value('stt_model_size', data.speech.stt.model_size ?? 'base.en'))}
                    onChange={(next) => set('stt_model_size', next)}
                    ariaLabel="Whisper model size"
                    options={(data.speech.stt.available_sizes ?? ['tiny.en', 'base.en', 'small.en']).map((size) => ({
                      value: size,
                      label:
                        size === 'tiny.en'
                          ? 'tiny.en — ~75 MB, fastest, least accurate'
                          : size === 'base.en'
                            ? 'base.en — ~145 MB, recommended balance'
                            : size === 'small.en'
                              ? 'small.en — ~480 MB, more accurate, slower'
                              : size,
                    }))}
                  />
                </Field>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  {[
                    ['Installed', data.speech.stt.installed ? 'yes' : 'no'],
                    ['Loaded model', data.speech.stt.loaded_model ?? 'not loaded yet'],
                    ['Device', data.speech.stt.device ?? '—'],
                    ['Compute type', data.speech.stt.compute_type ?? '—'],
                  ].map(([label, text]) => (
                    <div key={label} className="flex justify-between gap-2">
                      <dt className="text-ink-muted">{label}</dt>
                      <dd className="mono font-semibold text-ink">{String(text)}</dd>
                    </div>
                  ))}
                </dl>
                {data.speech.stt.last_error && (
                  <Notice tone="danger">{data.speech.stt.last_error}</Notice>
                )}
              </div>
            </div>

            <div className="border-t border-line pt-4">
              <p className="label flex items-center gap-1.5">
                <Volume2 size={12} aria-hidden /> Speech synthesis
              </p>
              <div className="space-y-3">
                <Toggle
                  checked={Boolean(value('tts_enabled', data.speech.tts.enabled))}
                  onChange={(next) => set('tts_enabled', next)}
                  label="Enable speech synthesis"
                  description="Turning this off leaves the interviewer's replies as text"
                />
                <Field label="Engine">
                  <Select
                    value={String(value('tts_engine', data.speech.tts.configured_engine ?? 'auto'))}
                    onChange={(next) => set('tts_engine', next)}
                    ariaLabel="TTS engine"
                    options={[
                      { value: 'auto', label: 'Auto — prefer Piper, fall back to the OS voice' },
                      { value: 'piper', label: 'Piper only — neural, best quality' },
                      { value: 'sapi', label: 'OS voice only — robotic, always available' },
                    ]}
                  />
                </Field>
                {data.speech.tts.piper && data.speech.tts.piper.voices_on_disk.length > 0 && (
                  <Field label="Piper voice">
                    <Select
                      value={String(value('tts_voice', data.speech.tts.piper.selected_voice))}
                      onChange={(next) => set('tts_voice', next)}
                      ariaLabel="Piper voice"
                      options={data.speech.tts.piper.voices_on_disk
                        .filter((voice) => voice.ready)
                        .map((voice) => ({
                          value: voice.name,
                          label: `${voice.name} (${bytes(voice.size_bytes)})`,
                        }))}
                    />
                  </Field>
                )}
                <div className="flex items-center gap-2">
                  <Badge tone={data.speech.tts.active_engine === 'piper' ? 'ok' : 'warn'}>
                    active: {data.speech.tts.active_engine}
                  </Badge>
                  <Badge tone="neutral">
                    {data.speech.tts.piper?.voices_on_disk.filter((v) => v.ready).length ?? 0} voice(s) installed
                  </Badge>
                </div>
                {!data.speech.tts.piper?.voices_on_disk.some((voice) => voice.ready) && (
                  <Notice tone="warn" title="No Piper voice installed">
                    The interviewer will use the operating-system voice, which is much more robotic.
                    Install a neural voice with{' '}
                    <span className="mono">python scripts/download_speech_models.py</span>
                  </Notice>
                )}
              </div>
            </div>
          </div>
        </Card>

        {/* -------------------------------------------------- scraping -- */}
        <Card>
          <CardHeader
            title="Job posting collection"
            subtitle="Which boards are queried and how politely"
            icon={Globe}
          />
          <div className="card-pad space-y-4">
            <Toggle
              checked={Boolean(value('scrape_enabled', data.scraping.enabled))}
              onChange={(next) => set('scrape_enabled', next)}
              label="Collect live job postings"
              description="When off, role requirements come from the language model alone"
            />

            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              {[
                ['Max postings per analysis', data.scraping.max_postings],
                ['Per-source limit', data.scraping.per_source_limit],
                ['Min interval per host', `${data.scraping.min_interval_seconds}s`],
                ['Cache lifetime', `${(data.scraping.cache_ttl_seconds / 3600).toFixed(0)}h`],
              ].map(([label, text]) => (
                <div key={String(label)} className="flex justify-between gap-2">
                  <dt className="text-ink-muted">{label}</dt>
                  <dd className="mono font-semibold text-ink">{String(text)}</dd>
                </div>
              ))}
            </dl>

            <div>
              <p className="label">Sources</p>
              <div className="space-y-1.5">
                {data.scraping.sources.map((source) => {
                  const live = sourceResult?.sources.find((item) => item.name === source.name);
                  return (
                    <div key={source.name} className="flex items-center gap-2 text-[0.8125rem]">
                      {live ? (
                        live.reachable ? (
                          <CheckCircle2 size={13} className="shrink-0 text-[rgb(var(--ok))]" aria-hidden />
                        ) : (
                          <XCircle size={13} className="shrink-0 text-[rgb(var(--danger))]" aria-hidden />
                        )
                      ) : (
                        <span className="h-2 w-2 shrink-0 rounded-full bg-line" aria-hidden />
                      )}
                      <span className="min-w-0 flex-1 truncate font-medium text-ink">{source.name}</span>
                      <Badge tone={source.source_type === 'rss_scrape' ? 'info' : 'neutral'}>
                        {source.source_type === 'rss_scrape' ? 'RSS scrape' : 'JSON API'}
                      </Badge>
                      {live && <span className="mono text-xs text-ink-faint">{ms(live.elapsed_ms)}</span>}
                    </div>
                  );
                })}
              </div>
              {!sourceResult && (
                <p className="mt-2 text-xs text-ink-faint">
                  Run the system check above to test reachability live.
                </p>
              )}
            </div>

            <Collapsible title="User agent sent to every source" className="!border-0 bg-surface-muted">
              <p className="mono break-all text-xs text-ink-muted">{data.scraping.user_agent}</p>
              <p className="mt-2 text-xs leading-relaxed text-ink-muted">
                It identifies this project rather than impersonating a browser. robots.txt is fetched
                and obeyed for every host before any request, and a crawl-delay directive is honoured.
              </p>
            </Collapsible>
          </div>
        </Card>

        {/* -------------------------------------------------- privacy -- */}
        <Card>
          <CardHeader
            title="Privacy"
            subtitle="Where your data goes, and where it does not"
            icon={Lock}
          />
          <div className="card-pad space-y-3">
            {shownHealth &&
              Object.entries(shownHealth.privacy).map(([key, text]) => (
                <div key={key} className="text-[0.8125rem]">
                  <p className="font-semibold text-ink">{titleCase(key)}</p>
                  <p className="leading-relaxed text-ink-muted">{text}</p>
                </div>
              ))}

            <Notice tone="info" className="!mt-4">
              Nothing is uploaded to this project's authors. The only outbound traffic is to the job
              boards listed above and, if you configure a cloud provider, to that provider's API.
              Choosing <span className="font-semibold">ollama</span> or{' '}
              <span className="font-semibold">offline</span> keeps everything on this machine.
            </Notice>
          </div>
        </Card>

        {/* -------------------------------------------------- storage -- */}
        <Card>
          <CardHeader title="Storage" subtitle="Everything is stored locally" icon={HardDrive} />
          <div className="card-pad space-y-4">
            {storage.data && (
              <>
                <div className="grid grid-cols-3 gap-3">
                  <StatTile
                    label="Database"
                    value={bytes(storage.data.size_bytes)}
                    icon={Database}
                    className="!shadow-none"
                  />
                  <StatTile
                    label="Scrape cache"
                    value={bytes(storage.data.scrape_cache.size_bytes)}
                    hint={`${storage.data.scrape_cache.entries} entries`}
                    className="!shadow-none"
                  />
                  <StatTile
                    label="Speech models"
                    value={bytes(storage.data.model_cache.size_bytes)}
                    hint={`${storage.data.model_cache.files} files`}
                    className="!shadow-none"
                  />
                </div>

                <Table head={['Table', 'Records']} dense>
                  {Object.entries(storage.data.row_counts).map(([table, count]) => (
                    <tr key={table}>
                      <Td dense className="mono text-xs">
                        {table}
                      </Td>
                      <Td dense className="mono text-xs font-semibold">
                        {count}
                      </Td>
                    </tr>
                  ))}
                </Table>

                <p className="mono break-all text-xs text-ink-faint">{storage.data.path}</p>
              </>
            )}

            <div className="flex flex-wrap gap-2 border-t border-line pt-4">
              <Button
                variant="secondary"
                size="sm"
                icon={RefreshCw}
                onClick={async () => {
                  const result = await roleApi.clearCache();
                  notify({ tone: 'ok', title: 'Scrape cache cleared', message: `${result.cleared} removed.` });
                  storage.reload();
                }}
              >
                Clear scrape cache
              </Button>
              <Button variant="danger" size="sm" icon={Trash2} onClick={() => setConfirmClear(true)}>
                Delete all my data
              </Button>
            </div>
          </div>
        </Card>

        {/* ------------------------------------------- normalisation -- */}
        <Card className="xl:col-span-2">
          <CardHeader
            title="Skill normalisation playground"
            subtitle="Paste any list of skill spellings and watch them collapse into canonical skills"
            icon={Sparkles}
            actions={
              <Badge tone="brand">
                <Layers size={11} aria-hidden /> {shownHealth?.components.skill_taxonomy.canonical_skills ?? 0}{' '}
                skills · {shownHealth?.components.skill_taxonomy.alias_entries ?? 0} aliases
              </Badge>
            }
          />
          <div className="card-pad space-y-4">
            <Field
              label="Skill strings, comma separated"
              hint="This is the component that satisfies the requirement that React / ReactJS / React.js count as one skill"
            >
              <textarea
                value={probe}
                onChange={(event) => setProbe(event.target.value)}
                rows={2}
                className="input resize-y"
                maxLength={1200}
              />
            </Field>
            <Button variant="primary" icon={Sparkles} loading={probing} onClick={() => void runProbe()}>
              Normalise
            </Button>

            {probeResult && (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">{probeResult.input_count} strings in</Badge>
                  <span className="text-ink-faint" aria-hidden>
                    →
                  </span>
                  <Badge tone="ok">{probeResult.output_count} canonical skills out</Badge>
                  {probeResult.input_count > probeResult.output_count && (
                    <Badge tone="brand">
                      {probeResult.input_count - probeResult.output_count} duplicates merged
                    </Badge>
                  )}
                </div>

                <Table head={['Canonical skill', 'Category', 'Merged from', 'Stage', 'Confidence']}>
                  {probeResult.output.map((row) => (
                    <tr key={row.canonical}>
                      <Td className="font-semibold">{row.canonical}</Td>
                      <Td className="text-xs text-ink-muted">{row.category}</Td>
                      <Td className="text-ink-muted">{row.surface_forms.join(' · ')}</Td>
                      <Td>
                        <Badge tone="neutral">{row.stage}</Badge>
                      </Td>
                      <Td className="mono text-xs">{row.confidence.toFixed(2)}</Td>
                    </tr>
                  ))}
                </Table>

                <Collapsible title="Lookup keys produced by the text normaliser">
                  <Table head={['Input string', 'Normalised lookup key']} dense>
                    {Object.entries(probeResult.lookup_keys).map(([input, key]) => (
                      <tr key={input}>
                        <Td dense className="mono text-xs">
                          {input}
                        </Td>
                        <Td dense className="mono text-xs font-semibold text-brand-600">
                          {key}
                        </Td>
                      </tr>
                    ))}
                  </Table>
                </Collapsible>
              </>
            )}
          </div>
        </Card>

        {/* ---------------------------------------------- system health -- */}
        {shownHealth && (
          <Card className="xl:col-span-2">
            <CardHeader
              title="System health"
              subtitle={deepResult ? 'Live deep check, including network probes' : 'Shallow check — run a system check for network probes'}
              icon={ShieldCheck}
              actions={
                <Badge tone={shownHealth.status === 'ok' ? 'ok' : 'warn'}>
                  {shownHealth.status === 'ok' ? (
                    <CheckCircle2 size={11} aria-hidden />
                  ) : (
                    <AlertTriangle size={11} aria-hidden />
                  )}
                  {shownHealth.status}
                </Badge>
              }
            />
            <div className="card-pad">
              <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <StatTile
                  label="Database"
                  value={shownHealth.components.database.ok ? 'ready' : 'error'}
                  hint={`schema v${shownHealth.components.database.schema_version ?? '?'}`}
                  tone={shownHealth.components.database.ok ? 'ok' : 'danger'}
                  className="!shadow-none"
                />
                <StatTile
                  label="Language model"
                  value={shownHealth.components.llm.provider}
                  hint={shownHealth.components.llm.model}
                  tone={shownHealth.components.llm.degraded ? 'warn' : 'ok'}
                  className="!shadow-none"
                />
                <StatTile
                  label="Speech recognition"
                  value={shownHealth.components.speech_recognition.installed ? 'ready' : 'missing'}
                  hint={shownHealth.components.speech_recognition.model_size}
                  tone={shownHealth.components.speech_recognition.installed ? 'ok' : 'danger'}
                  className="!shadow-none"
                />
                <StatTile
                  label="Speech synthesis"
                  value={shownHealth.components.text_to_speech.active_engine ?? '—'}
                  hint={
                    shownHealth.components.text_to_speech.active_engine === 'piper'
                      ? 'neural, local'
                      : 'OS voice, local'
                  }
                  tone={shownHealth.components.text_to_speech.active_engine === 'piper' ? 'ok' : 'warn'}
                  className="!shadow-none"
                />
              </div>

              {sourceResult && (
                <Table head={['Job source', 'Reachable', 'Status', 'Time', 'robots.txt', 'Detail']}>
                  {sourceResult.sources.map((source) => (
                    <tr key={source.name}>
                      <Td className="font-semibold">{source.name}</Td>
                      <Td>
                        <Badge tone={source.reachable ? 'ok' : 'danger'}>
                          {source.reachable ? 'yes' : 'no'}
                        </Badge>
                      </Td>
                      <Td className="text-xs">{source.status.replace(/_/g, ' ')}</Td>
                      <Td className="mono text-xs">{ms(source.elapsed_ms)}</Td>
                      <Td className="text-xs text-ink-muted">{source.robots ?? '—'}</Td>
                      <Td className="max-w-[16rem] text-xs text-ink-muted">{source.detail || '—'}</Td>
                    </tr>
                  ))}
                </Table>
              )}

              <dl className="mt-4 grid gap-x-8 gap-y-1 border-t border-line pt-4 text-xs sm:grid-cols-3">
                {[
                  ['Version', shownHealth.version],
                  ['Environment', shownHealth.environment],
                  ['Python', shownHealth.runtime.python],
                  ['Platform', shownHealth.runtime.platform],
                  ['Uptime', `${(shownHealth.uptime_seconds / 60).toFixed(1)} min`],
                  ['Taxonomy edges', shownHealth.components.skill_taxonomy.implication_edges],
                ].map(([label, text]) => (
                  <div key={String(label)} className="flex justify-between gap-2">
                    <dt className="text-ink-muted">{label}</dt>
                    <dd className="mono font-semibold text-ink">{String(text)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </Card>
        )}
      </div>

      {/* ------------------------------------------------- confirm modal -- */}
      <Modal
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        title="Delete all your data?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmClear(false)}>
              Cancel
            </Button>
            <Button variant="danger" icon={Trash2} loading={clearing} onClick={() => void clearAll()}>
              Delete everything
            </Button>
          </>
        }
      >
        <p className="text-sm leading-relaxed text-ink">
          This permanently deletes every CV, role analysis, gap analysis, CV rewrite, interview
          transcript, feedback report and latency measurement from the local database.
        </p>
        <Notice tone="warn" className="mt-4">
          <AlertTriangle size={12} className="mr-1 inline" aria-hidden />
          This cannot be undone.
        </Notice>
        <p className="mt-3 flex gap-1.5 text-xs text-ink-muted">
          <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
          Downloaded speech models are kept — they contain no personal data and are expensive to
          download again.
        </p>
      </Modal>
    </>
  );
}

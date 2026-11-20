/**
 * Page 8 - Performance report (Module 7).
 *
 * The assignment asks for latency measured across at least three very different
 * roles, so this page leads with the per-role comparison and states explicitly
 * whether that requirement is currently met by the data on this machine.
 */

import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Download,
  Gauge,
  Info,
  Mic,
  Timer,
  Trash2,
  Zap,
} from 'lucide-react';
import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import {
  Badge,
  Button,
  Card,
  CardHeader,
  Collapsible,
  EmptyState,
  ErrorState,
  Loading,
  Notice,
  PageHeader,
  StatTile,
  Table,
  Td,
} from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { metricsApi } from '../lib/api';
import { ms } from '../lib/format';
import { useApp } from '../lib/store';
import type { MetricField } from '../lib/types';

const FIELDS: MetricField[] = [
  'stt_ms',
  'llm_ttft_ms',
  'llm_total_ms',
  'tts_first_ms',
  'tts_total_ms',
  'e2e_first_audio_ms',
  'total_ms',
];

const STAGE_COLOURS = ['#0ea5e9', '#f59e0b', '#10b981'];

export default function Performance() {
  const { notify } = useApp();
  const { data, loading, error, reload } = useAsync(() => metricsApi.overview(false), []);

  const clear = useCallback(async () => {
    try {
      const result = await metricsApi.clear();
      notify({ tone: 'ok', title: 'Measurements cleared', message: `${result.cleared} removed.` });
      reload();
    } catch {
      notify({ tone: 'danger', title: 'Could not clear measurements' });
    }
  }, [notify, reload]);

  if (loading) return <Loading label="Loading performance measurements…" />;
  if (error || !data) {
    return <ErrorState title="Could not load measurements" message={error ?? undefined} onRetry={reload} />;
  }

  const summary = data.summary;
  const headline = summary.aggregates.e2e_first_audio_ms;

  if (summary.total_turns === 0) {
    return (
      <>
        <PageHeader
          title="Performance Report"
          description="Measured latency for the voice interview pipeline: local speech recognition, LLM generation, and local speech synthesis."
        />
        <Card>
          <EmptyState
            icon={Gauge}
            title="No measurements yet"
            description="Latency is recorded automatically during every interview turn. Run a voice interview and this report fills itself in — no numbers are estimated or entered by hand."
            action={
              <Link to="/interview">
                <Button variant="primary" icon={Mic}>
                  Run a voice interview
                </Button>
              </Link>
            }
          />
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Performance Report"
        description="Every figure below is measured with a high-resolution timer inside the real request path. The reference point for all end-to-end numbers is the moment the candidate's recording reached the server — the end of their speech."
        badge={
          summary.meets_three_role_requirement ? (
            <Badge tone="ok">
              <CheckCircle2 size={11} aria-hidden /> {summary.roles_tested} roles tested
            </Badge>
          ) : (
            <Badge tone="warn">
              <AlertTriangle size={11} aria-hidden /> {summary.roles_tested} of 3 roles
            </Badge>
          )
        }
        actions={
          <>
            <a href={metricsApi.exportCsvUrl()} download>
              <Button variant="secondary" icon={Download}>
                CSV
              </Button>
            </a>
            <a href={metricsApi.exportUrl()} download>
              <Button variant="secondary" icon={Download}>
                JSON
              </Button>
            </a>
            <Button variant="ghost" icon={Trash2} onClick={() => void clear()}>
              Clear
            </Button>
          </>
        }
      />

      {!summary.meets_three_role_requirement && (
        <Notice tone="warn" title="Fewer than three roles tested" className="mb-6">
          The project specification asks for the system to be tested on at least three very different
          roles. So far {summary.roles_tested} {summary.roles_tested === 1 ? 'role has' : 'roles have'}{' '}
          been interviewed on this machine. Run interviews for distinct roles — for example Software
          Engineer, Data Analyst and Cybersecurity Analyst — to complete the evaluation.
        </Notice>
      )}

      {/* ------------------------------------------------------ headline -- */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="End of speech → first audio"
          value={ms(headline.median_ms)}
          hint={`median of ${headline.samples} turns · p90 ${ms(headline.p90_ms)}`}
          icon={Zap}
          tone={headline.median_ms !== null && headline.median_ms < 1500 ? 'ok' : 'warn'}
        />
        <StatTile
          label="Speech recognition"
          value={ms(summary.aggregates.stt_ms.median_ms)}
          hint="local faster-whisper, median"
          icon={Mic}
        />
        <StatTile
          label="First text token"
          value={ms(summary.aggregates.llm_ttft_ms.median_ms)}
          hint="measured from end of speech"
          icon={Activity}
        />
        <StatTile
          label="First sentence spoken"
          value={ms(summary.aggregates.tts_first_ms.median_ms)}
          hint="local Piper, median"
          icon={Timer}
        />
      </div>

      <div className="space-y-6">
        {/* ------------------------------------------- stage contribution -- */}
        {data.stage_breakdown.length > 0 && (
          <Card>
            <CardHeader
              title="Where the time goes"
              subtitle="Mean contribution of each pipeline stage to the reply latency"
              icon={BarChart3}
            />
            <div className="card-pad">
              <ResponsiveContainer width="100%" height={150}>
                <BarChart
                  data={data.stage_breakdown}
                  layout="vertical"
                  margin={{ left: 4, right: 52, top: 4, bottom: 4 }}
                >
                  <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                  <XAxis type="number" unit="ms" tickLine={false} axisLine={false} />
                  <YAxis
                    type="category"
                    dataKey="stage"
                    width={168}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fontSize: 10 }}
                  />
                  <Tooltip
                    formatter={(value: number) => [ms(value), 'Mean']}
                    contentStyle={{
                      background: 'rgb(var(--surface-raised))',
                      border: '1px solid rgb(var(--line))',
                      borderRadius: 12,
                      fontSize: 11,
                    }}
                  />
                  <Bar dataKey="mean_ms" radius={[0, 5, 5, 0]} barSize={22}>
                    {data.stage_breakdown.map((row, index) => (
                      <Cell key={row.stage} fill={STAGE_COLOURS[index % STAGE_COLOURS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="mt-2 text-xs text-ink-faint">
                The LLM share is computed as first-token time minus transcription time, because the
                first-token measurement starts at the end of the candidate's speech.
              </p>
            </div>
          </Card>
        )}

        {/* ------------------------------------------------- full summary -- */}
        <Card>
          <CardHeader
            title="All measurements"
            subtitle={`${summary.total_turns} turns across ${summary.total_interviews} interviews`}
            icon={Gauge}
          />
          <Table head={['Measurement', 'Median', 'Mean', 'p90', 'Fastest', 'Slowest', 'Samples']}>
            {FIELDS.map((field) => {
              const row = summary.aggregates[field];
              const isHeadline = field === summary.headline_metric;
              return (
                <tr key={field} className={isHeadline ? 'bg-brand-500/8' : undefined}>
                  <Td className={isHeadline ? 'font-bold' : 'font-medium'}>
                    {summary.metric_labels[field] ?? field}
                    {isHeadline && (
                      <Badge tone="brand" className="ml-2">
                        headline
                      </Badge>
                    )}
                  </Td>
                  <Td className="mono text-xs font-semibold">{ms(row.median_ms)}</Td>
                  <Td className="mono text-xs">{ms(row.mean_ms)}</Td>
                  <Td className="mono text-xs">{ms(row.p90_ms)}</Td>
                  <Td className="mono text-xs">{ms(row.min_ms)}</Td>
                  <Td className="mono text-xs">{ms(row.max_ms)}</Td>
                  <Td className="mono text-xs">{row.samples}</Td>
                </tr>
              );
            })}
          </Table>
          <p className="px-5 pb-4 text-xs text-ink-faint">
            The median and p90 are reported alongside the mean because a mean alone hides the slow
            tail that users actually notice. Percentiles use nearest-rank with no interpolation, which
            stays honest at small sample sizes.
          </p>
        </Card>

        {/* --------------------------------------------------- by role -- */}
        <Card>
          <CardHeader
            title="By job role"
            subtitle="The specification requires at least three very different roles"
            icon={BarChart3}
          />
          <div className="card-pad">
            {summary.by_role.length > 1 && (
              <ResponsiveContainer width="100%" height={Math.max(170, summary.by_role.length * 52)}>
                <BarChart
                  data={summary.by_role.map((role) => ({
                    role: role.role_title,
                    median: role.aggregates.e2e_first_audio_ms.median_ms ?? 0,
                    stt: role.aggregates.stt_ms.median_ms ?? 0,
                    ttft: role.aggregates.llm_ttft_ms.median_ms ?? 0,
                  }))}
                  margin={{ left: -14, right: 8, top: 8, bottom: 4 }}
                >
                  <CartesianGrid vertical={false} strokeDasharray="3 3" />
                  <XAxis dataKey="role" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
                  <YAxis unit="ms" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
                  <Tooltip
                    formatter={(value: number, name: string) => [ms(value), name]}
                    contentStyle={{
                      background: 'rgb(var(--surface-raised))',
                      border: '1px solid rgb(var(--line))',
                      borderRadius: 12,
                      fontSize: 11,
                    }}
                  />
                  <Legend iconSize={9} wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="stt" name="Speech recognition" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="ttft" name="First text token" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                  <Bar
                    dataKey="median"
                    name="End of speech → first audio"
                    fill="rgb(var(--brand-600))"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}

            <Table head={['Role', 'Interviews', 'Turns', 'Median reply', 'p90 reply', 'Median STT', 'Median TTFT']}>
              {summary.by_role.map((role) => (
                <tr key={role.role_title}>
                  <Td className="font-semibold">{role.role_title}</Td>
                  <Td className="mono text-xs">{role.interviews}</Td>
                  <Td className="mono text-xs">{role.turns}</Td>
                  <Td className="mono text-xs font-semibold">
                    {ms(role.aggregates.e2e_first_audio_ms.median_ms)}
                  </Td>
                  <Td className="mono text-xs">{ms(role.aggregates.e2e_first_audio_ms.p90_ms)}</Td>
                  <Td className="mono text-xs">{ms(role.aggregates.stt_ms.median_ms)}</Td>
                  <Td className="mono text-xs">{ms(role.aggregates.llm_ttft_ms.median_ms)}</Td>
                </tr>
              ))}
            </Table>
          </div>
        </Card>

        {/* --------------------------------------------------- timeline -- */}
        {data.timeline.length > 1 && (
          <Card>
            <CardHeader
              title="Latency over time"
              subtitle="Each point is one real interview turn, oldest first"
              icon={Timer}
            />
            <div className="card-pad">
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={data.timeline} margin={{ left: -14, right: 8, top: 8, bottom: 4 }}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" />
                  <XAxis dataKey="index" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
                  <YAxis unit="ms" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
                  <Tooltip
                    formatter={(value: number, name: string) => [ms(value), name]}
                    labelFormatter={(label) => `Turn ${label}`}
                    contentStyle={{
                      background: 'rgb(var(--surface-raised))',
                      border: '1px solid rgb(var(--line))',
                      borderRadius: 12,
                      fontSize: 11,
                    }}
                  />
                  <Legend iconSize={9} wrapperStyle={{ fontSize: 11 }} />
                  <Line
                    type="monotone"
                    dataKey="e2e_first_audio_ms"
                    name="End of speech → first audio"
                    stroke="rgb(var(--brand-600))"
                    strokeWidth={2.5}
                    dot={{ r: 2.5 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="stt_ms"
                    name="Speech recognition"
                    stroke="#0ea5e9"
                    strokeWidth={1.6}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="tts_first_ms"
                    name="First sentence TTS"
                    stroke="#10b981"
                    strokeWidth={1.6}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        )}

        {/* -------------------------------------------------- provenance -- */}
        <Card>
          <CardHeader title="How these numbers were produced" icon={Info} />
          <div className="card-pad space-y-4">
            <dl className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
              {[
                ['Speech recognition', summary.engines.stt.join(', ') || '—'],
                ['Speech synthesis', summary.engines.tts.join(', ') || '—'],
                ['LLM providers', summary.engines.llm_providers.join(', ') || '—'],
                ['LLM models', summary.engines.llm_models.join(', ') || '—'],
              ].map(([label, value]) => (
                <div key={label} className="flex items-baseline justify-between gap-3 text-sm">
                  <dt className="text-ink-muted">{label}</dt>
                  <dd className="mono truncate text-xs font-semibold text-ink" title={value}>
                    {value}
                  </dd>
                </div>
              ))}
            </dl>

            <ul className="space-y-1.5 border-t border-line pt-4 text-[0.8125rem] leading-relaxed text-ink-muted">
              {summary.notes.map((note, index) => (
                <li key={index} className="flex gap-1.5">
                  <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-[rgb(var(--ok))]" aria-hidden />
                  {note}
                </li>
              ))}
            </ul>

            <Collapsible title="What each measurement means">
              <Table head={['Metric', 'Definition']} dense>
                {FIELDS.map((field) => (
                  <tr key={field}>
                    <Td dense className="mono text-xs font-semibold">
                      {field}
                    </Td>
                    <Td dense className="text-ink-muted">
                      {summary.metric_labels[field]}
                    </Td>
                  </tr>
                ))}
              </Table>
            </Collapsible>
          </div>
        </Card>
      </div>
    </>
  );
}

/**
 * Page 4 - Skill Gap Dashboard (Module 3).
 *
 * The score is presented as "requirement coverage", never as employability, and
 * the disclaimer sits next to the number rather than buried at the bottom —
 * a percentage next to a job title invites exactly the misreading the
 * assignment warns against.
 */

import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  CircleDot,
  Clock,
  Info,
  Layers,
  Lightbulb,
  Mic,
  PenLine,
  Sparkles,
  Target,
  TrendingUp,
  XCircle,
  Zap,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
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
  Field,
  Loading,
  Notice,
  PageHeader,
  Ring,
  Select,
  StatTile,
  Table,
  Tabs,
  Td,
} from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { ApiFailure, cvApi, gapApi, roleApi } from '../lib/api';
import { categoryColour, percent, relativeTime, severityBadgeClass, STATUS_COLOURS } from '../lib/format';
import { useApp } from '../lib/store';
import type { GapResult, SkillComparison } from '../lib/types';

type Tab = 'priority' | 'missing' | 'matched' | 'partial' | 'extra';

export default function SkillGap() {
  const { gapId } = useParams();
  const navigate = useNavigate();
  const { notify, selection, setCv, setRole } = useApp();

  const [cvId, setCvId] = useState(selection.cvId);
  const [roleId, setRoleId] = useState(selection.roleAnalysisId);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [result, setResult] = useState<{ id: string; roleTitle: string; cvName: string; data: GapResult } | null>(null);
  const [tab, setTab] = useState<Tab>('priority');

  const cvs = useAsync(() => cvApi.list(50), []);
  const roles = useAsync(() => roleApi.list(50), []);
  const history = useAsync(() => gapApi.list(12), []);
  const detail = useAsync(async () => (gapId ? gapApi.get(gapId) : null), [gapId]);

  useEffect(() => {
    if (detail.data) {
      setResult({
        id: detail.data.gap_analysis_id,
        roleTitle: detail.data.role_title,
        cvName: detail.data.cv_filename,
        data: detail.data.result,
      });
      setCvId(detail.data.cv_id);
      setRoleId(detail.data.role_analysis_id);
    }
  }, [detail.data]);

  const run = useCallback(async () => {
    if (!cvId || !roleId) {
      setRunError('Choose both a CV and a role analysis.');
      return;
    }
    setRunning(true);
    setRunError(null);
    try {
      const response = await gapApi.analyse(cvId, roleId, true);
      setResult({
        id: response.gap_analysis_id,
        roleTitle: response.role_title,
        cvName: response.cv_filename,
        data: response.result,
      });
      setCv(response.cv_id, response.cv_filename);
      setRole(response.role_analysis_id, response.role_title);
      setTab('priority');
      history.reload();
      notify({
        tone: 'ok',
        title: 'Gap analysis complete',
        message: `${response.result.match_percent.toFixed(0)}% requirement coverage · ${response.result.stats.missing} missing skills.`,
      });
      navigate(`/gap/${response.gap_analysis_id}`, { replace: true });
    } catch (caught: unknown) {
      const message = caught instanceof ApiFailure ? caught.message : 'The analysis failed.';
      setRunError(message);
      notify({ tone: 'danger', title: 'Gap analysis failed', message });
    } finally {
      setRunning(false);
    }
  }, [cvId, roleId, history, navigate, notify, setCv, setRole]);

  const data = result?.data;
  const ready = Boolean(cvs.data?.items.length && roles.data?.items.length);

  return (
    <>
      <PageHeader
        title="Skill Gap Dashboard"
        description="Compares the skills on your CV with the combined requirement list for a role, and ranks the gaps by how much they actually matter."
        actions={
          data && (
            <>
              <Link to="/improve">
                <Button variant="secondary" icon={PenLine}>
                  Improve CV
                </Button>
              </Link>
              <Link to="/interview">
                <Button variant="primary" icon={Mic} iconRight={ArrowRight}>
                  Practise interview
                </Button>
              </Link>
            </>
          )
        }
      />

      {/* --------------------------------------------------------- picker -- */}
      <Card className="mb-6">
        <div className="card-pad">
          <div className="grid gap-4 lg:grid-cols-[1fr_1fr_auto] lg:items-end">
            <Field label="Your CV" hint={`${cvs.data?.count ?? 0} available`}>
              <Select
                value={cvId}
                onChange={setCvId}
                ariaLabel="Select CV"
                options={[
                  { value: '', label: cvs.data?.items.length ? 'Choose a CV…' : 'No CVs uploaded yet' },
                  ...(cvs.data?.items ?? []).map((item) => ({
                    value: item.cv_id,
                    label: `${item.filename} — ${item.skill_count} skills`,
                  })),
                ]}
              />
            </Field>
            <Field label="Target role" hint={`${roles.data?.count ?? 0} analysed`}>
              <Select
                value={roleId}
                onChange={setRoleId}
                ariaLabel="Select role analysis"
                options={[
                  { value: '', label: roles.data?.items.length ? 'Choose a role…' : 'No roles analysed yet' },
                  ...(roles.data?.items ?? []).map((item) => ({
                    value: item.role_analysis_id,
                    label: `${item.role_title} — ${item.stats.total_skills ?? 0} requirements`,
                  })),
                ]}
              />
            </Field>
            <Button
              variant="primary"
              icon={Target}
              loading={running}
              disabled={!cvId || !roleId}
              onClick={() => void run()}
              className="h-[2.625rem]"
            >
              {running ? 'Comparing…' : 'Run gap analysis'}
            </Button>
          </div>

          {!ready && !cvs.loading && !roles.loading && (
            <Notice tone="info" className="mt-4">
              You need at least one parsed CV and one analysed role.{' '}
              {!cvs.data?.items.length && (
                <Link to="/cv" className="link">
                  Upload a CV
                </Link>
              )}
              {!cvs.data?.items.length && !roles.data?.items.length && ' · '}
              {!roles.data?.items.length && (
                <Link to="/roles" className="link">
                  Analyse a role
                </Link>
              )}
            </Notice>
          )}

          {runError && (
            <Notice tone="danger" className="mt-4">
              {runError}
            </Notice>
          )}
        </div>
      </Card>

      {detail.loading && gapId && <Loading label="Loading gap analysis…" />}
      {detail.error && gapId && (
        <ErrorState title="Could not load that analysis" message={detail.error} onRetry={detail.reload} />
      )}

      {data && result ? (
        <div className="space-y-6">
          {/* ---------------------------------------------- score header -- */}
          <Card>
            <div className="card-pad">
              <div className="flex flex-col gap-6 lg:flex-row lg:items-center">
                <div className="flex items-center gap-5">
                  <Ring
                    value={data.match_percent}
                    size={128}
                    thickness={10}
                    colour={
                      data.match_percent >= 70 ? '#10b981' : data.match_percent >= 45 ? '#f59e0b' : '#ef4444'
                    }
                    label={`${data.match_percent.toFixed(0)}% requirement coverage`}
                  >
                    <div>
                      <p className="text-2xl font-bold leading-none text-ink">
                        {data.match_percent.toFixed(0)}
                        <span className="text-base">%</span>
                      </p>
                      <p className="mt-0.5 text-[0.625rem] font-semibold uppercase tracking-wide text-ink-faint">
                        coverage
                      </p>
                    </div>
                  </Ring>
                  <div className="min-w-0">
                    <p className="text-[0.6875rem] font-bold uppercase tracking-wider text-ink-faint">
                      {result.cvName} → {result.roleTitle}
                    </p>
                    <h2 className="mt-1 text-lg font-bold text-ink text-balance">{data.readiness_label}</h2>
                    <p className="mt-1 text-sm text-ink-muted">
                      Weighted by how often each requirement appears in live adverts and how essential
                      it is. Unweighted count: {percent(data.unweighted_percent)}.
                    </p>
                  </div>
                </div>

                <div className="grid flex-1 grid-cols-2 gap-3 sm:grid-cols-4">
                  <StatTile
                    label="Matched"
                    value={data.stats.matched}
                    icon={CheckCircle2}
                    tone="ok"
                    className="!shadow-none"
                  />
                  <StatTile
                    label="Partial"
                    value={data.stats.partial}
                    icon={CircleDot}
                    tone="warn"
                    className="!shadow-none"
                  />
                  <StatTile
                    label="Missing"
                    value={data.stats.missing}
                    icon={XCircle}
                    tone="danger"
                    className="!shadow-none"
                  />
                  <StatTile
                    label="Essential covered"
                    value={percent(data.essential_coverage.coverage_percent)}
                    hint={`${data.essential_coverage.matched}/${data.essential_coverage.total} core`}
                    icon={Zap}
                    tone={data.essential_coverage.coverage_percent >= 70 ? 'ok' : 'warn'}
                    className="!shadow-none"
                  />
                </div>
              </div>

              <Notice tone="info" className="mt-5">
                <span className="font-semibold">What this number is.</span> {data.disclaimer}
              </Notice>

              {data.warnings.map((warning, index) => (
                <Notice key={index} tone="warn" className="mt-3">
                  {warning}
                </Notice>
              ))}
            </div>
          </Card>

          {/* ------------------------------------------------------ charts -- */}
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader
                title="Coverage by category"
                subtitle="Where your CV is strong and where it is thin"
                icon={TrendingUp}
              />
              <div className="card-pad">
                <ResponsiveContainer
                  width="100%"
                  height={Math.max(200, data.category_breakdown.length * 34)}
                >
                  <BarChart
                    data={data.category_breakdown}
                    layout="vertical"
                    margin={{ left: 4, right: 36, top: 4, bottom: 4 }}
                  >
                    <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                    <XAxis type="number" domain={[0, 100]} unit="%" tickLine={false} axisLine={false} />
                    <YAxis
                      type="category"
                      dataKey="category"
                      width={126}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 10 }}
                    />
                    <Tooltip
                      formatter={(value: number, _name, item) => [
                        `${value.toFixed(0)}% · ${item.payload.matched} matched, ${item.payload.partial} partial, ${item.payload.missing} missing`,
                        'Coverage',
                      ]}
                      contentStyle={{
                        background: 'rgb(var(--surface-raised))',
                        border: '1px solid rgb(var(--line))',
                        borderRadius: 12,
                        fontSize: 11,
                      }}
                    />
                    <Bar dataKey="coverage_percent" radius={[0, 5, 5, 0]} barSize={14}>
                      {data.category_breakdown.map((row) => (
                        <Cell key={row.category} fill={categoryColour(row.category)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card>
              <CardHeader
                title="Requirement profile"
                subtitle="Your coverage against each category of requirement"
                icon={Layers}
              />
              <div className="card-pad">
                {data.category_breakdown.length >= 3 ? (
                  <ResponsiveContainer width="100%" height={Math.max(230, data.category_breakdown.length * 24)}>
                    <RadarChart data={data.category_breakdown} outerRadius="72%">
                      <PolarGrid />
                      <PolarAngleAxis dataKey="category" tick={{ fontSize: 9 }} />
                      <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 9 }} angle={90} />
                      <Radar
                        name="Coverage"
                        dataKey="coverage_percent"
                        stroke="rgb(var(--brand-600))"
                        fill="rgb(var(--brand-600))"
                        fillOpacity={0.26}
                      />
                      <Tooltip
                        formatter={(value: number) => [`${value.toFixed(0)}%`, 'Coverage']}
                        contentStyle={{
                          background: 'rgb(var(--surface-raised))',
                          border: '1px solid rgb(var(--line))',
                          borderRadius: 12,
                          fontSize: 11,
                        }}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState
                    icon={Layers}
                    title="Not enough categories to plot"
                    description="A radar chart needs at least three requirement categories."
                  />
                )}
              </div>
            </Card>
          </div>

          {/* --------------------------------------------------- skill lists -- */}
          <Card>
            <div className="card-pad pb-0">
              <Tabs<Tab>
                active={tab}
                onChange={setTab}
                tabs={[
                  { key: 'priority', label: 'Priority gaps', count: data.priority_gaps.length, icon: AlertCircle },
                  { key: 'missing', label: 'Missing', count: data.stats.missing, icon: XCircle },
                  { key: 'partial', label: 'Partial', count: data.stats.partial, icon: CircleDot },
                  { key: 'matched', label: 'Matched', count: data.stats.matched, icon: CheckCircle2 },
                  { key: 'extra', label: 'Extra skills', count: data.stats.extra_skills, icon: Sparkles },
                ]}
              />
            </div>
            <div className="card-pad">
              {tab === 'extra' ? (
                data.extra_skills.length ? (
                  <>
                    <p className="mb-3 text-sm text-ink-muted">
                      Skills on your CV that this role did not ask for. These are differentiators, not
                      waste — mention the relevant ones in your cover letter.
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {data.extra_skills.map((skill) => (
                        <span
                          key={skill.canonical}
                          className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink"
                        >
                          <span
                            className="h-2 w-2 rounded-full"
                            style={{ backgroundColor: categoryColour(skill.category) }}
                            aria-hidden
                          />
                          {skill.canonical}
                        </span>
                      ))}
                    </div>
                  </>
                ) : (
                  <EmptyState icon={Sparkles} title="No extra skills" description="Every skill on your CV maps to a requirement for this role." />
                )
              ) : (
                <ComparisonTable
                  rows={
                    tab === 'priority'
                      ? data.priority_gaps
                      : tab === 'missing'
                        ? data.missing
                        : tab === 'partial'
                          ? data.partial
                          : data.matched
                  }
                  showSeverity={tab === 'priority' || tab === 'missing'}
                />
              )}
            </div>
          </Card>

          {/* ------------------------------------------------------ advice -- */}
          {data.advice.available ? (
            <Card>
              <CardHeader
                title="Recommended learning plan"
                subtitle={data.advice.headline}
                icon={Lightbulb}
                actions={
                  data.advice.filtered_out ? (
                    <Badge tone="warn" title="Suggestions about skills you already have were dropped">
                      {data.advice.filtered_out} filtered
                    </Badge>
                  ) : undefined
                }
              />
              <div className="card-pad space-y-5">
                {data.advice.priority_gaps && data.advice.priority_gaps.length > 0 && (
                  <ol className="space-y-3">
                    {data.advice.priority_gaps.map((gap, index) => (
                      <li key={gap.skill} className="rounded-xl border border-line p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand-500/15 text-xs font-bold text-brand-700">
                            {index + 1}
                          </span>
                          <h3 className="text-sm font-bold text-ink">{gap.skill}</h3>
                          <Badge tone="neutral" className="ml-auto">
                            <Clock size={10} aria-hidden /> {gap.estimated_effort}
                          </Badge>
                        </div>
                        <p className="mt-2 text-[0.8125rem] leading-relaxed text-ink-muted">
                          {gap.why_it_matters}
                        </p>
                        <p className="mt-1.5 flex gap-1.5 text-[0.8125rem] leading-relaxed text-ink">
                          <BookOpen size={13} className="mt-0.5 shrink-0 text-brand-600" aria-hidden />
                          {gap.how_to_close}
                        </p>
                      </li>
                    ))}
                  </ol>
                )}

                <div className="grid gap-4 sm:grid-cols-2">
                  {data.advice.quick_wins && data.advice.quick_wins.length > 0 && (
                    <div>
                      <p className="label flex items-center gap-1.5">
                        <Zap size={12} aria-hidden /> Quick wins
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {data.advice.quick_wins.map((win) => (
                          <Badge key={win} tone="ok">
                            {win}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {data.advice.strengths_to_lead_with && data.advice.strengths_to_lead_with.length > 0 && (
                    <div>
                      <p className="label flex items-center gap-1.5">
                        <CheckCircle2 size={12} aria-hidden /> Lead with these
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {data.advice.strengths_to_lead_with.map((strength) => (
                          <Badge key={strength} tone="brand">
                            {strength}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {data.advice.learning_sequence && data.advice.learning_sequence.length > 0 && (
                  <Collapsible title="Suggested order to learn them in" defaultOpen>
                    <ol className="space-y-1.5">
                      {data.advice.learning_sequence.map((step, index) => (
                        <li key={index} className="flex gap-2 text-[0.8125rem] text-ink">
                          <span className="font-bold text-brand-600">{index + 1}.</span>
                          {step}
                        </li>
                      ))}
                    </ol>
                  </Collapsible>
                )}

                {data.advice.caveat && (
                  <Notice tone="info">
                    <Info size={12} className="mr-1 inline" aria-hidden />
                    {data.advice.caveat}
                  </Notice>
                )}
              </div>
            </Card>
          ) : (
            data.advice.detail && (
              <Notice tone="warn" title="Learning plan unavailable">
                {data.advice.detail}
              </Notice>
            )
          )}
        </div>
      ) : (
        !detail.loading &&
        !running && (
          <div className="grid gap-6 lg:grid-cols-[1fr_19rem]">
            <Card>
              <EmptyState
                icon={Target}
                title="Run a gap analysis"
                description="Pick one of your CVs and a role you have analysed. Every requirement is classified as matched, partially matched or missing, with the evidence for each decision shown."
              />
            </Card>
            <Card>
              <CardHeader title="Previous analyses" icon={Clock} />
              {history.data && history.data.items.length > 0 ? (
                <ul className="divide-y divide-line">
                  {history.data.items.map((item) => (
                    <li key={item.gap_analysis_id}>
                      <Link
                        to={`/gap/${item.gap_analysis_id}`}
                        className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface-muted"
                      >
                        <Ring
                          value={item.match_percent}
                          size={38}
                          thickness={4}
                          colour={
                            item.match_percent >= 70 ? '#10b981' : item.match_percent >= 45 ? '#f59e0b' : '#ef4444'
                          }
                        >
                          <span className="text-[0.625rem] font-bold text-ink">
                            {item.match_percent.toFixed(0)}
                          </span>
                        </Ring>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[0.8125rem] font-semibold text-ink">{item.role_title}</p>
                          <p className="truncate text-xs text-ink-faint">
                            {item.cv_filename} · {relativeTime(item.created_at)}
                          </p>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="card-pad text-sm text-ink-muted">No gap analyses yet.</p>
              )}
            </Card>
          </div>
        )
      )}
    </>
  );
}

function ComparisonTable({ rows, showSeverity }: { rows: SkillComparison[]; showSeverity: boolean }) {
  if (!rows.length) {
    return <EmptyState icon={CheckCircle2} title="Nothing in this category" />;
  }

  return (
    <Table
      head={[
        'Requirement',
        'Status',
        ...(showSeverity ? ['Priority'] : []),
        'Why',
        'In adverts',
      ]}
    >
      {rows.map((row) => (
        <tr key={row.requirement}>
          <Td>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-semibold">{row.requirement}</span>
              {row.essential && <Badge tone="danger">essential</Badge>}
            </div>
            <span className="mt-0.5 flex items-center gap-1.5 text-[0.6875rem] text-ink-faint">
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: categoryColour(row.category) }}
                aria-hidden
              />
              {row.category}
            </span>
          </Td>
          <Td>
            <span
              className="badge"
              style={{
                backgroundColor: `${STATUS_COLOURS[row.status]}1f`,
                color: STATUS_COLOURS[row.status],
              }}
            >
              {row.status}
            </span>
          </Td>
          {showSeverity && (
            <Td>
              <span className={severityBadgeClass(row.severity)}>{row.severity}</span>
            </Td>
          )}
          <Td className="max-w-[24rem] text-xs leading-relaxed text-ink-muted">
            {row.evidence}
            {row.matched_via && (
              <span className="mt-0.5 block text-[0.6875rem] text-ink-faint">via {row.matched_via}</span>
            )}
          </Td>
          <Td className="mono text-xs">{row.posting_count || '—'}</Td>
        </tr>
      ))}
    </Table>
  );
}

/**
 * Page 1 - Dashboard.
 *
 * Answers three questions at a glance: how far through preparation am I, what
 * did the system find in my CV, and how is each engine behaving. The
 * preparation checklist is the spine, because the product's value is the
 * sequence of steps rather than any single screen.
 */

import {
  ArrowRight,
  Award,
  BarChart3,
  Briefcase,
  CheckCircle2,
  Circle,
  Clock,
  FileText,
  FolderOpen,
  GraduationCap,
  Mic,
  PenLine,
  Sparkles,
  Target,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
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
  EmptyState,
  ErrorState,
  Loading,
  Notice,
  PageHeader,
  ProgressBar,
  Ring,
  StatTile,
} from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { systemApi } from '../lib/api';
import { ms, percent, relativeTime, scoreColour, titleCase } from '../lib/format';
import { useApp } from '../lib/store';

const STEP_ICONS: Record<string, typeof FileText> = {
  cv: FileText,
  role: Briefcase,
  gap: Target,
  improve: PenLine,
  interview: Mic,
  feedback: Award,
};

export default function Dashboard() {
  const { data, loading, error, reload } = useAsync(() => systemApi.dashboard(), []);
  const { selection } = useApp();

  if (loading) return <Loading label="Loading your dashboard…" />;
  if (error || !data) {
    return (
      <ErrorState
        title="Could not load the dashboard"
        message={error ?? 'The backend returned no data.'}
        onRetry={reload}
      />
    );
  }

  const progress = data.preparation_progress;
  const headline = data.performance.aggregates.e2e_first_audio_ms;
  const hasAnything = data.cv_count > 0 || data.recent_roles.length > 0 || data.recent_interviews.length > 0;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Your job-preparation progress, what the system extracted from your CV, and the measured performance of the local speech pipeline."
        badge={
          data.engine_status.llm.degraded ? (
            <Badge tone="warn">Offline LLM engine</Badge>
          ) : (
            <Badge tone="brand">{data.engine_status.llm.provider}</Badge>
          )
        }
        actions={
          <>
            <Link to="/cv">
              <Button variant="secondary" icon={FileText}>
                {data.cv_count > 0 ? 'Manage CVs' : 'Upload CV'}
              </Button>
            </Link>
            <Link to="/interview">
              <Button variant="primary" icon={Mic}>
                Start mock interview
              </Button>
            </Link>
          </>
        }
      />

      {!hasAnything && (
        <Card className="mb-6">
          <EmptyState
            icon={Sparkles}
            title="Let's get you prepared"
            description="Nothing has been analysed yet. The platform works in six steps: parse your CV, analyse a target role against live job postings, see your skill gaps, strengthen your CV bullet points, sit a spoken mock interview, then read the scored feedback."
            action={
              <Link to="/cv">
                <Button variant="primary" icon={FileText} iconRight={ArrowRight}>
                  Start by uploading your CV
                </Button>
              </Link>
            }
          />
        </Card>
      )}

      {data.engine_status.llm.degraded && (
        <Notice tone="warn" title="Running without a language model" className="mb-6">
          No LLM is configured, so a deterministic rule-based engine is producing role profiles,
          rewrites, interview questions and feedback. Everything works, but quality is visibly lower.
          Choose a provider on the{' '}
          <Link to="/settings" className="link">
            Settings
          </Link>{' '}
          page.
        </Notice>
      )}

      {/* ----------------------------------------------- top stat strip -- */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Preparation"
          value={progress.completed}
          unit={`/ ${progress.total} steps`}
          hint={progress.percent >= 100 ? 'All steps complete' : 'Keep going — see the checklist below'}
          icon={CheckCircle2}
          tone={progress.percent >= 100 ? 'ok' : 'brand'}
        />
        <StatTile
          label="Best role coverage"
          value={progress.best_match_percent > 0 ? percent(progress.best_match_percent) : '—'}
          hint={
            data.recent_gaps[0]
              ? `${data.recent_gaps[0].role_title} · ${data.recent_gaps[0].matched} matched, ${data.recent_gaps[0].missing} missing`
              : 'Run a skill gap analysis to see this'
          }
          icon={Target}
          tone={progress.best_match_percent >= 70 ? 'ok' : progress.best_match_percent >= 45 ? 'warn' : 'neutral'}
        />
        <StatTile
          label="Best interview score"
          value={progress.best_interview_score !== null ? progress.best_interview_score.toFixed(2) : '—'}
          unit={progress.best_interview_score !== null ? '/ 5' : undefined}
          hint={`${progress.interviews_completed} interview${progress.interviews_completed === 1 ? '' : 's'} completed`}
          icon={Award}
          tone={
            progress.best_interview_score === null
              ? 'neutral'
              : progress.best_interview_score >= 3.8
                ? 'ok'
                : progress.best_interview_score >= 3
                  ? 'warn'
                  : 'danger'
          }
        />
        <StatTile
          label="Reply latency (median)"
          value={headline.median_ms !== null ? ms(headline.median_ms) : '—'}
          hint={
            headline.samples > 0
              ? `End of speech to first audio · ${headline.samples} turn${headline.samples === 1 ? '' : 's'}`
              : 'Measured once you run a voice interview'
          }
          icon={Zap}
          tone={
            headline.median_ms === null ? 'neutral' : headline.median_ms < 1500 ? 'ok' : headline.median_ms < 3000 ? 'warn' : 'danger'
          }
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        {/* ------------------------------------------------- left column -- */}
        <div className="space-y-6 xl:col-span-2">
          {/* preparation checklist */}
          <Card>
            <CardHeader
              title="Preparation checklist"
              subtitle="The six steps this platform takes you through"
              icon={CheckCircle2}
              actions={
                <span className="text-sm font-bold text-brand-600">{percent(progress.percent)}</span>
              }
            />
            <div className="card-pad">
              <ProgressBar value={progress.percent} className="mb-5" label="Preparation progress" />
              <ol className="space-y-1">
                {progress.steps.map((step, index) => {
                  const Icon = STEP_ICONS[step.key] ?? Circle;
                  return (
                    <li key={step.key}>
                      <Link
                        to={step.href}
                        className="flex items-center gap-3 rounded-xl px-2 py-2.5 transition-colors hover:bg-surface-muted"
                      >
                        <span
                          className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-xs font-bold"
                          style={{
                            backgroundColor: step.done ? 'rgb(var(--ok) / 0.14)' : 'rgb(var(--surface-muted))',
                            color: step.done ? 'rgb(var(--ok))' : 'rgb(var(--ink-faint))',
                          }}
                        >
                          {step.done ? <CheckCircle2 size={15} aria-hidden /> : index + 1}
                        </span>
                        <Icon size={15} className="shrink-0 text-ink-faint" aria-hidden />
                        <span
                          className={`min-w-0 flex-1 truncate text-sm ${step.done ? 'font-medium text-ink-muted' : 'font-semibold text-ink'}`}
                        >
                          {step.label}
                        </span>
                        <ArrowRight size={14} className="shrink-0 text-ink-faint" aria-hidden />
                      </Link>
                    </li>
                  );
                })}
              </ol>
            </div>
          </Card>

          {/* candidate profile */}
          <Card>
            <CardHeader
              title="Candidate profile"
              subtitle={
                data.latest_cv
                  ? `From ${data.latest_cv.filename} · parsed ${relativeTime(data.latest_cv.created_at)}`
                  : 'No CV has been parsed yet'
              }
              icon={FileText}
              actions={
                data.latest_cv && (
                  <Link to={`/cv/${data.latest_cv.cv_id}`}>
                    <Button variant="ghost" size="sm" iconRight={ArrowRight}>
                      View
                    </Button>
                  </Link>
                )
              }
            />
            {data.latest_cv ? (
              <div className="card-pad">
                <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-lg font-bold text-ink">
                      {data.latest_cv.full_name || 'Name not detected'}
                    </p>
                    {data.latest_cv.headline && (
                      <p className="mt-1 max-w-xl text-sm leading-relaxed text-ink-muted text-pretty">
                        {data.latest_cv.headline.slice(0, 220)}
                        {data.latest_cv.headline.length > 220 ? '…' : ''}
                      </p>
                    )}
                  </div>
                </div>

                <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {[
                    { label: 'Skills', value: data.latest_cv.skill_count, icon: Sparkles },
                    { label: 'Roles', value: data.latest_cv.experience_count, icon: Briefcase },
                    { label: 'Projects', value: data.latest_cv.project_count, icon: FolderOpen },
                    { label: 'Education', value: data.latest_cv.education_count, icon: GraduationCap },
                  ].map((item) => (
                    <div key={item.label} className="rounded-xl bg-surface-muted px-3 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <item.icon size={12} className="text-ink-faint" aria-hidden />
                        <p className="text-[0.6875rem] font-semibold uppercase tracking-wide text-ink-muted">
                          {item.label}
                        </p>
                      </div>
                      <p className="mt-1 text-xl font-bold leading-none text-ink">{item.value}</p>
                    </div>
                  ))}
                </div>

                {data.latest_cv.top_skills.length > 0 && (
                  <>
                    <p className="label">Top extracted skills</p>
                    <div className="flex flex-wrap gap-1.5">
                      {data.latest_cv.top_skills.map((skill) => (
                        <Badge key={skill} tone="neutral">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  </>
                )}

                {data.latest_cv.warnings.length > 0 && (
                  <Notice tone="warn" className="mt-4">
                    {data.latest_cv.warnings[0]}
                  </Notice>
                )}
              </div>
            ) : (
              <EmptyState
                icon={FileText}
                title="No CV parsed yet"
                description="Upload a PDF or Word CV and the parser will extract your skills, experience, projects, education and certifications into structured data."
                action={
                  <Link to="/cv">
                    <Button variant="primary" icon={FileText}>
                      Upload a CV
                    </Button>
                  </Link>
                }
              />
            )}
          </Card>

          {/* role coverage chart */}
          {data.recent_gaps.length > 0 && (
            <Card>
              <CardHeader
                title="Role coverage"
                subtitle="How much of each role's collected requirement list your CV names"
                icon={TrendingUp}
              />
              <div className="card-pad">
                <ResponsiveContainer width="100%" height={Math.max(160, data.recent_gaps.length * 44)}>
                  <BarChart
                    data={[...data.recent_gaps].reverse()}
                    layout="vertical"
                    margin={{ left: 4, right: 36, top: 4, bottom: 4 }}
                  >
                    <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                    <XAxis type="number" domain={[0, 100]} unit="%" tickLine={false} axisLine={false} />
                    <YAxis
                      type="category"
                      dataKey="role_title"
                      width={128}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 11 }}
                    />
                    <Tooltip
                      formatter={(value: number) => [`${value.toFixed(1)}%`, 'Requirement coverage']}
                      contentStyle={{
                        background: 'rgb(var(--surface-raised))',
                        border: '1px solid rgb(var(--line))',
                        borderRadius: 12,
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="match_percent" radius={[0, 6, 6, 0]} barSize={18}>
                      {[...data.recent_gaps].reverse().map((gap) => (
                        <Cell
                          key={gap.gap_analysis_id}
                          fill={
                            gap.match_percent >= 70 ? '#10b981' : gap.match_percent >= 45 ? '#f59e0b' : '#ef4444'
                          }
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <p className="mt-2 text-xs text-ink-faint">
                  Coverage is a weighted keyword comparison, not a prediction of whether you will be
                  shortlisted.
                </p>
              </div>
            </Card>
          )}
        </div>

        {/* ------------------------------------------------ right column -- */}
        <div className="space-y-6">
          {/* quick actions */}
          <Card>
            <CardHeader title="Quick actions" icon={Zap} />
            <div className="card-pad space-y-2">
              {[
                { to: '/cv', label: 'Upload a CV', icon: FileText },
                { to: '/roles', label: 'Analyse a job role', icon: Briefcase },
                { to: '/gap', label: 'Run gap analysis', icon: Target, disabled: !selection.cvId },
                { to: '/improve', label: 'Improve CV bullets', icon: PenLine, disabled: !selection.cvId },
                { to: '/interview', label: 'Start mock interview', icon: Mic },
                { to: '/performance', label: 'View performance report', icon: BarChart3 },
              ].map((action) => (
                <Link
                  key={action.to}
                  to={action.to}
                  className="flex items-center gap-2.5 rounded-xl border border-line px-3 py-2.5 text-sm font-semibold text-ink transition-colors hover:border-brand-300 hover:bg-brand-500/8"
                >
                  <action.icon size={15} className="shrink-0 text-brand-600" aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{action.label}</span>
                  {action.disabled && <span className="shrink-0 text-[0.6875rem] text-ink-faint">needs CV</span>}
                  <ArrowRight size={13} className="shrink-0 text-ink-faint" aria-hidden />
                </Link>
              ))}
            </div>
          </Card>

          {/* recent interviews */}
          <Card>
            <CardHeader
              title="Recent interviews"
              subtitle={`${data.counts.interviews ?? 0} in total`}
              icon={Mic}
            />
            {data.recent_interviews.length > 0 ? (
              <ul className="divide-y divide-line">
                {data.recent_interviews.map((interview) => (
                  <li key={interview.interview_id}>
                    <Link
                      to={`/results/${interview.interview_id}`}
                      className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-surface-muted"
                    >
                      <Ring
                        value={interview.overall_score !== null ? (interview.overall_score / 5) * 100 : 0}
                        size={40}
                        thickness={4}
                        colour={scoreColour(interview.overall_score)}
                      >
                        <span className="text-[0.625rem] font-bold text-ink">
                          {interview.overall_score !== null ? interview.overall_score.toFixed(1) : '—'}
                        </span>
                      </Ring>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-ink">{interview.role_title}</p>
                        <p className="truncate text-xs text-ink-faint">
                          {titleCase(interview.difficulty)} · {relativeTime(interview.started_at)}
                        </p>
                      </div>
                      <Badge tone={interview.status === 'complete' ? 'ok' : 'neutral'}>
                        {interview.status}
                      </Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={Mic}
                title="No interviews yet"
                description="The spoken mock interview follows a real six-stage structure and adapts to your answers."
                action={
                  <Link to="/interview">
                    <Button variant="primary" size="sm" icon={Mic}>
                      Start one
                    </Button>
                  </Link>
                }
              />
            )}
          </Card>

          {/* activity */}
          <Card>
            <CardHeader title="Recent activity" icon={Clock} />
            {data.activity.length > 0 ? (
              <ul className="scroll-area max-h-80 divide-y divide-line">
                {data.activity.map((entry, index) => (
                  <li key={`${entry.created_at}-${index}`} className="px-5 py-2.5">
                    <p className="text-[0.8125rem] font-medium leading-snug text-ink">{entry.title}</p>
                    {entry.detail && (
                      <p className="mt-0.5 text-xs leading-snug text-ink-muted">{entry.detail}</p>
                    )}
                    <p className="mt-0.5 text-[0.6875rem] text-ink-faint">{relativeTime(entry.created_at)}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="card-pad text-sm text-ink-muted">
                Nothing yet. Your analyses and interviews will appear here.
              </p>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

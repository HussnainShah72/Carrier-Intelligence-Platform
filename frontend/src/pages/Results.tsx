/**
 * Page 7 - Interview Results (Module 6 + Module 7 per interview).
 *
 * Every score shows its justification and, where available, the quote it was
 * based on. A rubric score without its evidence is just a number, and the point
 * of this page is that the candidate can disagree with it on specific grounds.
 */

import {
  Activity,
  AlertCircle,
  Award,
  BookOpen,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  Download,
  Info,
  Lightbulb,
  MessageSquare,
  Mic,
  Quote,
  RefreshCw,
  Target,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
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
  Loading,
  Notice,
  PageHeader,
  Ring,
  StatTile,
  Table,
  Tabs,
  Td,
} from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { ApiFailure, interviewApi } from '../lib/api';
import { dateTime, downloadFile, ms, relativeTime, scoreColour, titleCase } from '../lib/format';
import { useApp } from '../lib/store';
import type { InterviewReport } from '../lib/types';

type Tab = 'scores' | 'feedback' | 'plan' | 'transcript' | 'performance';

export default function Results() {
  const { interviewId } = useParams();
  const navigate = useNavigate();
  const { notify, selection } = useApp();

  const [report, setReport] = useState<InterviewReport | null>(null);
  const [scoring, setScoring] = useState(false);
  const [tab, setTab] = useState<Tab>('scores');

  const list = useAsync(() => interviewApi.list(25), []);
  const fetched = useAsync(
    async () => (interviewId ? interviewApi.report(interviewId) : null),
    [interviewId],
  );

  useEffect(() => {
    if (fetched.data?.available && fetched.data.report) setReport(fetched.data.report);
    else setReport(null);
  }, [fetched.data]);

  /* Land on the most recent interview when none is in the URL. */
  useEffect(() => {
    if (interviewId || !list.data?.items.length) return;
    const target =
      list.data.items.find((item) => item.id === selection.lastInterviewId) ?? list.data.items[0];
    navigate(`/results/${target.id}`, { replace: true });
  }, [interviewId, list.data, selection.lastInterviewId, navigate]);

  const score = useCallback(async () => {
    if (!interviewId) return;
    setScoring(true);
    try {
      const result = await interviewApi.score(interviewId);
      setReport(result);
      notify({
        tone: 'ok',
        title: 'Scored',
        message:
          result.overall_score !== null
            ? `${result.overall_score.toFixed(2)} / 5 — ${result.overall_band}`
            : 'The interview could not be scored.',
      });
      list.reload();
    } catch (caught: unknown) {
      notify({
        tone: 'danger',
        title: 'Scoring failed',
        message: caught instanceof ApiFailure ? caught.message : undefined,
      });
    } finally {
      setScoring(false);
    }
  }, [interviewId, notify, list]);

  const exportReport = useCallback(() => {
    if (!report) return;
    downloadFile(
      JSON.stringify(report, null, 2),
      `interview-report-${report.role_title.replace(/\W+/g, '-').toLowerCase()}-${report.interview_id}.json`,
      'application/json',
    );
    notify({ tone: 'ok', title: 'Report downloaded' });
  }, [report, notify]);

  const exportTranscript = useCallback(() => {
    if (!report) return;
    const lines = report.transcript.map(
      (turn) => `${turn.speaker === 'interviewer' ? 'INTERVIEWER' : 'CANDIDATE'}: ${turn.text}`,
    );
    downloadFile(
      `Mock interview transcript\nRole: ${report.role_title}\nDifficulty: ${report.difficulty}\n` +
        `Started: ${dateTime(report.started_at)}\n${'='.repeat(70)}\n\n${lines.join('\n\n')}\n`,
      `interview-transcript-${report.interview_id}.txt`,
    );
    notify({ tone: 'ok', title: 'Transcript downloaded' });
  }, [report, notify]);

  if (fetched.loading && interviewId) return <Loading label="Loading your results…" />;
  if (fetched.error && interviewId) {
    return <ErrorState title="Could not load the report" message={fetched.error} onRetry={fetched.reload} />;
  }

  if (!interviewId) {
    return (
      <>
        <PageHeader title="Interview Results" />
        <Card>
          {list.loading ? (
            <Loading />
          ) : (
            <EmptyState
              icon={ClipboardList}
              title="No interviews yet"
              description="Complete a mock interview and your scored feedback, rubric breakdown, transcript and measured latency will appear here."
              action={
                <Link to="/interview">
                  <Button variant="primary" icon={Mic}>
                    Start a mock interview
                  </Button>
                </Link>
              }
            />
          )}
        </Card>
      </>
    );
  }

  if (!report) {
    return (
      <>
        <PageHeader title="Interview Results" />
        <Card>
          <EmptyState
            icon={Award}
            title="This interview has not been scored yet"
            description={fetched.data?.message ?? 'Score it now to get your rubric breakdown and feedback.'}
            action={
              <Button variant="primary" icon={Award} loading={scoring} onClick={() => void score()}>
                Score this interview
              </Button>
            }
          />
        </Card>
      </>
    );
  }

  const scored = report.category_scores.filter((category) => category.score !== null);
  const headline = report.performance.aggregates.e2e_first_audio_ms;

  return (
    <>
      <PageHeader
        title="Interview Results"
        description={`${report.role_title} · ${titleCase(report.difficulty)} difficulty · ${titleCase(report.mode)} mode · ${relativeTime(report.started_at)}`}
        badge={<Badge tone="brand">Rubric v{report.rubric.version}</Badge>}
        actions={
          <>
            <Button variant="ghost" icon={RefreshCw} loading={scoring} onClick={() => void score()}>
              Re-score
            </Button>
            <Button variant="secondary" icon={Download} onClick={exportReport}>
              Export report
            </Button>
            <Link to="/interview">
              <Button variant="primary" icon={Mic}>
                New interview
              </Button>
            </Link>
          </>
        }
      />

      <Notice tone="info" title="What this feedback is and is not" className="mb-6">
        {report.disclaimer}
      </Notice>

      {report.assessor.degraded && (
        <Notice tone="warn" title="Rule-based assessment" className="mb-6">
          {report.assessor.note}
        </Notice>
      )}

      {/* ---------------------------------------------------- score header -- */}
      <Card className="mb-6">
        <div className="card-pad">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center">
            <div className="flex items-center gap-5">
              <Ring
                value={report.overall_percent ?? 0}
                size={132}
                thickness={10}
                colour={scoreColour(report.overall_score)}
                label={`Overall score ${report.overall_score ?? 'not assessed'} out of 5`}
              >
                <div>
                  <p className="text-2xl font-bold leading-none text-ink">
                    {report.overall_score !== null ? report.overall_score.toFixed(2) : '—'}
                  </p>
                  <p className="mt-0.5 text-[0.625rem] font-semibold uppercase tracking-wide text-ink-faint">
                    out of 5
                  </p>
                </div>
              </Ring>
              <div className="min-w-0">
                <p className="text-[0.6875rem] font-bold uppercase tracking-wider text-ink-faint">
                  Overall assessment
                </p>
                <h2 className="mt-1 text-xl font-bold text-ink">{report.overall_band}</h2>
                <p className="mt-1 max-w-md text-sm leading-relaxed text-ink-muted text-pretty">
                  {report.overall_band_summary}
                </p>
                <p className="mt-2 text-xs text-ink-faint">
                  Weighted mean of {report.categories_scored} of {report.rubric.categories.length} rubric
                  categories
                  {report.categories_not_tested.length > 0 &&
                    ` · not tested: ${report.categories_not_tested.join(', ')}`}
                </p>
              </div>
            </div>

            <div className="grid flex-1 grid-cols-2 gap-3 sm:grid-cols-4">
              <StatTile
                label="Questions"
                value={report.transcript_stats.interviewer_questions}
                hint={`${report.transcript_stats.candidate_answers} answered`}
                icon={MessageSquare}
                className="!shadow-none"
              />
              <StatTile
                label="Mean answer"
                value={report.transcript_stats.candidate_mean_words.toFixed(0)}
                unit="words"
                hint={`${report.transcript_stats.shortest_answer_words}–${report.transcript_stats.longest_answer_words} range`}
                icon={Activity}
                tone={report.transcript_stats.candidate_mean_words >= 45 ? 'ok' : 'warn'}
                className="!shadow-none"
              />
              <StatTile
                label="Skills shown"
                value={report.demonstrated_skills.length}
                hint="Role-relevant skills you named"
                icon={Target}
                className="!shadow-none"
              />
              <StatTile
                label="Reply latency"
                value={headline.median_ms !== null ? ms(headline.median_ms) : '—'}
                hint="Median, end of speech to first audio"
                icon={Zap}
                tone={
                  headline.median_ms === null ? 'neutral' : headline.median_ms < 1500 ? 'ok' : 'warn'
                }
                className="!shadow-none"
              />
            </div>
          </div>
        </div>
      </Card>

      {/* ------------------------------------------------------------ tabs -- */}
      <Card>
        <div className="card-pad pb-0">
          <Tabs<Tab>
            active={tab}
            onChange={setTab}
            tabs={[
              { key: 'scores', label: 'Rubric breakdown', count: scored.length, icon: Award },
              { key: 'feedback', label: 'Strengths & weaknesses', icon: TrendingUp },
              { key: 'plan', label: 'Improvement plan', count: report.improvement_plan.length, icon: Lightbulb },
              { key: 'transcript', label: 'Transcript', count: report.transcript.length, icon: MessageSquare },
              { key: 'performance', label: 'Performance', count: report.performance.turns.length, icon: Zap },
            ]}
          />
        </div>

        <div className="card-pad">
          {tab === 'scores' && <ScoresTab report={report} />}
          {tab === 'feedback' && <FeedbackTab report={report} />}
          {tab === 'plan' && <PlanTab report={report} />}
          {tab === 'transcript' && <TranscriptTab report={report} onExport={exportTranscript} />}
          {tab === 'performance' && <PerformanceTab report={report} />}
        </div>
      </Card>

      {/* --------------------------------------------------- other results -- */}
      {list.data && list.data.items.length > 1 && (
        <Card className="mt-6">
          <CardHeader title="Your other interviews" icon={CalendarClock} />
          <Table head={['Role', 'Difficulty', 'Mode', 'Questions', 'Score', 'When', '']}>
            {list.data.items
              .filter((item) => item.id !== interviewId)
              .map((item) => (
                <tr key={item.id}>
                  <Td className="font-semibold">{item.role_title}</Td>
                  <Td>
                    <Badge tone="neutral">{titleCase(item.difficulty)}</Badge>
                  </Td>
                  <Td>
                    <Badge tone="neutral">{item.mode}</Badge>
                  </Td>
                  <Td className="mono text-xs">{item.total_questions}</Td>
                  <Td>
                    {item.overall_score !== null ? (
                      <span className="mono font-bold" style={{ color: scoreColour(item.overall_score) }}>
                        {item.overall_score.toFixed(2)}
                      </span>
                    ) : (
                      <span className="text-xs text-ink-faint">not scored</span>
                    )}
                  </Td>
                  <Td className="text-xs text-ink-muted">{relativeTime(item.started_at)}</Td>
                  <Td>
                    <Link to={`/results/${item.id}`}>
                      <Button variant="ghost" size="sm">
                        Open
                      </Button>
                    </Link>
                  </Td>
                </tr>
              ))}
          </Table>
        </Card>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ tabs -- */

function ScoresTab({ report }: { report: InterviewReport }) {
  const chartData = report.category_scores.map((category) => ({
    name: category.name.replace(/ to the Role| Competency| Understanding| Accuracy/, ''),
    fullName: category.name,
    score: category.score ?? 0,
    tested: category.score !== null,
    weight: category.weight_percent,
  }));

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <p className="label">Score by category</p>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={chartData} margin={{ left: -18, right: 8, top: 8, bottom: 32 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis
                dataKey="name"
                tickLine={false}
                axisLine={false}
                angle={-30}
                textAnchor="end"
                height={56}
                tick={{ fontSize: 9 }}
              />
              <YAxis domain={[0, 5]} ticks={[0, 1, 2, 3, 4, 5]} tickLine={false} axisLine={false} />
              <Tooltip
                formatter={(value: number, _name, item) => [
                  item.payload.tested ? `${value} / 5 (weight ${item.payload.weight}%)` : 'Not tested',
                  item.payload.fullName,
                ]}
                contentStyle={{
                  background: 'rgb(var(--surface-raised))',
                  border: '1px solid rgb(var(--line))',
                  borderRadius: 12,
                  fontSize: 11,
                }}
              />
              <Bar dataKey="score" radius={[5, 5, 0, 0]} barSize={28}>
                {chartData.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={entry.tested ? scoreColour(entry.score) : 'rgb(var(--line))'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div>
          <p className="label">Profile shape</p>
          <ResponsiveContainer width="100%" height={230}>
            <RadarChart data={chartData} outerRadius="70%">
              <PolarGrid />
              <PolarAngleAxis dataKey="name" tick={{ fontSize: 9 }} />
              <PolarRadiusAxis domain={[0, 5]} tick={{ fontSize: 9 }} angle={90} />
              <Radar
                name="Score"
                dataKey="score"
                stroke="rgb(var(--brand-600))"
                fill="rgb(var(--brand-600))"
                fillOpacity={0.26}
              />
              <Tooltip
                formatter={(value: number, _name, item) => [
                  item.payload.tested ? `${value} / 5` : 'Not tested',
                  item.payload.fullName,
                ]}
                contentStyle={{
                  background: 'rgb(var(--surface-raised))',
                  border: '1px solid rgb(var(--line))',
                  borderRadius: 12,
                  fontSize: 11,
                }}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="space-y-3">
        {report.category_scores.map((category) => (
          <div key={category.key} className="rounded-xl border border-line p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="text-sm font-bold text-ink">{category.name}</h3>
                <p className="mt-0.5 text-xs text-ink-muted">{category.description}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge tone="neutral">weight {category.weight_percent.toFixed(0)}%</Badge>
                {category.score !== null ? (
                  <span
                    className="rounded-lg px-2.5 py-1 text-sm font-bold text-white"
                    style={{ backgroundColor: scoreColour(category.score) }}
                  >
                    {category.score} / 5
                  </span>
                ) : (
                  <Badge tone="neutral">not tested</Badge>
                )}
              </div>
            </div>

            {category.score !== null && (
              <div className="mt-2.5 flex gap-1" aria-hidden>
                {[1, 2, 3, 4, 5].map((step) => (
                  <span
                    key={step}
                    className="h-1.5 flex-1 rounded-full"
                    style={{
                      backgroundColor:
                        step <= (category.score ?? 0) ? scoreColour(category.score) : 'rgb(var(--line))',
                    }}
                  />
                ))}
              </div>
            )}

            <p className="mt-3 text-[0.8125rem] leading-relaxed text-ink-muted">{category.justification}</p>

            {category.evidence_quote && (
              <blockquote className="mt-3 flex gap-2 rounded-lg bg-surface-muted p-3">
                <Quote size={13} className="mt-0.5 shrink-0 text-ink-faint" aria-hidden />
                <p className="text-[0.8125rem] italic leading-relaxed text-ink">
                  {category.evidence_quote}
                </p>
              </blockquote>
            )}
          </div>
        ))}
      </div>

      <Collapsible title="The rubric used, and the scale" subtitle={`Version ${report.rubric.version}, fixed before the interview`}>
        <Table head={['Score', 'Label', 'What it means']} dense>
          {report.rubric.scale.map((level) => (
            <tr key={level.score}>
              <Td dense className="mono font-bold">
                {level.score}
              </Td>
              <Td dense className="font-semibold">
                {level.label}
              </Td>
              <Td dense className="text-ink-muted">
                {level.descriptor}
              </Td>
            </tr>
          ))}
        </Table>
        <p className="mt-3 text-xs leading-relaxed text-ink-muted">{report.rubric.note}</p>
      </Collapsible>
    </div>
  );
}

function FeedbackTab({ report }: { report: InterviewReport }) {
  return (
    <div className="space-y-6">
      {report.overall_comment && (
        <div className="rounded-xl border border-line bg-surface-muted/50 p-4">
          <p className="label flex items-center gap-1.5">
            <Info size={12} aria-hidden /> Overall comment
          </p>
          <p className="text-sm leading-relaxed text-ink text-pretty">{report.overall_comment}</p>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <p className="label flex items-center gap-1.5 text-[rgb(var(--ok))]">
            <TrendingUp size={13} aria-hidden /> Strengths
          </p>
          {report.strengths.length ? (
            <ul className="space-y-2">
              {report.strengths.map((strength, index) => (
                <li
                  key={index}
                  className="flex gap-2 rounded-xl border p-3 text-[0.8125rem] leading-relaxed text-ink"
                  style={{
                    backgroundColor: 'rgb(var(--ok) / 0.06)',
                    borderColor: 'rgb(var(--ok) / 0.2)',
                  }}
                >
                  <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-[rgb(var(--ok))]" aria-hidden />
                  {strength}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-muted">No specific strengths were identified.</p>
          )}
        </div>

        <div>
          <p className="label flex items-center gap-1.5 text-[rgb(var(--warn))]">
            <TrendingDown size={13} aria-hidden /> Areas to work on
          </p>
          {report.weaknesses.length ? (
            <ul className="space-y-2">
              {report.weaknesses.map((weakness, index) => (
                <li
                  key={index}
                  className="flex gap-2 rounded-xl border p-3 text-[0.8125rem] leading-relaxed text-ink"
                  style={{
                    backgroundColor: 'rgb(var(--warn) / 0.07)',
                    borderColor: 'rgb(var(--warn) / 0.22)',
                  }}
                >
                  <AlertCircle size={14} className="mt-0.5 shrink-0 text-[rgb(var(--warn))]" aria-hidden />
                  {weakness}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-muted">No specific weaknesses were identified.</p>
          )}
        </div>
      </div>

      {report.answers_to_improve.length > 0 && (
        <div>
          <p className="label">Answers worth rehearsing</p>
          <div className="space-y-3">
            {report.answers_to_improve.map((item, index) => (
              <Collapsible
                key={index}
                title={item.question}
                subtitle="What you said, why it fell short, and the shape of a better answer"
                defaultOpen={index === 0}
              >
                <dl className="space-y-3 text-[0.8125rem] leading-relaxed">
                  <div>
                    <dt className="label !mb-1">What you said</dt>
                    <dd className="rounded-lg bg-surface p-3 italic text-ink-muted">
                      {item.candidate_answer_summary}
                    </dd>
                  </div>
                  <div>
                    <dt className="label !mb-1">Why it fell short</dt>
                    <dd className="text-ink">{item.why_it_fell_short}</dd>
                  </div>
                  <div>
                    <dt className="label !mb-1">A stronger answer would</dt>
                    <dd
                      className="rounded-lg border p-3 text-ink"
                      style={{
                        backgroundColor: 'rgb(var(--ok) / 0.06)',
                        borderColor: 'rgb(var(--ok) / 0.2)',
                      }}
                    >
                      {item.stronger_answer_outline}
                    </dd>
                  </div>
                </dl>
              </Collapsible>
            ))}
          </div>
        </div>
      )}

      {report.demonstrated_skills.length > 0 && (
        <div>
          <p className="label">Role-relevant skills you actually demonstrated out loud</p>
          <div className="flex flex-wrap gap-1.5">
            {report.demonstrated_skills.map((skill) => (
              <Badge key={skill} tone="ok">
                {skill}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {report.answer_quality_series.length > 1 && (
        <div>
          <p className="label">How your answers scored as the interview went on</p>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart
              data={report.answer_quality_series.map((value, index) => ({
                turn: index + 1,
                quality: Number((value * 100).toFixed(1)),
              }))}
              margin={{ left: -20, right: 8, top: 8, bottom: 4 }}
            >
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="turn" tickLine={false} axisLine={false} />
              <YAxis domain={[0, 100]} unit="%" tickLine={false} axisLine={false} />
              <Tooltip
                formatter={(value: number) => [`${value}%`, 'Answer quality (local analysis)']}
                labelFormatter={(label) => `Answer ${label}`}
                contentStyle={{
                  background: 'rgb(var(--surface-raised))',
                  border: '1px solid rgb(var(--line))',
                  borderRadius: 12,
                  fontSize: 11,
                }}
              />
              <Line
                type="monotone"
                dataKey="quality"
                stroke="rgb(var(--brand-600))"
                strokeWidth={2.5}
                dot={{ r: 3.5, fill: 'rgb(var(--brand-600))' }}
              />
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-1 text-xs text-ink-faint">
            This is the fast local score that drives the interviewer's adaptation, not the rubric score.
          </p>
        </div>
      )}
    </div>
  );
}

function PlanTab({ report }: { report: InterviewReport }) {
  if (!report.improvement_plan.length && !report.recommended_topics.length) {
    return <EmptyState icon={Lightbulb} title="No improvement plan was generated" />;
  }

  return (
    <div className="space-y-6">
      {report.recommended_topics.length > 0 && (
        <div>
          <p className="label flex items-center gap-1.5">
            <BookOpen size={12} aria-hidden /> Preparation topics, most important first
          </p>
          <ol className="space-y-2">
            {report.recommended_topics.map((topic, index) => (
              <li key={index} className="flex items-start gap-2.5 rounded-xl border border-line p-3">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand-500/15 text-xs font-bold text-brand-700">
                  {index + 1}
                </span>
                <span className="text-[0.8125rem] leading-relaxed text-ink">{topic}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {report.improvement_plan.length > 0 && (
        <div>
          <p className="label flex items-center gap-1.5">
            <CalendarClock size={12} aria-hidden /> Your personalised plan
          </p>
          <div className="space-y-3">
            {report.improvement_plan.map((phase, index) => (
              <div key={index} className="relative border-l-2 border-brand-300 pl-5">
                <span
                  className="absolute -left-[0.3125rem] top-1.5 h-2 w-2 rounded-full bg-brand-600"
                  aria-hidden
                />
                <p className="text-[0.6875rem] font-bold uppercase tracking-wider text-brand-600">
                  {phase.timeframe}
                </p>
                <h3 className="mt-0.5 text-sm font-bold text-ink">{phase.focus}</h3>
                <ul className="mt-2 space-y-1.5">
                  {phase.actions.map((action, actionIndex) => (
                    <li key={actionIndex} className="flex gap-2 text-[0.8125rem] leading-relaxed text-ink-muted">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-faint" aria-hidden />
                      {action}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      <Notice tone="info">
        Want to close the skill gaps behind this?{' '}
        <Link to="/gap" className="link">
          Run a skill gap analysis
        </Link>{' '}
        for this role, or{' '}
        <Link to="/improve" className="link">
          strengthen your CV bullet points
        </Link>
        .
      </Notice>
    </div>
  );
}

function TranscriptTab({ report, onExport }: { report: InterviewReport; onExport: () => void }) {
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-muted">
          {report.transcript_stats.total_turns} turns · {report.transcript_stats.candidate_total_words}{' '}
          words spoken by you
        </p>
        <Button variant="secondary" size="sm" icon={Download} onClick={onExport}>
          Download transcript
        </Button>
      </div>

      <div className="space-y-4">
        {report.transcript.map((turn) => {
          const isCandidate = turn.speaker === 'candidate';
          return (
            <div key={turn.id} className={`flex ${isCandidate ? 'justify-end' : 'justify-start'}`}>
              <div className="max-w-[85%]">
                <p
                  className={`mb-1 text-[0.6875rem] font-bold uppercase tracking-wider ${
                    isCandidate ? 'text-right text-brand-600' : 'text-ink-faint'
                  }`}
                >
                  {isCandidate ? 'You' : 'Interviewer'} · {titleCase(turn.stage)}
                </p>
                <div
                  className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    isCandidate
                      ? 'rounded-br-sm bg-brand-600 text-white'
                      : 'rounded-bl-sm bg-surface-muted text-ink'
                  }`}
                >
                  {turn.text}
                </div>
                {isCandidate && turn.meta.analysis && (
                  <div className="mt-1 flex flex-wrap items-center justify-end gap-1.5">
                    {turn.meta.analysis.signals.slice(0, 3).map((signal) => (
                      <Badge key={signal} tone="neutral">
                        {signal}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

function PerformanceTab({ report }: { report: InterviewReport }) {
  const metrics = report.performance;
  const fields = [
    'stt_ms',
    'llm_ttft_ms',
    'tts_first_ms',
    'e2e_first_audio_ms',
    'total_ms',
  ] as const;

  if (!metrics.turns.length) {
    return (
      <EmptyState
        icon={Zap}
        title="No latency measurements for this interview"
        description="Latency is recorded per turn during a voice interview. A text interview records generation time but no speech timings."
      />
    );
  }

  return (
    <div className="space-y-6">
      <Table head={['Measurement', 'Median', 'Mean', 'p90', 'Fastest', 'Slowest', 'Turns']}>
        {fields.map((field) => {
          const row = metrics.aggregates[field];
          const headline = field === metrics.headline_metric;
          return (
            <tr key={field} className={headline ? 'bg-brand-500/8' : undefined}>
              <Td className={headline ? 'font-bold' : 'font-medium'}>
                {metrics.metric_labels[field] ?? field}
                {headline && (
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

      <div>
        <p className="label">Latency per turn</p>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={metrics.turns} margin={{ left: -14, right: 8, top: 8, bottom: 4 }}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" />
            <XAxis dataKey="turn_index" tickLine={false} axisLine={false} />
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
            <Line
              type="monotone"
              dataKey="e2e_first_audio_ms"
              name="End of speech → first audio"
              stroke="rgb(var(--brand-600))"
              strokeWidth={2.5}
              dot={{ r: 3 }}
            />
            <Line
              type="monotone"
              dataKey="stt_ms"
              name="Speech recognition"
              stroke="#0ea5e9"
              strokeWidth={1.8}
              dot={{ r: 2.5 }}
            />
            <Line
              type="monotone"
              dataKey="llm_ttft_ms"
              name="First text token"
              stroke="#f59e0b"
              strokeWidth={1.8}
              dot={{ r: 2.5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="rounded-xl bg-surface-muted p-4">
        <p className="label">Engines that produced these numbers</p>
        <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
          {[
            ['Speech recognition', metrics.engines.stt.join(', ') || '—'],
            ['Speech synthesis', metrics.engines.tts.join(', ') || '—'],
            ['LLM provider', metrics.engines.llm_providers.join(', ') || '—'],
            ['LLM model', metrics.engines.llm_models.join(', ') || '—'],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3">
              <dt className="text-ink-muted">{label}</dt>
              <dd className="mono truncate font-semibold text-ink" title={value}>
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </div>

      <Notice tone="info">
        Every figure is measured with a high-resolution timer inside the real request path. The
        reference point for the end-to-end numbers is the moment your recording reached the server —
        that is, the end of your speech.
      </Notice>
    </div>
  );
}

/**
 * Page 3 - Job Role Analysis (Module 2).
 *
 * The important design decision on this page is that provenance is never
 * hidden. Every requirement carries a badge saying whether live job adverts
 * asked for it, the language model asserted it, or both agreed — and the
 * per-source report shows exactly what each source returned, including its
 * failures. A requirement list without that is just an assertion.
 */

import {
  AlertTriangle,
  ArrowRight,
  Brain,
  Briefcase,
  CheckCircle2,
  Clock,
  Database,
  ExternalLink,
  Globe,
  Layers,
  Radio,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  XCircle,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

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
  Select,
  StatTile,
  Table,
  Tabs,
  Td,
  Toggle,
} from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { ApiFailure, roleApi } from '../lib/api';
import { categoryColour, ms, provenanceLabel, relativeTime, titleCase, truncate } from '../lib/format';
import { useApp } from '../lib/store';
import type { RoleRequirements, SourceReport } from '../lib/types';

type Tab = 'skills' | 'postings' | 'sources' | 'merge';

const SENIORITIES = [
  { value: 'any', label: 'Any seniority' },
  { value: 'entry', label: 'Entry level' },
  { value: 'junior', label: 'Junior' },
  { value: 'mid', label: 'Mid level' },
  { value: 'senior', label: 'Senior' },
  { value: 'lead', label: 'Lead / Principal' },
];

const EXAMPLES = ['Software Engineer', 'Data Analyst', 'Cybersecurity Analyst', 'Product Manager'];

export default function RoleAnalysis() {
  const { roleId } = useParams();
  const navigate = useNavigate();
  const { notify, setRole, selection } = useApp();

  const [title, setTitle] = useState('');
  const [location, setLocation] = useState('');
  const [seniority, setSeniority] = useState('any');
  const [useScraping, setUseScraping] = useState(true);
  const [useLlm, setUseLlm] = useState(true);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [current, setCurrent] = useState<{ id: string; requirements: RoleRequirements } | null>(null);
  const [tab, setTab] = useState<Tab>('skills');

  const list = useAsync(() => roleApi.list(25), []);
  const sources = useAsync(() => roleApi.sources(), []);
  const detail = useAsync(async () => (roleId ? roleApi.get(roleId) : null), [roleId]);

  useEffect(() => {
    if (detail.data) {
      setCurrent({ id: detail.data.role_analysis_id, requirements: detail.data.requirements });
      setTitle(detail.data.role_title);
      setTab('skills');
    }
  }, [detail.data]);

  const run = useCallback(
    async (roleTitle: string) => {
      const clean = roleTitle.trim();
      if (clean.length < 2) {
        setRunError('Enter a job title with at least two characters.');
        return;
      }
      setRunning(true);
      setRunError(null);
      try {
        const result = await roleApi.analyse({
          role_title: clean,
          location,
          seniority,
          use_scraping: useScraping,
          use_llm: useLlm,
        });
        setCurrent({ id: result.role_analysis_id, requirements: result.requirements });
        setRole(result.role_analysis_id, result.requirements.role_title);
        setTab('skills');
        list.reload();
        notify({
          tone: 'ok',
          title: `Analysed "${result.requirements.role_title}"`,
          message: `${result.requirements.stats.total_skills} requirements from ${result.requirements.stats.postings_collected} live postings and the language model.`,
        });
        navigate(`/roles/${result.role_analysis_id}`, { replace: true });
      } catch (caught: unknown) {
        const message = caught instanceof ApiFailure ? caught.message : 'The analysis failed.';
        setRunError(message);
        notify({ tone: 'danger', title: 'Role analysis failed', message });
      } finally {
        setRunning(false);
      }
    },
    [location, seniority, useScraping, useLlm, list, navigate, notify, setRole],
  );

  const requirements = current?.requirements;

  return (
    <>
      <PageHeader
        title="Job Role Analysis"
        description="Enter any job title. The platform collects live job postings from public job boards AND asks a language model what the role requires, then merges the two into one normalised list with the source of every requirement shown."
        actions={
          requirements && (
            <Link to="/gap">
              <Button variant="primary" icon={Target} iconRight={ArrowRight}>
                Compare with your CV
              </Button>
            </Link>
          )
        }
      />

      {/* ----------------------------------------------------------- form -- */}
      <Card className="mb-6">
        <div className="card-pad">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void run(title);
            }}
            className="space-y-4"
          >
            <div className="grid gap-4 lg:grid-cols-[1fr_14rem_12rem_auto] lg:items-end">
              <Field label="Job title" hint="Any title works — there is no fixed list">
                <div className="relative">
                  <Search
                    size={15}
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint"
                    aria-hidden
                  />
                  <input
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="e.g. Machine Learning Engineer"
                    className="input pl-9"
                    maxLength={120}
                  />
                </div>
              </Field>
              <Field label="Location" hint="Optional">
                <input
                  value={location}
                  onChange={(event) => setLocation(event.target.value)}
                  placeholder="e.g. Remote, London"
                  className="input"
                  maxLength={80}
                />
              </Field>
              <Field label="Seniority">
                <Select value={seniority} onChange={setSeniority} options={SENIORITIES} ariaLabel="Seniority" />
              </Field>
              <Button type="submit" variant="primary" icon={Sparkles} loading={running} className="h-[2.625rem]">
                {running ? 'Analysing…' : 'Analyse role'}
              </Button>
            </div>

            <div className="flex flex-wrap items-center gap-x-8 gap-y-3 border-t border-line pt-4">
              <div className="min-w-[14rem]">
                <Toggle
                  checked={useScraping}
                  onChange={setUseScraping}
                  label="Collect live job postings"
                  description="Queries six public job boards"
                />
              </div>
              <div className="min-w-[14rem]">
                <Toggle
                  checked={useLlm}
                  onChange={setUseLlm}
                  label="Generate skills with an LLM"
                  description="Covers roles the boards miss"
                />
              </div>
              {!useScraping && !useLlm && (
                <Notice tone="warn" className="flex-1">
                  Both sources are switched off, so no requirements can be produced.
                </Notice>
              )}
            </div>

            {!current && (
              <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
                <span className="text-xs font-semibold text-ink-muted">Try:</span>
                {EXAMPLES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => {
                      setTitle(example);
                      void run(example);
                    }}
                    className="badge-neutral transition-colors hover:border-brand-300 hover:text-brand-600"
                  >
                    {example}
                  </button>
                ))}
              </div>
            )}
          </form>

          {runError && (
            <Notice tone="danger" title="Analysis failed" className="mt-4">
              {runError}
            </Notice>
          )}
          {running && (
            <Notice tone="info" className="mt-4">
              Querying six job boards in parallel and asking the language model for the role profile.
              This usually takes 10–30 seconds.
            </Notice>
          )}
        </div>
      </Card>

      {detail.loading && roleId && <Loading label="Loading role analysis…" />}
      {detail.error && roleId && (
        <ErrorState title="Could not load that analysis" message={detail.error} onRetry={detail.reload} />
      )}

      <div className="grid gap-6 xl:grid-cols-[1fr_19rem]">
        <div className="min-w-0 space-y-6">
          {requirements ? (
            <>
              {/* summary */}
              <Card>
                <CardHeader
                  title={requirements.normalised_title || requirements.role_title}
                  subtitle={requirements.role_summary || 'No role summary was produced.'}
                  icon={Briefcase}
                  actions={
                    <Badge tone={requirements.seniority === 'unspecified' ? 'neutral' : 'brand'}>
                      {titleCase(requirements.seniority)}
                    </Badge>
                  }
                />
                <div className="card-pad">
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <StatTile
                      label="Requirements"
                      value={requirements.stats.total_skills}
                      hint={`${requirements.stats.essential_skills} marked essential`}
                      icon={Layers}
                      className="!shadow-none"
                    />
                    <StatTile
                      label="Live postings"
                      value={requirements.stats.postings_collected}
                      hint={`${requirements.stats.sources_succeeded} of ${requirements.stats.sources_attempted} sources productive`}
                      icon={Globe}
                      tone={requirements.stats.postings_collected > 0 ? 'ok' : 'warn'}
                      className="!shadow-none"
                    />
                    <StatTile
                      label="Both sources agree"
                      value={requirements.stats.confirmed_by_both}
                      hint={`${(requirements.stats.agreement_rate * 100).toFixed(0)}% agreement rate`}
                      icon={CheckCircle2}
                      tone="brand"
                      className="!shadow-none"
                    />
                    <StatTile
                      label="Collection time"
                      value={ms(Object.values(requirements.timings).reduce((a, b) => a + b, 0))}
                      hint={`scrape ${ms(requirements.timings.scrape_ms)} · LLM ${ms(requirements.timings.llm_role_ms)}`}
                      icon={Clock}
                      className="!shadow-none"
                    />
                  </div>

                  {requirements.title_assessment && requirements.title_assessment !== 'clear' && (
                    <Notice tone="info" title="Note on the job title you entered" className="mt-4">
                      {requirements.title_assessment}
                    </Notice>
                  )}

                  {requirements.warnings.map((warning, index) => (
                    <Notice key={index} tone="warn" className="mt-3">
                      {warning}
                    </Notice>
                  ))}

                  {requirements.llm_degraded && (
                    <Notice tone="warn" title="Rule-based role profile" className="mt-3">
                      No language model is configured, so the LLM half of this analysis came from a
                      small built-in knowledge base. Requirements for unusual job titles will be
                      generic.
                    </Notice>
                  )}
                </div>
              </Card>

              {/* tabs */}
              <Card>
                <div className="card-pad pb-0">
                  <Tabs<Tab>
                    active={tab}
                    onChange={setTab}
                    tabs={[
                      { key: 'skills', label: 'Requirements', count: requirements.combined_skills.length, icon: Layers },
                      { key: 'postings', label: 'Job postings', count: requirements.postings.length, icon: Globe },
                      { key: 'sources', label: 'Source report', count: requirements.source_reports.length, icon: Radio },
                      { key: 'merge', label: 'Normalisation', count: requirements.merge_evidence.length, icon: ShieldCheck },
                    ]}
                  />
                </div>
                <div className="card-pad">
                  {tab === 'skills' && <SkillsTab requirements={requirements} />}
                  {tab === 'postings' && <PostingsTab requirements={requirements} />}
                  {tab === 'sources' && <SourcesTab reports={requirements.source_reports} />}
                  {tab === 'merge' && <MergeTab requirements={requirements} />}
                </div>
              </Card>

              {/* responsibilities */}
              {requirements.responsibilities.length > 0 && (
                <Card>
                  <CardHeader title="Typical responsibilities" icon={Briefcase} />
                  <ul className="card-pad space-y-2">
                    {requirements.responsibilities.map((item, index) => (
                      <li key={index} className="flex gap-2.5 text-[0.8125rem] leading-relaxed text-ink">
                        <span className="mt-0.5 shrink-0 text-xs font-bold text-brand-600">
                          {String(index + 1).padStart(2, '0')}
                        </span>
                        {item}
                      </li>
                    ))}
                  </ul>
                </Card>
              )}
            </>
          ) : (
            !detail.loading &&
            !running && (
              <Card>
                <EmptyState
                  icon={Briefcase}
                  title="Analyse a job role to begin"
                  description="Enter any job title above. The platform will collect live postings from six public job boards and independently ask a language model what the role requires, then merge and normalise both lists."
                />
              </Card>
            )
          )}
        </div>

        {/* ------------------------------------------------------ sidebar -- */}
        <div className="space-y-6">
          <Card>
            <CardHeader title="Previous analyses" subtitle={`${list.data?.count ?? 0} saved`} icon={Database} />
            {list.loading ? (
              <div className="card-pad space-y-2">
                <div className="skeleton h-12" />
                <div className="skeleton h-12" />
              </div>
            ) : list.data && list.data.items.length > 0 ? (
              <ul className="divide-y divide-line">
                {list.data.items.map((item) => (
                  <li
                    key={item.role_analysis_id}
                    className={`flex items-center gap-2 px-4 py-2.5 ${
                      item.role_analysis_id === current?.id ? 'bg-brand-500/8' : ''
                    }`}
                  >
                    <Link to={`/roles/${item.role_analysis_id}`} className="min-w-0 flex-1">
                      <p className="truncate text-[0.8125rem] font-semibold text-ink">{item.role_title}</p>
                      <p className="text-xs text-ink-faint">
                        {item.stats.total_skills ?? 0} skills · {item.stats.postings_collected ?? 0} postings ·{' '}
                        {relativeTime(item.created_at)}
                      </p>
                    </Link>
                    {selection.roleAnalysisId === item.role_analysis_id && <Badge tone="brand">active</Badge>}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="card-pad text-sm text-ink-muted">No analyses saved yet.</p>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Where postings come from"
              subtitle="Only boards that publish their listings for programmatic use"
              icon={Globe}
              actions={
                <Button
                  variant="ghost"
                  size="sm"
                  icon={RefreshCw}
                  onClick={async () => {
                    const result = await roleApi.clearCache();
                    notify({
                      tone: 'ok',
                      title: 'Cache cleared',
                      message: `${result.cleared} cached response(s) removed.`,
                    });
                    sources.reload();
                  }}
                  title="Clear the response cache"
                  ariaLabel="Clear scrape cache"
                />
              }
            />
            <div className="card-pad space-y-3">
              {sources.data?.sources.map((source) => (
                <div key={source.name} className="text-[0.8125rem]">
                  <div className="flex items-center gap-1.5">
                    <a
                      href={source.homepage}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-semibold text-ink hover:text-brand-600"
                    >
                      {source.name}
                    </a>
                    <Badge tone={source.source_type === 'rss_scrape' ? 'info' : 'neutral'}>
                      {source.source_type === 'rss_scrape' ? 'RSS scrape' : 'JSON API'}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-xs leading-snug text-ink-faint">{source.attribution}</p>
                </div>
              ))}

              {sources.data && (
                <Collapsible title="Compliance measures" className="!border-0 bg-surface-muted">
                  <dl className="space-y-2 text-xs leading-relaxed">
                    {Object.entries(sources.data.compliance).map(([key, value]) => (
                      <div key={key}>
                        <dt className="font-semibold text-ink">{titleCase(key)}</dt>
                        <dd className="text-ink-muted">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </Collapsible>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="How the two sources merge" icon={Brain} />
            <div className="card-pad space-y-2.5 text-[0.8125rem] leading-relaxed text-ink-muted">
              <p>
                Each requirement gets an importance score from three signals:{' '}
                <span className="font-semibold text-ink">how many adverts asked for it</span> (55%),{' '}
                <span className="font-semibold text-ink">how essential the LLM called it</span> (30%),
                and <span className="font-semibold text-ink">whether both sources agree</span> (15%).
              </p>
              <p>
                That ordering is deliberate: adverts supply evidence, the model supplies breadth, and
                agreement supplies confidence — so a skill both sources name outranks one asserted by
                either alone.
              </p>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ tabs -- */

function SkillsTab({ requirements }: { requirements: RoleRequirements }) {
  const [filter, setFilter] = useState<'all' | 'essential' | 'both' | 'scraped' | 'llm'>('all');

  const skills = requirements.combined_skills.filter((skill) => {
    if (filter === 'essential') return skill.essential;
    if (filter === 'both') return skill.provenance === 'both';
    if (filter === 'scraped') return skill.provenance === 'scraped';
    if (filter === 'llm') return skill.provenance === 'llm';
    return true;
  });

  if (!requirements.combined_skills.length) {
    return <EmptyState icon={Layers} title="No requirements were determined for this role" />;
  }

  const provenanceData = [
    { name: 'Both sources', value: requirements.stats.confirmed_by_both, colour: '#10b981' },
    { name: 'Job adverts only', value: requirements.stats.from_scraping_only, colour: '#0ea5e9' },
    { name: 'LLM only', value: requirements.stats.from_llm_only, colour: '#8b5cf6' },
  ].filter((entry) => entry.value > 0);

  return (
    <>
      <div className="mb-4 grid gap-4 lg:grid-cols-[1fr_16rem]">
        <Tabs
          active={filter}
          onChange={setFilter}
          tabs={[
            { key: 'all' as const, label: 'All', count: requirements.combined_skills.length },
            { key: 'essential' as const, label: 'Essential', count: requirements.stats.essential_skills },
            { key: 'both' as const, label: 'Both agree', count: requirements.stats.confirmed_by_both },
            { key: 'scraped' as const, label: 'Adverts only', count: requirements.stats.from_scraping_only },
            { key: 'llm' as const, label: 'LLM only', count: requirements.stats.from_llm_only },
          ]}
        />
        {provenanceData.length > 1 && (
          <div className="h-[6.5rem]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={provenanceData}
                  dataKey="value"
                  nameKey="name"
                  cx="34%"
                  cy="50%"
                  innerRadius={24}
                  outerRadius={42}
                  paddingAngle={2}
                >
                  {provenanceData.map((entry) => (
                    <Cell key={entry.name} fill={entry.colour} />
                  ))}
                </Pie>
                <Legend
                  layout="vertical"
                  align="right"
                  verticalAlign="middle"
                  iconSize={8}
                  wrapperStyle={{ fontSize: 10, lineHeight: '1.3' }}
                />
                <Tooltip
                  contentStyle={{
                    background: 'rgb(var(--surface-raised))',
                    border: '1px solid rgb(var(--line))',
                    borderRadius: 10,
                    fontSize: 11,
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <Table head={['Requirement', 'Category', 'Source', 'In adverts', 'Importance']}>
        {skills.map((skill) => (
          <tr key={skill.canonical}>
            <Td>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-semibold">{skill.canonical}</span>
                {skill.essential && <Badge tone="danger">essential</Badge>}
                {skill.surface_forms.length > 1 && (
                  <span
                    className="badge-neutral"
                    title={`Merged from: ${skill.surface_forms.join(', ')}`}
                  >
                    {skill.surface_forms.length} variants
                  </span>
                )}
              </div>
            </Td>
            <Td>
              <span className="inline-flex items-center gap-1.5 text-xs text-ink-muted">
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: categoryColour(skill.category) }}
                  aria-hidden
                />
                {skill.category}
              </span>
            </Td>
            <Td>
              <Badge
                tone={skill.provenance === 'both' ? 'ok' : skill.provenance === 'scraped' ? 'info' : 'brand'}
                title={
                  skill.example_sources.length ? `Seen on: ${skill.example_sources.join(', ')}` : undefined
                }
              >
                {provenanceLabel(skill.provenance)}
              </Badge>
            </Td>
            <Td className="mono text-xs">
              {skill.posting_count > 0
                ? `${skill.posting_count} / ${requirements.stats.postings_collected}`
                : '—'}
            </Td>
            <Td>
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-14 overflow-hidden rounded-full bg-surface-muted">
                  <div
                    className="h-full rounded-full bg-brand-600"
                    style={{ width: `${Math.min(100, skill.importance * 100)}%` }}
                  />
                </div>
                <span className="mono text-xs text-ink-muted">{skill.importance.toFixed(2)}</span>
              </div>
            </Td>
          </tr>
        ))}
      </Table>
    </>
  );
}

function PostingsTab({ requirements }: { requirements: RoleRequirements }) {
  if (!requirements.postings.length) {
    return (
      <EmptyState
        icon={Globe}
        title="No live postings were collected"
        description="This happens when the job boards have nothing matching the title, or when they could not be reached. Check the Source report tab for exactly what each source returned."
      />
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-muted">
        {requirements.postings.length} live postings, de-duplicated across sources and filtered for
        relevance to the title you entered.
      </p>
      {requirements.postings.map((posting, index) => (
        <Collapsible
          key={`${posting.url}-${index}`}
          title={posting.title}
          subtitle={`${posting.company || 'Company not stated'}${posting.location ? ` · ${posting.location}` : ''} · via ${posting.source}`}
          badge={<Badge tone="neutral">{posting.skills.length} skills found</Badge>}
        >
          <div className="space-y-3">
            {posting.skills.length > 0 && (
              <div>
                <p className="label">Skills extracted from this advert</p>
                <div className="flex flex-wrap gap-1">
                  {posting.skills.map((skill) => (
                    <Badge key={skill} tone="neutral">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            {posting.description && (
              <div>
                <p className="label">Advert text (as collected)</p>
                <p className="max-h-56 overflow-y-auto whitespace-pre-line rounded-lg bg-surface p-3 text-xs leading-relaxed text-ink-muted">
                  {truncate(posting.description, 2200)}
                </p>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-3 text-xs text-ink-faint">
              {posting.posted_at && <span>Posted {posting.posted_at.slice(0, 10)}</span>}
              {posting.url && (
                <a
                  href={posting.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="link inline-flex items-center gap-1"
                >
                  <ExternalLink size={11} aria-hidden /> View original posting
                </a>
              )}
            </div>
          </div>
        </Collapsible>
      ))}
    </div>
  );
}

function SourcesTab({ reports }: { reports: SourceReport[] }) {
  const statusTone = (status: string) =>
    status === 'ok' ? 'ok' : status.startsWith('no_') ? 'neutral' : 'danger';

  return (
    <>
      <p className="mb-4 text-sm text-ink-muted">
        Exactly what each source returned, including failures. Nothing here is inferred — a source
        that failed is reported as failed.
      </p>
      <Table head={['Source', 'Type', 'Outcome', 'Returned', 'Kept', 'Time', 'Detail']}>
        {reports.map((report) => (
          <tr key={report.name}>
            <Td className="font-semibold">{report.name}</Td>
            <Td>
              <Badge tone={report.source_type === 'rss_scrape' ? 'info' : 'neutral'}>
                {report.source_type === 'rss_scrape' ? 'RSS scrape' : 'JSON API'}
              </Badge>
            </Td>
            <Td>
              <Badge tone={statusTone(report.status)}>
                {report.status === 'ok' ? (
                  <CheckCircle2 size={10} aria-hidden />
                ) : statusTone(report.status) === 'danger' ? (
                  <XCircle size={10} aria-hidden />
                ) : (
                  <AlertTriangle size={10} aria-hidden />
                )}
                {report.status.replace(/_/g, ' ')}
              </Badge>
            </Td>
            <Td className="mono text-xs">{report.postings_found}</Td>
            <Td className="mono text-xs font-semibold">{report.postings_kept}</Td>
            <Td className="mono text-xs">
              {ms(report.elapsed_ms)}
              {report.from_cache && (
                <Badge tone="neutral" className="ml-1">
                  cached
                </Badge>
              )}
            </Td>
            <Td className="max-w-[18rem] text-xs text-ink-muted">{report.detail || '—'}</Td>
          </tr>
        ))}
      </Table>
    </>
  );
}

function MergeTab({ requirements }: { requirements: RoleRequirements }) {
  const filtering = requirements.filtering;

  if (!requirements.merge_evidence.length && !filtering?.dropped_uncorroborated) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="No variant spellings needed merging"
        description="Every requirement arrived in a single consistent form from both sources."
      />
    );
  }

  return (
    <>
      <p className="mb-4 text-sm text-ink-muted">
        Different spellings of the same skill, collapsed into one requirement. The stage column shows
        which layer of the normaliser made the decision — exact alias lookup, fuzzy token matching,
        TF-IDF character n-gram similarity, or clustering of unknown terms.
      </p>
      <Table head={['Canonical requirement', 'Spellings merged', 'Stage', 'Source', 'In adverts']}>
        {requirements.merge_evidence.map((row) => (
          <tr key={row.canonical}>
            <Td className="font-semibold">{row.canonical}</Td>
            <Td className="text-ink-muted">{row.variants.join(' · ')}</Td>
            <Td>
              <Badge tone="brand">{row.stage}</Badge>
            </Td>
            <Td>
              <Badge tone={row.provenance === 'both' ? 'ok' : 'neutral'}>
                {provenanceLabel(row.provenance)}
              </Badge>
            </Td>
            <Td className="mono text-xs">{row.posting_count || '—'}</Td>
          </tr>
        ))}
      </Table>

      {filtering && filtering.dropped_uncorroborated > 0 && (
        <Collapsible
          title="Skills dropped as uncorroborated"
          subtitle="Mentioned by a single advert and not named by the language model"
          className="mt-4"
          badge={<Badge tone="warn">{filtering.dropped_uncorroborated} dropped</Badge>}
        >
          <p className="mb-3 text-[0.8125rem] leading-relaxed text-ink-muted">{filtering.rule}</p>
          <p className="text-[0.8125rem] text-ink-muted">
            {filtering.candidates_considered} candidate skills were found in total and{' '}
            {filtering.requirements_kept} were kept. Dropping the long tail matters: a skill one
            advert happened to mention is not a requirement of the role, and counting it would make
            every candidate's gap score look worse for no real reason.
          </p>
          {filtering.dropped_examples.length > 0 && (
            <div className="mt-3">
              <p className="label">Examples of what was dropped</p>
              <div className="flex flex-wrap gap-1">
                {filtering.dropped_examples.map((skill) => (
                  <Badge key={skill} tone="neutral">
                    {skill}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </Collapsible>
      )}
    </>
  );
}

/**
 * Page 2 - CV Analysis (Module 1).
 *
 * Shows the user exactly what the parser extracted AND what it refused to
 * accept. The `rejected_claims` panel is deliberately prominent: it is the
 * visible proof that the LLM's output is filtered against the document rather
 * than trusted, which is the main hallucination defence in this module.
 */

import {
  AlertTriangle,
  Award,
  Briefcase,
  CheckCircle2,
  Eye,
  FileText,
  FolderOpen,
  GraduationCap,
  Languages,
  Link2,
  Mail,
  MapPin,
  Phone,
  ShieldCheck,
  Sparkles,
  Target,
  Trash2,
  Upload,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import {
  Badge,
  Button,
  Card,
  CardHeader,
  Collapsible,
  EmptyState,
  ErrorState,
  Loading,
  Modal,
  Notice,
  PageHeader,
  Table,
  Tabs,
  Td,
} from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { ApiFailure, cvApi } from '../lib/api';
import { bytes, categoryColour, relativeTime, titleCase } from '../lib/format';
import { useApp } from '../lib/store';
import type { CVUploadResponse } from '../lib/types';

type Tab = 'skills' | 'experience' | 'education' | 'projects' | 'other' | 'raw';

export default function CVAnalysis() {
  const { cvId } = useParams();
  const navigate = useNavigate();
  const { notify, setCv, selection } = useApp();

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [current, setCurrent] = useState<CVUploadResponse | null>(null);
  const [tab, setTab] = useState<Tab>('skills');
  const [rawText, setRawText] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const limits = useAsync(() => cvApi.limits(), []);
  const list = useAsync(() => cvApi.list(25), []);
  const detail = useAsync(async () => (cvId ? cvApi.get(cvId) : null), [cvId]);

  useEffect(() => {
    if (detail.data) {
      setCurrent(detail.data);
      setTab('skills');
    }
  }, [detail.data]);

  const upload = useCallback(
    async (file: File) => {
      setUploading(true);
      setUploadError(null);
      try {
        const result = await cvApi.upload(file);
        setCurrent(result);
        setCv(result.cv_id, result.filename);
        setTab('skills');
        list.reload();
        notify({
          tone: 'ok',
          title: 'CV parsed',
          message: `${result.profile.skill_count} skills, ${result.profile.experience.length} roles, ${result.profile.projects.length} projects extracted.`,
        });
        navigate(`/cv/${result.cv_id}`, { replace: true });
      } catch (caught: unknown) {
        const message =
          caught instanceof ApiFailure ? caught.message : 'The upload failed unexpectedly.';
        setUploadError(message);
        notify({ tone: 'danger', title: 'Could not parse that CV', message });
      } finally {
        setUploading(false);
      }
    },
    [notify, setCv, list, navigate],
  );

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setDragging(false);
      const file = event.dataTransfer.files?.[0];
      if (file) void upload(file);
    },
    [upload],
  );

  const openRaw = useCallback(async () => {
    if (!current) return;
    setShowRaw(true);
    if (rawText === null) {
      try {
        const result = await cvApi.text(current.cv_id);
        setRawText(result.text);
      } catch {
        setRawText('The extracted text could not be loaded.');
      }
    }
  }, [current, rawText]);

  const remove = useCallback(
    async (id: string) => {
      try {
        await cvApi.remove(id);
        notify({ tone: 'ok', title: 'CV deleted' });
        if (current?.cv_id === id) {
          setCurrent(null);
          navigate('/cv', { replace: true });
        }
        list.reload();
      } catch (caught: unknown) {
        notify({
          tone: 'danger',
          title: 'Could not delete',
          message: caught instanceof ApiFailure ? caught.message : undefined,
        });
      }
    },
    [current, list, navigate, notify],
  );

  const profile = current?.profile;

  return (
    <>
      <PageHeader
        title="CV Analysis"
        description="Upload a PDF or Word CV. The parser extracts your skills, roles, education, projects and certifications into structured data — and shows you anything it refused to accept."
        badge={profile && <Badge tone="brand">{profile.parse_mode}</Badge>}
        actions={
          current && (
            <>
              <Button variant="secondary" icon={Eye} onClick={openRaw}>
                Extracted text
              </Button>
              <Link to="/roles">
                <Button variant="primary" icon={Target}>
                  Analyse a role next
                </Button>
              </Link>
            </>
          )
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1fr_20rem]">
        <div className="min-w-0 space-y-6">
          {/* ------------------------------------------------------ upload -- */}
          {!current && (
            <Card>
              <div className="card-pad">
                <div
                  onDragOver={(event) => {
                    event.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={onDrop}
                  className={`rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-colors ${
                    dragging ? 'border-brand-500 bg-brand-500/8' : 'border-line bg-surface-muted/40'
                  }`}
                >
                  <span className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-brand-500/12 text-brand-600">
                    <Upload size={24} aria-hidden />
                  </span>
                  <h2 className="text-base font-semibold text-ink">Drop your CV here</h2>
                  <p className="mx-auto mt-1.5 max-w-sm text-sm text-ink-muted text-pretty">
                    PDF or Word (.docx), up to {limits.data?.max_upload_mb ?? 5} MB. Your file stays on
                    this machine.
                  </p>
                  <div className="mt-5">
                    <Button
                      variant="primary"
                      icon={FileText}
                      loading={uploading}
                      onClick={() => fileRef.current?.click()}
                    >
                      {uploading ? 'Parsing…' : 'Choose a file'}
                    </Button>
                  </div>
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".pdf,.docx,.txt"
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) void upload(file);
                      event.target.value = '';
                    }}
                  />
                </div>

                {uploadError && (
                  <Notice tone="danger" title="Upload rejected" className="mt-4">
                    {uploadError}
                  </Notice>
                )}

                {limits.data && (
                  <ul className="mt-4 space-y-1 text-xs text-ink-faint">
                    {limits.data.notes.map((note) => (
                      <li key={note} className="flex gap-1.5">
                        <span aria-hidden>·</span>
                        {note}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Card>
          )}

          {detail.loading && cvId && <Loading label="Loading CV…" />}
          {detail.error && cvId && (
            <ErrorState title="Could not load that CV" message={detail.error} onRetry={detail.reload} />
          )}

          {/* ----------------------------------------------------- profile -- */}
          {profile && current && (
            <>
              <Card>
                <CardHeader
                  title={profile.full_name || 'Name not detected'}
                  subtitle={
                    profile.headline ||
                    `${current.filename} · ${bytes(current.size_bytes)} · ${current.char_count.toLocaleString()} characters extracted with ${current.extractor}`
                  }
                  icon={FileText}
                  actions={
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={Upload}
                      onClick={() => {
                        setCurrent(null);
                        navigate('/cv', { replace: true });
                      }}
                    >
                      New upload
                    </Button>
                  }
                />
                <div className="card-pad">
                  <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {[
                      { icon: Mail, label: 'Email', value: profile.email },
                      { icon: Phone, label: 'Phone', value: profile.phone },
                      { icon: MapPin, label: 'Location', value: profile.location },
                      {
                        icon: Briefcase,
                        label: 'Experience',
                        value:
                          profile.total_years_experience !== null
                            ? `${profile.total_years_experience} years (stated)`
                            : '',
                      },
                    ].map((item) => (
                      <div key={item.label} className="min-w-0">
                        <dt className="flex items-center gap-1.5 text-[0.6875rem] font-semibold uppercase tracking-wide text-ink-muted">
                          <item.icon size={11} aria-hidden /> {item.label}
                        </dt>
                        <dd
                          className={`mt-0.5 truncate text-sm ${item.value ? 'font-medium text-ink' : 'text-ink-faint'}`}
                          title={item.value || undefined}
                        >
                          {item.value || 'not found'}
                        </dd>
                      </div>
                    ))}
                  </dl>

                  {profile.links.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {profile.links.map((link) => (
                        <a
                          key={link}
                          href={link.startsWith('http') ? link : `https://${link}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="badge-neutral hover:text-brand-600"
                        >
                          <Link2 size={11} aria-hidden /> {link.replace(/^https?:\/\/(www\.)?/, '').slice(0, 42)}
                        </a>
                      ))}
                    </div>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-4">
                    {[
                      { label: 'skills', count: profile.skills.length },
                      { label: 'roles', count: profile.experience.length },
                      { label: 'projects', count: profile.projects.length },
                      { label: 'education', count: profile.education.length },
                      { label: 'certifications', count: profile.certifications.length },
                      { label: 'improvable bullets', count: profile.all_bullets.length },
                    ].map((item) => (
                      <Badge key={item.label} tone={item.count > 0 ? 'brand' : 'neutral'}>
                        {item.count} {item.label}
                      </Badge>
                    ))}
                  </div>
                </div>
              </Card>

              {/* honesty panels */}
              {(current.extraction_warnings.length > 0 || profile.warnings.length > 0) && (
                <Notice tone="warn" title="Parsing notes">
                  <ul className="mt-1 space-y-1">
                    {[...current.extraction_warnings, ...profile.warnings].map((warning, index) => (
                      <li key={index} className="flex gap-1.5">
                        <span aria-hidden>·</span>
                        {warning}
                      </li>
                    ))}
                  </ul>
                </Notice>
              )}

              {profile.rejected_claims.length > 0 && (
                <Card>
                  <CardHeader
                    title="Claims rejected by the grounding filter"
                    subtitle="The language model proposed these, but they do not appear in your CV text, so they were discarded rather than shown as fact"
                    icon={ShieldCheck}
                    actions={<Badge tone="danger">{profile.rejected_claims.length} dropped</Badge>}
                  />
                  <Table head={['Field', 'Proposed value', 'Why it was dropped']}>
                    {profile.rejected_claims.map((claim, index) => (
                      <tr key={index}>
                        <Td>
                          <Badge tone="neutral">{titleCase(claim.field)}</Badge>
                        </Td>
                        <Td className="font-medium">{claim.value}</Td>
                        <Td className="text-ink-muted">{claim.reason}</Td>
                      </tr>
                    ))}
                  </Table>
                </Card>
              )}

              {/* tabs */}
              <Card>
                <div className="card-pad pb-0">
                  <Tabs<Tab>
                    active={tab}
                    onChange={setTab}
                    tabs={[
                      { key: 'skills', label: 'Skills', count: profile.skills.length, icon: Sparkles },
                      { key: 'experience', label: 'Experience', count: profile.experience.length, icon: Briefcase },
                      { key: 'education', label: 'Education', count: profile.education.length, icon: GraduationCap },
                      { key: 'projects', label: 'Projects', count: profile.projects.length, icon: FolderOpen },
                      { key: 'other', label: 'Other', icon: Award },
                      { key: 'raw', label: 'Bullets', count: profile.all_bullets.length, icon: FileText },
                    ]}
                  />
                </div>

                <div className="card-pad">
                  {tab === 'skills' && <SkillsTab profile={profile} />}
                  {tab === 'experience' && <ExperienceTab profile={profile} />}
                  {tab === 'education' && <EducationTab profile={profile} />}
                  {tab === 'projects' && <ProjectsTab profile={profile} />}
                  {tab === 'other' && <OtherTab profile={profile} />}
                  {tab === 'raw' && <BulletsTab current={current} />}
                </div>
              </Card>
            </>
          )}
        </div>

        {/* --------------------------------------------------- CV library -- */}
        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Your CVs"
              subtitle={`${list.data?.count ?? 0} stored locally`}
              icon={FolderOpen}
            />
            {list.loading ? (
              <div className="card-pad space-y-2">
                <div className="skeleton h-14" />
                <div className="skeleton h-14" />
              </div>
            ) : list.data && list.data.items.length > 0 ? (
              <ul className="divide-y divide-line">
                {list.data.items.map((item) => (
                  <li
                    key={item.cv_id}
                    className={`flex items-start gap-2 px-4 py-3 ${
                      item.cv_id === current?.cv_id ? 'bg-brand-500/8' : ''
                    }`}
                  >
                    <Link to={`/cv/${item.cv_id}`} className="min-w-0 flex-1">
                      <p className="truncate text-[0.8125rem] font-semibold text-ink">{item.filename}</p>
                      <p className="truncate text-xs text-ink-muted">
                        {item.full_name || 'name not detected'} · {item.skill_count} skills
                      </p>
                      <p className="text-[0.6875rem] text-ink-faint">{relativeTime(item.created_at)}</p>
                    </Link>
                    <div className="flex shrink-0 flex-col gap-1">
                      {selection.cvId === item.cv_id && <Badge tone="brand">active</Badge>}
                      <button
                        type="button"
                        onClick={() => void remove(item.cv_id)}
                        className="rounded-md p-1 text-ink-faint transition-colors hover:bg-surface-muted hover:text-[rgb(var(--danger))]"
                        aria-label={`Delete ${item.filename}`}
                        title="Delete"
                      >
                        <Trash2 size={13} aria-hidden />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="card-pad text-sm text-ink-muted">No CVs uploaded yet.</p>
            )}
          </Card>

          <Card>
            <CardHeader title="How parsing works" icon={ShieldCheck} />
            <div className="card-pad space-y-3 text-[0.8125rem] leading-relaxed text-ink-muted">
              <p>
                <span className="font-semibold text-ink">1. Text extraction.</span> pdfplumber reads
                PDFs (with pypdf as a fallback) and python-docx reads Word files, including content
                hidden in tables and headers.
              </p>
              <p>
                <span className="font-semibold text-ink">2. Rule-based parsing.</span> Section
                headings, contact patterns and bullet lines are found with deterministic rules, then
                skills are matched against a curated taxonomy.
              </p>
              <p>
                <span className="font-semibold text-ink">3. LLM refinement.</span> A language model
                reads the same text and may fill gaps the rules missed.
              </p>
              <p>
                <span className="font-semibold text-ink">4. Grounding filter.</span> Every value the
                model supplies is checked against the document. Anything unsupported is dropped and
                listed above, so nothing invented reaches your profile.
              </p>
            </div>
          </Card>
        </div>
      </div>

      <Modal
        open={showRaw}
        onClose={() => setShowRaw(false)}
        title="Text extracted from your CV"
        width="max-w-3xl"
        footer={
          <Button variant="secondary" onClick={() => setShowRaw(false)}>
            Close
          </Button>
        }
      >
        <p className="mb-3 text-xs text-ink-muted">
          This is exactly what the parser read. If something is missing from your profile, it is
          usually missing here too — which points at the document rather than the parser.
        </p>
        <pre className="mono whitespace-pre-wrap rounded-xl bg-surface-muted p-4 text-ink">
          {rawText ?? 'Loading…'}
        </pre>
      </Modal>
    </>
  );
}

/* ------------------------------------------------------------------ tabs -- */

function SkillsTab({ profile }: { profile: CVUploadResponse['profile'] }) {
  if (!profile.skills.length) {
    return (
      <EmptyState
        icon={Sparkles}
        title="No skills extracted"
        description="Add a clearly headed 'Skills' section to your CV, listing technologies separated by commas, and upload it again."
      />
    );
  }

  const byCategory = profile.skills.reduce<Record<string, typeof profile.skills>>((acc, skill) => {
    (acc[skill.category] ??= []).push(skill);
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      {Object.entries(byCategory)
        .sort((a, b) => b[1].length - a[1].length)
        .map(([category, skills]) => (
          <div key={category}>
            <p className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-ink-muted">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: categoryColour(category) }}
                aria-hidden
              />
              {category}
              <span className="font-semibold text-ink-faint">({skills.length})</span>
            </p>
            <div className="flex flex-wrap gap-1.5">
              {skills.map((skill) => (
                <span
                  key={skill.canonical}
                  className="group inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink"
                  title={
                    skill.surface_forms.length > 1
                      ? `Merged from: ${skill.surface_forms.join(', ')} (${skill.stage})`
                      : `Matched by ${skill.stage}`
                  }
                >
                  {skill.canonical}
                  {skill.surface_forms.length > 1 && (
                    <span className="rounded-full bg-brand-500/15 px-1 text-[0.625rem] font-bold text-brand-700">
                      {skill.surface_forms.length}
                    </span>
                  )}
                  {!skill.in_taxonomy && (
                    <span className="text-[0.625rem] text-ink-faint" title="Not in the curated taxonomy">
                      new
                    </span>
                  )}
                </span>
              ))}
            </div>
          </div>
        ))}

      {profile.skills.some((s) => s.surface_forms.length > 1) && (
        <Collapsible
          title="Skill normalisation evidence"
          subtitle="Which spellings were merged into one skill, and which stage decided it"
          badge={
            <Badge tone="brand">
              {profile.skills.filter((s) => s.surface_forms.length > 1).length} merged
            </Badge>
          }
        >
          <Table head={['Canonical skill', 'Merged from', 'Stage', 'Confidence']} dense>
            {profile.skills
              .filter((s) => s.surface_forms.length > 1)
              .map((skill) => (
                <tr key={skill.canonical}>
                  <Td dense className="font-semibold">
                    {skill.canonical}
                  </Td>
                  <Td dense className="text-ink-muted">
                    {skill.surface_forms.join(' · ')}
                  </Td>
                  <Td dense>
                    <Badge tone="neutral">{skill.stage}</Badge>
                  </Td>
                  <Td dense className="mono">
                    {skill.confidence.toFixed(2)}
                  </Td>
                </tr>
              ))}
          </Table>
        </Collapsible>
      )}
    </div>
  );
}

function ExperienceTab({ profile }: { profile: CVUploadResponse['profile'] }) {
  if (!profile.experience.length) {
    return (
      <EmptyState
        icon={Briefcase}
        title="No work experience found"
        description="The parser looks for a heading such as 'Experience' or 'Employment History', followed by job titles and bullet points."
      />
    );
  }

  return (
    <ol className="space-y-4">
      {profile.experience.map((job, index) => (
        <li key={index} className="relative border-l-2 border-line pl-5">
          <span
            className="absolute -left-[0.3125rem] top-1.5 h-2 w-2 rounded-full bg-brand-600"
            aria-hidden
          />
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-sm font-bold text-ink">{job.job_title || 'Role title not detected'}</h3>
            {(job.start || job.end) && (
              <span className="mono text-xs text-ink-faint">
                {job.start} {job.start && job.end ? '–' : ''} {job.end}
              </span>
            )}
          </div>
          {(job.company || job.location) && (
            <p className="mt-0.5 text-[0.8125rem] text-ink-muted">
              {job.company}
              {job.company && job.location ? ' · ' : ''}
              {job.location}
            </p>
          )}
          {job.bullets.length > 0 && (
            <ul className="mt-2 space-y-1.5">
              {job.bullets.map((bullet, bulletIndex) => (
                <li key={bulletIndex} className="flex gap-2 text-[0.8125rem] leading-relaxed text-ink">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-faint" aria-hidden />
                  {bullet}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}

function EducationTab({ profile }: { profile: CVUploadResponse['profile'] }) {
  if (!profile.education.length) {
    return <EmptyState icon={GraduationCap} title="No education entries found" />;
  }
  return (
    <Table head={['Qualification', 'Field', 'Institution', 'Period', 'Grade']}>
      {profile.education.map((entry, index) => (
        <tr key={index}>
          <Td className="font-semibold">{entry.degree || '—'}</Td>
          <Td>{entry.field || '—'}</Td>
          <Td className="text-ink-muted">{entry.institution || '—'}</Td>
          <Td className="mono text-xs">
            {entry.start} {entry.start && entry.end ? '–' : ''} {entry.end || '—'}
          </Td>
          <Td className="mono text-xs">{entry.grade || '—'}</Td>
        </tr>
      ))}
    </Table>
  );
}

function ProjectsTab({ profile }: { profile: CVUploadResponse['profile'] }) {
  if (!profile.projects.length) {
    return (
      <EmptyState
        icon={FolderOpen}
        title="No projects found"
        description="A 'Projects' heading with a name per project, and optionally a 'Technologies:' line, parses best."
      />
    );
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {profile.projects.map((project, index) => (
        <div key={index} className="rounded-xl border border-line p-4">
          <h3 className="text-sm font-bold text-ink">{project.name}</h3>
          {project.description && (
            <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-ink-muted">
              {project.description.slice(0, 300)}
              {project.description.length > 300 ? '…' : ''}
            </p>
          )}
          {project.technologies.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1">
              {project.technologies.map((tech) => (
                <Badge key={tech} tone="neutral">
                  {tech}
                </Badge>
              ))}
            </div>
          )}
          {project.link && (
            <a
              href={project.link.startsWith('http') ? project.link : `https://${project.link}`}
              target="_blank"
              rel="noopener noreferrer"
              className="link mt-2 inline-flex items-center gap-1 text-xs"
            >
              <Link2 size={11} aria-hidden /> {project.link.slice(0, 44)}
            </a>
          )}
        </div>
      ))}
    </div>
  );
}

function OtherTab({ profile }: { profile: CVUploadResponse['profile'] }) {
  const empty =
    !profile.certifications.length && !profile.languages.length && !profile.job_roles.length;
  if (empty) {
    return <EmptyState icon={Award} title="No certifications, languages or job titles detected" />;
  }

  return (
    <div className="space-y-5">
      {profile.certifications.length > 0 && (
        <div>
          <p className="label flex items-center gap-1.5">
            <Award size={12} aria-hidden /> Certifications
          </p>
          <Table head={['Certification', 'Issuer', 'Year']} dense>
            {profile.certifications.map((cert, index) => (
              <tr key={index}>
                <Td dense className="font-medium">
                  {cert.name}
                </Td>
                <Td dense className="text-ink-muted">
                  {cert.issuer || '—'}
                </Td>
                <Td dense className="mono text-xs">
                  {cert.year || '—'}
                </Td>
              </tr>
            ))}
          </Table>
        </div>
      )}

      {profile.job_roles.length > 0 && (
        <div>
          <p className="label flex items-center gap-1.5">
            <Briefcase size={12} aria-hidden /> Job titles held
          </p>
          <div className="flex flex-wrap gap-1.5">
            {profile.job_roles.map((role) => (
              <Badge key={role} tone="brand">
                {role}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {profile.languages.length > 0 && (
        <div>
          <p className="label flex items-center gap-1.5">
            <Languages size={12} aria-hidden /> Languages
          </p>
          <div className="flex flex-wrap gap-1.5">
            {profile.languages.map((language) => (
              <Badge key={language} tone="neutral">
                {language}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {profile.sections_found.length > 0 && (
        <div>
          <p className="label">Sections identified in the document</p>
          <div className="flex flex-wrap gap-1.5">
            {profile.sections_found.map((section) => (
              <Badge key={section} tone="neutral">
                <CheckCircle2 size={10} aria-hidden /> {titleCase(section)}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function BulletsTab({ current }: { current: CVUploadResponse }) {
  if (!current.bullet_ranking.length) {
    return (
      <EmptyState
        icon={FileText}
        title="No improvable bullet points found"
        description="Bullet points come from your experience section and project descriptions."
      />
    );
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-muted">
          Ranked weakest first. The CV Improvement Studio rewrites these without inventing anything.
        </p>
        <Link to="/improve">
          <Button variant="primary" size="sm" icon={Sparkles}>
            Open Improvement Studio
          </Button>
        </Link>
      </div>
      <ul className="space-y-2">
        {current.bullet_ranking.map((bullet) => (
          <li key={bullet.index} className="rounded-xl border border-line p-3">
            <p className="text-[0.8125rem] leading-relaxed text-ink">{bullet.text}</p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <Badge tone={bullet.weakness_score >= 3 ? 'danger' : bullet.weakness_score >= 1 ? 'warn' : 'ok'}>
                {bullet.weakness_score === 0 ? (
                  <>
                    <CheckCircle2 size={10} aria-hidden /> looks strong
                  </>
                ) : (
                  <>
                    <AlertTriangle size={10} aria-hidden /> {bullet.weakness_score} issue
                    {bullet.weakness_score === 1 ? '' : 's'}
                  </>
                )}
              </Badge>
              {bullet.weakness_signals.map((signal) => (
                <Badge key={signal} tone="neutral">
                  {signal}
                </Badge>
              ))}
              <span className="ml-auto text-[0.6875rem] text-ink-faint">{bullet.word_count} words</span>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

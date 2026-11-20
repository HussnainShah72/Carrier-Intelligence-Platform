/**
 * Page 5 - CV Improvement Studio (Module 4).
 *
 * Side-by-side original and rewrite, with accept / reject / copy per bullet.
 * A rejected rewrite is shown as rejected, with the reason: the guard catching
 * an invented metric is the feature, so hiding it would waste the one piece of
 * evidence that the tool is safe to trust with a real CV.
 */

import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  Copy,
  FileText,
  Info,
  PenLine,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Undo2,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Field,
  Loading,
  Notice,
  PageHeader,
  Select,
  StatTile,
  Table,
  Td,
} from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { ApiFailure, cvApi, improveApi, roleApi } from '../lib/api';
import { copyToClipboard, downloadFile, ms, titleCase } from '../lib/format';
import { useApp } from '../lib/store';
import type { BulletImprovement, ImproveResponse } from '../lib/types';

const MAX_SELECTED = 12;

const REJECTION_LABELS: Record<string, string> = {
  invented_metric: 'Invented a metric',
  invented_technology: 'Invented a technology',
  escalated_scope: 'Escalated your role',
  empty_rewrite: 'No rewrite returned',
  rewrite_too_long: 'Rewrite far too long',
};

export default function Improve() {
  const { notify, selection, setCv } = useApp();

  const [cvId, setCvId] = useState(selection.cvId);
  const [roleTitle, setRoleTitle] = useState(selection.roleLabel);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [response, setResponse] = useState<ImproveResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, 'accepted' | 'rejected'>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const cvs = useAsync(() => cvApi.list(50), []);
  const roles = useAsync(() => roleApi.list(50), []);
  const cv = useAsync(async () => (cvId ? cvApi.get(cvId) : null), [cvId]);

  const ranking = useMemo(() => cv.data?.bullet_ranking ?? [], [cv.data]);

  useEffect(() => {
    // Pre-select the weakest bullets, capped at what one request allows.
    if (ranking.length) {
      setSelected(new Set(ranking.slice(0, Math.min(6, MAX_SELECTED)).map((bullet) => bullet.index)));
      setResponse(null);
      setDecisions({});
    }
  }, [ranking]);

  const toggle = useCallback((index: number) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else if (next.size < MAX_SELECTED) next.add(index);
      return next;
    });
  }, []);

  const run = useCallback(async () => {
    const bullets = ranking.filter((bullet) => selected.has(bullet.index)).map((bullet) => bullet.text);
    if (!bullets.length) {
      setRunError('Select at least one bullet point to improve.');
      return;
    }
    setRunning(true);
    setRunError(null);
    try {
      const result = await improveApi.bullets(bullets, roleTitle, cvId);
      setResponse(result);
      setDecisions({});
      notify({
        tone: result.summary.rejected > 0 ? 'warn' : 'ok',
        title: `${result.summary.accepted} of ${result.summary.requested} rewrites accepted`,
        message:
          result.summary.rejected > 0
            ? `${result.summary.rejected} rejected by the invention guard — your originals were kept.`
            : 'All rewrites passed the invention checks.',
      });
    } catch (caught: unknown) {
      const message = caught instanceof ApiFailure ? caught.message : 'The rewrite failed.';
      setRunError(message);
      notify({ tone: 'danger', title: 'Could not improve bullets', message });
    } finally {
      setRunning(false);
    }
  }, [ranking, selected, roleTitle, cvId, notify]);

  const decide = useCallback(
    async (improvement: BulletImprovement, decision: 'accepted' | 'rejected') => {
      setDecisions((current) => ({ ...current, [improvement.id]: decision }));
      try {
        await improveApi.decide(improvement.id, decision);
      } catch {
        // The decision is a local preference; a failed sync is not worth an error.
      }
    },
    [],
  );

  const copy = useCallback(
    async (improvement: BulletImprovement) => {
      const ok = await copyToClipboard(improvement.accepted ? improvement.improved : improvement.original);
      setCopiedId(ok ? improvement.id : null);
      if (ok) setTimeout(() => setCopiedId(null), 1800);
      notify(
        ok
          ? { tone: 'ok', title: 'Copied to clipboard' }
          : { tone: 'danger', title: 'Could not copy', message: 'Select the text and copy it manually.' },
      );
    },
    [notify],
  );

  const exportAccepted = useCallback(() => {
    if (!response) return;
    const lines = response.results.map((item) => {
      const useImproved = item.accepted && decisions[item.id] !== 'rejected';
      return `• ${useImproved ? item.improved : item.original}`;
    });
    downloadFile(
      `Improved CV bullet points${roleTitle ? ` — ${roleTitle}` : ''}\n` +
        `${'='.repeat(60)}\n\n${lines.join('\n\n')}\n\n` +
        `${'='.repeat(60)}\nGenerated by the Career Intelligence Platform. ` +
        `Rewrites are checked automatically for invented metrics, invented technologies and escalated scope.\n`,
      'improved-cv-bullets.txt',
    );
    notify({ tone: 'ok', title: 'Downloaded', message: 'improved-cv-bullets.txt' });
  }, [response, decisions, roleTitle, notify]);

  const accepted = response?.results.filter((item) => item.accepted && decisions[item.id] !== 'rejected').length ?? 0;

  return (
    <>
      <PageHeader
        title="CV Improvement Studio"
        description="Rewrites weak bullet points so they read professionally — without inventing a single metric, technology or responsibility you did not already claim."
        actions={
          response && (
            <>
              <Button variant="secondary" icon={FileText} onClick={exportAccepted}>
                Export bullets
              </Button>
              <Link to="/interview">
                <Button variant="primary" icon={ArrowRight}>
                  Practise interview
                </Button>
              </Link>
            </>
          )
        }
      />

      <Notice tone="info" title="How your experience is protected" className="mb-6">
        Every rewrite is checked automatically before you see it. A rewrite that introduces a number
        your original did not contain, names a technology absent from your CV, or upgrades "helped
        with" into "led" is <span className="font-semibold">rejected</span> and your original text is
        kept. Rejections are shown below with the reason, so you can see the guard working.
      </Notice>

      {/* --------------------------------------------------------- picker -- */}
      <Card className="mb-6">
        <div className="card-pad">
          <div className="grid gap-4 lg:grid-cols-[1fr_1fr_auto] lg:items-end">
            <Field label="Your CV" hint={`${cvs.data?.count ?? 0} available`}>
              <Select
                value={cvId}
                onChange={(value) => {
                  setCvId(value);
                  const match = cvs.data?.items.find((item) => item.cv_id === value);
                  if (match) setCv(value, match.filename);
                  setResponse(null);
                }}
                ariaLabel="Select CV"
                options={[
                  { value: '', label: cvs.data?.items.length ? 'Choose a CV…' : 'No CVs uploaded yet' },
                  ...(cvs.data?.items ?? []).map((item) => ({
                    value: item.cv_id,
                    label: item.filename,
                  })),
                ]}
              />
            </Field>
            <Field label="Target role" hint="Shapes the emphasis, but never adds new content">
              <Select
                value={roleTitle}
                onChange={setRoleTitle}
                ariaLabel="Target role"
                options={[
                  { value: '', label: 'No specific role' },
                  ...(roles.data?.items ?? []).map((item) => ({
                    value: item.role_title,
                    label: item.role_title,
                  })),
                ]}
              />
            </Field>
            <Button
              variant="primary"
              icon={Sparkles}
              loading={running}
              disabled={!selected.size || !cvId}
              onClick={() => void run()}
              className="h-[2.625rem]"
            >
              {running ? 'Rewriting…' : `Improve ${selected.size || ''} bullet${selected.size === 1 ? '' : 's'}`}
            </Button>
          </div>

          {!cvs.data?.items.length && !cvs.loading && (
            <Notice tone="info" className="mt-4">
              You need a parsed CV first.{' '}
              <Link to="/cv" className="link">
                Upload one
              </Link>
              .
            </Notice>
          )}
          {runError && (
            <Notice tone="danger" className="mt-4">
              {runError}
            </Notice>
          )}
        </div>
      </Card>

      {cv.loading && cvId && <Loading label="Loading bullet points…" />}

      {/* -------------------------------------------------------- results -- */}
      {response && (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Rewrites accepted" value={accepted} unit={`/ ${response.summary.requested}`} icon={CheckCircle2} tone="ok" />
            <StatTile
              label="Blocked by guard"
              value={response.summary.rejected}
              hint={
                Object.keys(response.summary.rejections_by_reason).length
                  ? Object.entries(response.summary.rejections_by_reason)
                      .map(([reason, count]) => `${count} ${REJECTION_LABELS[reason] ?? reason}`)
                      .join(', ')
                  : 'No inventions detected'
              }
              icon={ShieldCheck}
              tone={response.summary.rejected > 0 ? 'danger' : 'ok'}
            />
            <StatTile
              label="Already strong"
              value={response.summary.already_strong}
              hint="Left close to the original"
              icon={Check}
            />
            <StatTile
              label="Processing time"
              value={ms(response.summary.elapsed_ms)}
              hint={response.summary.engine}
              icon={Sparkles}
            />
          </div>

          {response.summary.degraded && (
            <Notice tone="warn" title="Rule-based rewrites" className="mb-6">
              No language model is configured, so rewrites came from deterministic rules (filler
              removal and verb strengthening). They are safe but much less fluent than an LLM rewrite.
            </Notice>
          )}

          <div className="space-y-4">
            {response.results.map((item, index) => (
              <ImprovementCard
                key={item.id}
                item={item}
                index={index}
                decision={decisions[item.id]}
                copied={copiedId === item.id}
                onDecide={decide}
                onCopy={copy}
              />
            ))}
          </div>

          <Card className="mt-6">
            <CardHeader title="What the guard checks" icon={ShieldCheck} />
            <div className="card-pad">
              <Table head={['Check', 'Rule', 'If it fails']} dense>
                {[
                  {
                    check: 'Numbers',
                    rule: 'Every numeric token in the rewrite must also appear in your original bullet.',
                    outcome: 'Rejected — the original is kept.',
                  },
                  {
                    check: 'Technologies',
                    rule: 'Every technology named in the rewrite must appear in the bullet or elsewhere in your CV.',
                    outcome: 'Rejected — the original is kept.',
                  },
                  {
                    check: 'Scope',
                    rule: 'Words like "led", "owned" or "architected" require matching evidence in the original.',
                    outcome: 'Rejected — the original is kept.',
                  },
                  {
                    check: 'New wording',
                    rule: 'Content words with no basis in your CV are counted.',
                    outcome: 'Warning shown — you decide.',
                  },
                ].map((row) => (
                  <tr key={row.check}>
                    <Td dense className="font-semibold">
                      {row.check}
                    </Td>
                    <Td dense className="text-ink-muted">
                      {row.rule}
                    </Td>
                    <Td dense className="text-ink-muted">
                      {row.outcome}
                    </Td>
                  </tr>
                ))}
              </Table>
            </div>
          </Card>
        </>
      )}

      {/* --------------------------------------------------- bullet picker -- */}
      {!response && cvId && (
        <Card>
          <CardHeader
            title="Choose bullet points to improve"
            subtitle={`Ranked weakest first · select up to ${MAX_SELECTED}`}
            icon={PenLine}
            actions={
              ranking.length > 0 && (
                <div className="flex items-center gap-2">
                  <Badge tone={selected.size >= MAX_SELECTED ? 'warn' : 'brand'}>
                    {selected.size} / {MAX_SELECTED} selected
                  </Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={RotateCcw}
                    onClick={() => setSelected(new Set())}
                    disabled={!selected.size}
                  >
                    Clear
                  </Button>
                </div>
              )
            }
          />
          {ranking.length > 0 ? (
            <ul className="divide-y divide-line">
              {ranking.map((bullet) => {
                const isSelected = selected.has(bullet.index);
                const atLimit = !isSelected && selected.size >= MAX_SELECTED;
                return (
                  <li key={bullet.index}>
                    <label
                      className={`flex cursor-pointer items-start gap-3 px-5 py-3 transition-colors ${
                        isSelected ? 'bg-brand-500/8' : atLimit ? 'opacity-50' : 'hover:bg-surface-muted'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        disabled={atLimit}
                        onChange={() => toggle(bullet.index)}
                        className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-brand-600"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-[0.8125rem] leading-relaxed text-ink">{bullet.text}</p>
                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                          {bullet.weakness_signals.length === 0 ? (
                            <Badge tone="ok">
                              <CheckCircle2 size={10} aria-hidden /> looks strong
                            </Badge>
                          ) : (
                            bullet.weakness_signals.map((signal) => (
                              <Badge key={signal} tone={bullet.weakness_score >= 3 ? 'danger' : 'warn'}>
                                {signal}
                              </Badge>
                            ))
                          )}
                          <span className="ml-auto text-[0.6875rem] text-ink-faint">
                            {bullet.word_count} words
                          </span>
                        </div>
                      </div>
                    </label>
                  </li>
                );
              })}
            </ul>
          ) : (
            <EmptyState
              icon={PenLine}
              title="No bullet points found in this CV"
              description="Bullet points come from your experience section and project descriptions. Add bulleted achievements under each role and upload the CV again."
              action={
                <Link to="/cv">
                  <Button variant="secondary" icon={FileText}>
                    Back to CV Analysis
                  </Button>
                </Link>
              }
            />
          )}
        </Card>
      )}

      {!cvId && !cvs.loading && (
        <Card>
          <EmptyState
            icon={PenLine}
            title="Select a CV to begin"
            description="Choose one of your parsed CVs above. The studio ranks your bullet points by how weak they look, then rewrites the ones you pick."
          />
        </Card>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ card -- */

function ImprovementCard({
  item,
  index,
  decision,
  copied,
  onDecide,
  onCopy,
}: {
  item: BulletImprovement;
  index: number;
  decision?: 'accepted' | 'rejected';
  copied: boolean;
  onDecide: (item: BulletImprovement, decision: 'accepted' | 'rejected') => void;
  onCopy: (item: BulletImprovement) => void;
}) {
  const blocking = item.flags.filter((flag) => flag.severity === 'blocking');
  const warnings = item.flags.filter((flag) => flag.severity === 'warning');

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3">
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-surface-muted text-xs font-bold text-ink-muted">
          {index + 1}
        </span>
        {item.accepted ? (
          item.already_strong ? (
            <Badge tone="info">
              <Check size={10} aria-hidden /> already strong
            </Badge>
          ) : (
            <Badge tone="ok">
              <CheckCircle2 size={10} aria-hidden /> rewrite passed all checks
            </Badge>
          )
        ) : (
          <Badge tone="danger">
            <ShieldCheck size={10} aria-hidden /> blocked:{' '}
            {REJECTION_LABELS[item.rejection_reason] ?? item.rejection_reason}
          </Badge>
        )}
        {item.changes.map((change) => (
          <Badge key={change} tone="neutral">
            {change}
          </Badge>
        ))}
        {decision && (
          <Badge tone={decision === 'accepted' ? 'ok' : 'neutral'} className="ml-auto">
            {decision === 'accepted' ? 'you accepted' : 'you rejected'}
          </Badge>
        )}
      </div>

      <div className="grid gap-0 md:grid-cols-2">
        {/* original */}
        <div className="border-b border-line p-5 md:border-b-0 md:border-r">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="label !mb-0">Your original</p>
            <span className="text-[0.6875rem] text-ink-faint">{item.word_count_before} words</span>
          </div>
          <p className="text-sm leading-relaxed text-ink">{item.original}</p>
          {item.weakness_signals.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {item.weakness_signals.map((signal) => (
                <Badge key={signal} tone="neutral">
                  {signal}
                </Badge>
              ))}
            </div>
          )}
        </div>

        {/* improved */}
        <div
          className="p-5"
          style={{
            backgroundColor: item.accepted
              ? 'rgb(var(--ok) / 0.05)'
              : 'rgb(var(--danger) / 0.05)',
          }}
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="label !mb-0">{item.accepted ? 'Improved' : 'Rejected rewrite'}</p>
            <span className="text-[0.6875rem] text-ink-faint">{item.word_count_after} words</span>
          </div>
          <p
            className={`text-sm leading-relaxed ${
              item.accepted ? 'font-medium text-ink' : 'text-ink-muted line-through decoration-ink-faint/60'
            }`}
          >
            {item.improved}
          </p>
          {item.metrics_preserved.length > 0 && (
            <p className="mt-2 text-[0.6875rem] text-ink-faint">
              Metrics preserved from your original: {item.metrics_preserved.join(', ')}
            </p>
          )}
        </div>
      </div>

      <div className="border-t border-line px-5 py-3">
        {item.explanation && (
          <p className="flex gap-1.5 text-[0.8125rem] leading-relaxed text-ink-muted">
            <Info size={13} className="mt-0.5 shrink-0 text-ink-faint" aria-hidden />
            {item.explanation}
          </p>
        )}

        {blocking.map((flag, flagIndex) => (
          <Notice key={flagIndex} tone="danger" title={REJECTION_LABELS[flag.type] ?? titleCase(flag.type)} className="mt-3">
            {flag.detail}
          </Notice>
        ))}
        {warnings.map((flag, flagIndex) => (
          <Notice key={flagIndex} tone="warn" className="mt-3">
            <AlertTriangle size={12} className="mr-1 inline" aria-hidden />
            {flag.detail}
          </Notice>
        ))}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {item.accepted && (
            <>
              <Button
                variant={decision === 'accepted' ? 'primary' : 'secondary'}
                size="sm"
                icon={Check}
                onClick={() => onDecide(item, 'accepted')}
              >
                Accept
              </Button>
              <Button
                variant={decision === 'rejected' ? 'danger' : 'secondary'}
                size="sm"
                icon={decision === 'rejected' ? Undo2 : X}
                onClick={() => onDecide(item, 'rejected')}
              >
                {decision === 'rejected' ? 'Keep original' : 'Reject'}
              </Button>
            </>
          )}
          <Button
            variant="ghost"
            size="sm"
            icon={copied ? Check : Copy}
            onClick={() => void onCopy(item)}
          >
            {copied ? 'Copied' : item.accepted ? 'Copy improved' : 'Copy original'}
          </Button>
        </div>
      </div>
    </Card>
  );
}

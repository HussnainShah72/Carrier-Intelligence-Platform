/**
 * Page 6 - Mock Interview (Module 5).
 *
 * Two screens in one: a setup panel, then the live interview.
 *
 * The live screen is built around one constraint — the candidate must be able
 * to tell, at a glance, whether the system is listening, thinking or speaking.
 * A voice interface that leaves the user guessing is worse than a text one, so
 * state is shown with the microphone meter, the streaming transcript, and the
 * per-turn latency readout rather than a single spinner.
 *
 * A text fallback is always one click away: if the microphone or the local
 * speech model fails, the interview continues instead of ending.
 */

import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Award,
  Brain,
  CheckCircle2,
  ClipboardList,
  Info,
  Keyboard,
  Loader2,
  Mic,
  MicOff,
  Radio,
  Send,
  Settings,
  SkipForward,
  Square,
  Volume2,
  VolumeX,
  Zap,
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
  Field,
  Loading,
  Notice,
  PageHeader,
  ProgressBar,
  Select,
  Table,
  Td,
} from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { ApiFailure, cvApi, interviewApi, roleApi, streamTextTurn, streamVoiceTurn } from '../lib/api';
import { ms, titleCase } from '../lib/format';
import { useApp } from '../lib/store';
import { useAudioQueue, useRecorder } from '../hooks/useVoice';
import type {
  AnswerAnalysis,
  Difficulty,
  Interview as InterviewType,
  InterviewMode,
  InterviewProgress,
  InterviewTurn,
  TranscriptionInfo,
  TurnEvent,
  TurnTimings,
} from '../lib/types';

type Phase = 'setup' | 'live' | 'finished';

const DIFFICULTIES: Array<{ value: Difficulty; label: string }> = [
  { value: 'easy', label: 'Easy — supportive, foundational questions' },
  { value: 'medium', label: 'Medium — a realistic mid-level interview' },
  { value: 'hard', label: 'Hard — demanding, probes trade-offs and depth' },
];

export default function Interview() {
  const { interviewId } = useParams();
  const navigate = useNavigate();
  const { notify, selection, setLastInterview } = useApp();

  const [phase, setPhase] = useState<Phase>('setup');
  const [interview, setInterview] = useState<InterviewType | null>(null);
  const [turns, setTurns] = useState<InterviewTurn[]>([]);
  const [progress, setProgress] = useState<InterviewProgress | null>(null);

  // setup
  const [roleTitle, setRoleTitle] = useState(selection.roleLabel);
  const [difficulty, setDifficulty] = useState<Difficulty>('medium');
  const [mode, setMode] = useState<InterviewMode>('voice');
  const [cvId, setCvId] = useState(selection.cvId);
  const [roleAnalysisId, setRoleAnalysisId] = useState(selection.roleAnalysisId);
  const [starting, setStarting] = useState(false);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [warming, setWarming] = useState(false);

  // live turn state
  const [streamingText, setStreamingText] = useState('');
  const [pendingTranscript, setPendingTranscript] = useState('');
  const [sttInfo, setSttInfo] = useState<TranscriptionInfo | null>(null);
  const [lastAnalysis, setLastAnalysis] = useState<AnswerAnalysis | null>(null);
  const [lastTimings, setLastTimings] = useState<TurnTimings | null>(null);
  const [turnState, setTurnState] = useState<'idle' | 'transcribing' | 'thinking' | 'speaking'>('idle');
  const [turnError, setTurnError] = useState<string | null>(null);
  const [typed, setTyped] = useState('');
  const [useText, setUseText] = useState(false);
  const [finishing, setFinishing] = useState(false);

  const recorder = useRecorder(150);
  const audio = useAudioQueue();
  const transcriptRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const cvs = useAsync(() => cvApi.list(50), []);
  const roles = useAsync(() => roleApi.list(50), []);
  const speech = useAsync(() => interviewApi.speechHealth(), []);
  const rubric = useAsync(() => interviewApi.rubric(difficulty), [difficulty]);
  const stages = useAsync(() => interviewApi.stages(difficulty), [difficulty]);
  const existing = useAsync(async () => (interviewId ? interviewApi.get(interviewId) : null), [interviewId]);

  /* resume an interview from its URL */
  useEffect(() => {
    if (!existing.data) return;
    setInterview(existing.data.interview);
    setTurns(existing.data.turns);
    setProgress(existing.data.interview.progress);
    setRoleTitle(existing.data.interview.role_title);
    setDifficulty(existing.data.interview.difficulty);
    setMode(existing.data.interview.mode);
    setUseText(existing.data.interview.mode === 'text');
    setPhase(existing.data.interview.status === 'active' ? 'live' : 'finished');
  }, [existing.data]);

  /* keep the transcript pinned to the newest turn */
  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns, streamingText]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
      audio.stopAll();
      recorder.release();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  /* ------------------------------------------------------------- handlers -- */

  const handleEvent = useCallback(
    (event: TurnEvent) => {
      switch (event.type) {
        case 'transcript':
          setPendingTranscript(event.text);
          setSttInfo(event.stt);
          setTurnState('thinking');
          break;

        case 'no_speech':
          setSttInfo(event.stt);
          setTurnState('idle');
          setPendingTranscript('');
          setTurnError(event.message);
          break;

        case 'analysis':
          setLastAnalysis(event.analysis);
          break;

        case 'stage':
          setProgress(event.progress);
          notify({
            tone: 'info',
            title: `Stage: ${event.stage_name}`,
            message: stages.data?.stages.find((s) => s.key === event.stage)?.goal,
          });
          break;

        case 'text':
          setStreamingText((current) => current + event.delta);
          setTurnState((current) => (current === 'speaking' ? current : 'thinking'));
          break;

        case 'audio':
          audio.enqueue(event.audio_base64, event.mime);
          setTurnState('speaking');
          break;

        case 'tts_error':
          notify({
            tone: 'warn',
            title: 'A sentence could not be spoken',
            message: `${event.message} The text is still shown.`,
          });
          break;

        case 'metrics':
          setLastTimings(event.timings);
          break;

        case 'done': {
          setProgress(event.progress);
          setStreamingText('');
          setPendingTranscript('');
          setTurnState('idle');
          if (event.timings) setLastTimings(event.timings);

          if (event.finished) {
            setPhase('finished');
            notify({
              tone: 'ok',
              title: 'Interview complete',
              message: event.message ?? 'Generating your scored feedback.',
            });
            if (interview) void finishAndScore(interview.id);
          } else if (interviewId) {
            // Re-read the turns so every entry carries its stored metadata.
            void interviewApi
              .get(interviewId)
              .then((fresh) => {
                setTurns(fresh.turns);
                setInterview(fresh.interview);
              })
              .catch(() => undefined);
          }
          break;
        }

        case 'error':
          setTurnState('idle');
          setStreamingText('');
          setTurnError(event.message);
          if (event.fallback === 'text') setUseText(true);
          notify({ tone: 'danger', title: 'Turn failed', message: event.message });
          break;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [audio, notify, stages.data, interviewId, interview],
  );

  const finishAndScore = useCallback(
    async (id: string) => {
      setFinishing(true);
      try {
        await interviewApi.score(id);
        notify({ tone: 'ok', title: 'Feedback ready', message: 'Opening your results.' });
        navigate(`/results/${id}`);
      } catch (caught: unknown) {
        notify({
          tone: 'warn',
          title: 'Scoring failed',
          message:
            caught instanceof ApiFailure
              ? caught.message
              : 'Your transcript is saved — try scoring again from the Results page.',
        });
        navigate(`/results/${id}`);
      } finally {
        setFinishing(false);
      }
    },
    [navigate, notify],
  );

  const start = useCallback(async () => {
    const clean = roleTitle.trim();
    if (clean.length < 2) {
      setSetupError('Enter the job title you want to be interviewed for.');
      return;
    }
    setStarting(true);
    setSetupError(null);

    try {
      if (mode === 'voice') {
        // Warm both local models first, so the first measured turn is not
        // dominated by one-off model loading (seconds, not milliseconds).
        setWarming(true);
        await interviewApi.warmUp().catch(() => undefined);
        setWarming(false);
        await audio.unlock();
        await recorder.prepare();
      }

      const result = await interviewApi.start({
        role_title: clean,
        difficulty,
        mode,
        cv_id: cvId,
        role_analysis_id: roleAnalysisId,
      });

      setInterview(result.interview);
      setProgress(result.interview.progress);
      setTurns([]);
      setUseText(mode === 'text');
      setLastInterview(result.interview.id);
      setPhase('live');
      navigate(`/interview/${result.interview.id}`, { replace: true });

      // Opening turn: no candidate answer yet.
      setTurnState('thinking');
      const controller = new AbortController();
      abortRef.current = controller;
      await streamTextTurn(result.interview.id, '', mode === 'voice', {
        onEvent: handleEvent,
        signal: controller.signal,
      });
    } catch (caught: unknown) {
      const message = caught instanceof ApiFailure ? caught.message : 'The interview could not be started.';
      setSetupError(message);
      setTurnState('idle');
      notify({ tone: 'danger', title: 'Could not start', message });
    } finally {
      setStarting(false);
      setWarming(false);
    }
  }, [
    roleTitle, difficulty, mode, cvId, roleAnalysisId, audio, recorder,
    navigate, notify, setLastInterview, handleEvent,
  ]);

  const submitVoice = useCallback(async () => {
    if (!interview) return;
    const blob = await recorder.stop();
    if (!blob || blob.size < 1200) {
      setTurnError('That recording was too short to transcribe. Hold the button while you speak.');
      return;
    }

    setTurnError(null);
    setStreamingText('');
    setLastAnalysis(null);
    setTurnState('transcribing');
    audio.stopAll();

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamVoiceTurn(interview.id, blob, true, { onEvent: handleEvent, signal: controller.signal });
    } catch (caught: unknown) {
      setTurnState('idle');
      const message = caught instanceof ApiFailure ? caught.message : 'The turn failed.';
      setTurnError(message);
    }
  }, [interview, recorder, audio, handleEvent]);

  const submitText = useCallback(async () => {
    if (!interview) return;
    const text = typed.trim();
    if (!text) return;

    setTyped('');
    setTurnError(null);
    setStreamingText('');
    setLastAnalysis(null);
    setPendingTranscript(text);
    setTurnState('thinking');
    audio.stopAll();

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamTextTurn(interview.id, text, mode === 'voice' && !audio.muted, {
        onEvent: handleEvent,
        signal: controller.signal,
      });
    } catch (caught: unknown) {
      setTurnState('idle');
      setTurnError(caught instanceof ApiFailure ? caught.message : 'The turn failed.');
    }
  }, [interview, typed, mode, audio, handleEvent]);

  const endNow = useCallback(async () => {
    if (!interview) return;
    abortRef.current?.abort();
    audio.stopAll();
    recorder.cancel();
    try {
      await interviewApi.end(interview.id);
    } catch {
      /* the interview is ended locally regardless */
    }
    setPhase('finished');
    void finishAndScore(interview.id);
  }, [interview, audio, recorder, finishAndScore]);

  /* ----------------------------------------------------------------- views -- */

  if (existing.loading && interviewId) return <Loading label="Loading interview…" />;
  if (existing.error && interviewId) {
    return (
      <ErrorState title="Could not load that interview" message={existing.error} onRetry={existing.reload} />
    );
  }

  if (phase === 'setup') {
    return (
      <SetupView
        roleTitle={roleTitle}
        setRoleTitle={setRoleTitle}
        difficulty={difficulty}
        setDifficulty={setDifficulty}
        mode={mode}
        setMode={setMode}
        cvId={cvId}
        setCvId={setCvId}
        roleAnalysisId={roleAnalysisId}
        setRoleAnalysisId={setRoleAnalysisId}
        cvs={cvs.data?.items ?? []}
        roles={roles.data?.items ?? []}
        speech={speech.data}
        speechLoading={speech.loading}
        rubric={rubric.data}
        stages={stages.data?.stages ?? []}
        starting={starting}
        warming={warming}
        error={setupError}
        recorderStatus={recorder.status}
        recorderError={recorder.error}
        onStart={() => void start()}
      />
    );
  }

  if (phase === 'finished') {
    return (
      <>
        <PageHeader title="Interview complete" description="Your transcript is saved." />
        <Card>
          <EmptyState
            icon={finishing ? Loader2 : Award}
            title={finishing ? 'Scoring your interview…' : 'Interview finished'}
            description={
              finishing
                ? 'Your answers are being assessed against the rubric that was fixed before the interview started.'
                : 'Open your results to see the rubric breakdown, strengths, weaknesses and measured latency.'
            }
            action={
              interview && (
                <Link to={`/results/${interview.id}`}>
                  <Button variant="primary" icon={ClipboardList} iconRight={ArrowRight}>
                    View results
                  </Button>
                </Link>
              )
            }
          />
        </Card>
      </>
    );
  }

  /* ------------------------------------------------------------ live view -- */

  const busy = turnState !== 'idle';
  const recording = recorder.status === 'recording';

  return (
    <>
      <PageHeader
        title={`Interview: ${interview?.role_title ?? ''}`}
        description={
          interview?.plan.interviewer_name
            ? `${interview.plan.interviewer_name} · ${interview.plan.interviewer_persona}`
            : undefined
        }
        badge={
          <>
            <Badge tone="brand">{titleCase(interview?.difficulty ?? '')}</Badge>
            {progress && progress.effective_difficulty !== interview?.difficulty && (
              <Badge tone="warn" title="The interviewer adapted to your answers">
                now {progress.effective_difficulty}
              </Badge>
            )}
          </>
        }
        actions={
          <>
            <Button
              variant="ghost"
              icon={audio.muted ? VolumeX : Volume2}
              onClick={() => audio.setMuted(!audio.muted)}
              title={audio.muted ? 'Unmute the interviewer' : 'Mute the interviewer'}
            >
              {audio.muted ? 'Muted' : 'Sound on'}
            </Button>
            <Button variant="danger" icon={Square} onClick={() => void endNow()} disabled={finishing}>
              End interview
            </Button>
          </>
        }
      />

      {progress && <StageTracker progress={progress} />}

      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_20rem]">
        {/* ------------------------------------------------------ transcript -- */}
        <div className="min-w-0 space-y-4">
          <Card className="flex flex-col">
            <CardHeader
              title="Conversation"
              subtitle={`${turns.filter((t) => t.speaker === 'candidate').length} answers given`}
              icon={Radio}
              actions={
                <Badge
                  tone={
                    turnState === 'idle' ? 'neutral' : turnState === 'speaking' ? 'ok' : 'brand'
                  }
                >
                  {turnState === 'idle' && recording && (
                    <>
                      <Mic size={10} aria-hidden /> listening
                    </>
                  )}
                  {turnState === 'idle' && !recording && 'your turn'}
                  {turnState === 'transcribing' && (
                    <>
                      <Loader2 size={10} className="animate-spin" aria-hidden /> transcribing locally
                    </>
                  )}
                  {turnState === 'thinking' && (
                    <>
                      <Brain size={10} aria-hidden /> thinking
                    </>
                  )}
                  {turnState === 'speaking' && (
                    <>
                      <Volume2 size={10} aria-hidden /> speaking
                    </>
                  )}
                </Badge>
              }
            />

            <div ref={transcriptRef} className="scroll-area max-h-[32rem] min-h-[18rem] space-y-4 p-5">
              {turns.length === 0 && !streamingText && (
                <p className="py-8 text-center text-sm text-ink-muted">
                  The interviewer is about to speak…
                </p>
              )}

              {turns.map((turn) => (
                <TurnBubble key={turn.id} turn={turn} />
              ))}

              {pendingTranscript && (
                <div className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-brand-600 px-4 py-2.5 text-sm leading-relaxed text-white">
                    {pendingTranscript}
                    {sttInfo && (
                      <p className="mt-1.5 text-[0.6875rem] text-white/70">
                        transcribed locally in {ms(sttInfo.processing_ms)} · confidence {sttInfo.confidence}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {streamingText && (
                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-surface-muted px-4 py-2.5 text-sm leading-relaxed text-ink">
                    {streamingText}
                    <span className="ml-0.5 inline-block h-4 w-1 animate-pulse bg-brand-600 align-middle" />
                  </div>
                </div>
              )}
            </div>

            {/* ---------------------------------------------------- controls -- */}
            <div className="border-t border-line p-5">
              {turnError && (
                <Notice tone="warn" className="mb-4" onDismiss={() => setTurnError(null)}>
                  {turnError}
                </Notice>
              )}

              {recorder.status === 'unsupported' || recorder.status === 'denied' ? (
                <Notice tone="danger" title="Microphone unavailable" className="mb-4">
                  {recorder.error} The interview continues below in text mode.
                </Notice>
              ) : null}

              {!useText && mode === 'voice' && recorder.status !== 'unsupported' && recorder.status !== 'denied' ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-4">
                    <button
                      type="button"
                      onClick={() => (recording ? void submitVoice() : void recorder.start())}
                      disabled={busy}
                      className={`relative grid h-16 w-16 shrink-0 place-items-center rounded-full text-white transition-all disabled:opacity-50 ${
                        recording ? 'bg-[rgb(var(--danger))]' : 'bg-brand-600 hover:bg-brand-700'
                      }`}
                      aria-label={recording ? 'Stop recording and send' : 'Start recording your answer'}
                    >
                      {recording && (
                        <span
                          className="absolute inset-0 animate-pulse-ring rounded-full"
                          style={{ backgroundColor: 'rgb(var(--danger) / 0.4)' }}
                          aria-hidden
                        />
                      )}
                      {busy ? (
                        <Loader2 size={24} className="animate-spin" aria-hidden />
                      ) : recording ? (
                        <Square size={22} aria-hidden />
                      ) : (
                        <Mic size={24} aria-hidden />
                      )}
                    </button>

                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-ink">
                        {busy
                          ? turnState === 'transcribing'
                            ? 'Transcribing your answer on this machine…'
                            : turnState === 'thinking'
                              ? 'The interviewer is thinking…'
                              : 'The interviewer is speaking…'
                          : recording
                            ? `Recording — ${recorder.seconds.toFixed(1)}s. Press again when you finish.`
                            : 'Press to answer out loud'}
                      </p>

                      {/* live input level: proves the microphone is working */}
                      <div className="mt-2 flex h-6 items-end gap-0.5" aria-hidden>
                        {Array.from({ length: 28 }).map((_, index) => {
                          const threshold = index / 28;
                          const active = recording && recorder.level > threshold * 0.9;
                          return (
                            <span
                              key={index}
                              className="flex-1 rounded-sm transition-all duration-75"
                              style={{
                                height: active ? `${30 + recorder.level * 70 * (1 - threshold * 0.5)}%` : '12%',
                                backgroundColor: active
                                  ? threshold > 0.75
                                    ? 'rgb(var(--danger))'
                                    : threshold > 0.5
                                      ? 'rgb(var(--warn))'
                                      : 'rgb(var(--ok))'
                                  : 'rgb(var(--line))',
                              }}
                            />
                          );
                        })}
                      </div>
                      <p className="mt-1 text-[0.6875rem] text-ink-faint">
                        {recording
                          ? recorder.level < 0.04
                            ? 'No sound detected — check your microphone is not muted'
                            : 'Input level looks good'
                          : recorder.mimeType
                            ? `Audio captured as ${recorder.mimeType}, transcribed locally by Whisper`
                            : 'Audio is transcribed locally by Whisper — nothing is uploaded'}
                      </p>
                    </div>

                    {recording && (
                      <Button variant="ghost" size="sm" onClick={() => recorder.cancel()}>
                        Discard
                      </Button>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
                    <Button variant="ghost" size="sm" icon={Keyboard} onClick={() => setUseText(true)}>
                      Type instead
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={SkipForward}
                      disabled={busy}
                      onClick={() => {
                        setTyped('I would rather skip this question.');
                        setUseText(true);
                      }}
                    >
                      Skip question
                    </Button>
                    {audio.queued > 0 && (
                      <Badge tone="neutral" className="ml-auto">
                        {audio.queued} sentence{audio.queued === 1 ? '' : 's'} queued
                      </Badge>
                    )}
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <Field
                    label="Your answer"
                    hint="Press Ctrl+Enter to send. Answer as you would out loud — the assessment rewards specifics."
                  >
                    <textarea
                      value={typed}
                      onChange={(event) => setTyped(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                          event.preventDefault();
                          void submitText();
                        }
                      }}
                      rows={4}
                      maxLength={6000}
                      disabled={busy}
                      placeholder="Type your answer…"
                      className="input resize-y"
                    />
                  </Field>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="primary"
                      icon={Send}
                      loading={busy}
                      disabled={!typed.trim()}
                      onClick={() => void submitText()}
                    >
                      Send answer
                    </Button>
                    {mode === 'voice' && recorder.status !== 'unsupported' && recorder.status !== 'denied' && (
                      <Button variant="ghost" size="sm" icon={Mic} onClick={() => setUseText(false)}>
                        Back to voice
                      </Button>
                    )}
                    <span className="ml-auto text-[0.6875rem] text-ink-faint">
                      {typed.length} / 6000
                    </span>
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* --------------------------------------------------------- sidebar -- */}
        <div className="space-y-4">
          {lastTimings && <LatencyPanel timings={lastTimings} />}
          {lastAnalysis && <AnalysisPanel analysis={lastAnalysis} />}

          {interview && (
            <Card>
              <CardHeader title="Interview plan" subtitle="Built from your CV and the role" icon={Brain} />
              <div className="card-pad space-y-3 text-[0.8125rem]">
                {interview.plan.cv_talking_points.length > 0 && (
                  <div>
                    <p className="label">From your CV</p>
                    <ul className="space-y-1 text-ink-muted">
                      {interview.plan.cv_talking_points.slice(0, 4).map((point, index) => (
                        <li key={index} className="flex gap-1.5">
                          <span aria-hidden>·</span>
                          {point}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {interview.plan.technical_topics.length > 0 && (
                  <div>
                    <p className="label">Technical topics</p>
                    <div className="flex flex-wrap gap-1">
                      {interview.plan.technical_topics.slice(0, 7).map((topic) => (
                        <Badge key={topic} tone="neutral">
                          {topic}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
                {interview.plan.gap_probes.length > 0 && (
                  <div>
                    <p className="label">Gaps it may probe</p>
                    <div className="flex flex-wrap gap-1">
                      {interview.plan.gap_probes.map((probe) => (
                        <Badge key={probe} tone="warn">
                          {probe}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}

          <Card>
            <CardHeader title="Everything is local" icon={Activity} />
            <div className="card-pad space-y-2 text-xs leading-relaxed text-ink-muted">
              <p>
                Your voice is recorded in the browser, posted to your own backend, transcribed by
                Whisper running on this machine, and the temporary file is deleted immediately.
              </p>
              <p>
                The interviewer's replies are spoken by Piper, also on this machine. No audio is sent
                to any external service.
              </p>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------ components -- */

function StageTracker({ progress }: { progress: InterviewProgress }) {
  return (
    <Card>
      <div className="card-pad">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <p className="text-sm font-bold text-ink">
              Stage {progress.stage_index + 1} of {progress.stage_total}: {progress.stage_name}
            </p>
            <p className="text-xs text-ink-muted">
              Question {Math.min(progress.stage_question_count + 1, progress.stage_budget)} of about{' '}
              {progress.stage_budget} in this stage · {progress.total_questions} asked in total
            </p>
          </div>
          <span className="text-sm font-bold text-brand-600">{progress.percent.toFixed(0)}%</span>
        </div>

        <ProgressBar value={progress.percent} className="mb-4" label="Interview progress" />

        <ol className="no-scrollbar flex gap-1.5 overflow-x-auto">
          {progress.stages.map((stage, index) => (
            <li key={stage.key} className="flex min-w-0 shrink-0 items-center gap-1.5">
              <div
                className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold ${
                  stage.status === 'done'
                    ? 'bg-[rgb(var(--ok)/0.12)] text-[rgb(var(--ok))]'
                    : stage.status === 'active'
                      ? 'bg-brand-500/15 text-brand-700'
                      : 'bg-surface-muted text-ink-faint'
                }`}
                title={stage.goal}
              >
                {stage.status === 'done' ? (
                  <CheckCircle2 size={12} aria-hidden />
                ) : (
                  <span className="grid h-3.5 w-3.5 place-items-center text-[0.625rem] font-bold">
                    {index + 1}
                  </span>
                )}
                <span className="whitespace-nowrap">{stage.name}</span>
                {!stage.scored && (
                  <span className="text-[0.625rem] font-normal opacity-70" title="Not scored">
                    (unscored)
                  </span>
                )}
              </div>
              {index < progress.stages.length - 1 && (
                <span className="text-ink-faint" aria-hidden>
                  ›
                </span>
              )}
            </li>
          ))}
        </ol>
      </div>
    </Card>
  );
}

function TurnBubble({ turn }: { turn: InterviewTurn }) {
  const isCandidate = turn.speaker === 'candidate';
  const analysis = turn.meta.analysis;
  const timings = turn.meta.timings;

  return (
    <div className={`flex ${isCandidate ? 'justify-end' : 'justify-start'}`}>
      <div className="max-w-[85%]">
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isCandidate
              ? 'rounded-br-sm bg-brand-600 text-white'
              : 'rounded-bl-sm bg-surface-muted text-ink'
          }`}
        >
          {turn.text}
        </div>

        <div
          className={`mt-1 flex flex-wrap items-center gap-1.5 text-[0.6875rem] text-ink-faint ${
            isCandidate ? 'justify-end' : ''
          }`}
        >
          {!isCandidate && turn.meta.follow_up && (
            <Badge tone="brand" title="Generated as a follow-up to your previous answer">
              follow-up
            </Badge>
          )}
          {!isCandidate && timings?.e2e_first_audio_ms != null && (
            <span title="End of your speech to first audio">
              <Zap size={9} className="mr-0.5 inline" aria-hidden />
              {ms(timings.e2e_first_audio_ms)}
            </span>
          )}
          {isCandidate && analysis && (
            <>
              <Badge
                tone={
                  analysis.quality_band === 'strong'
                    ? 'ok'
                    : analysis.quality_band === 'adequate'
                      ? 'warn'
                      : 'danger'
                }
              >
                {analysis.quality_band}
              </Badge>
              <span>{analysis.word_count} words</span>
              {analysis.role_skills_mentioned.length > 0 && (
                <span title={analysis.role_skills_mentioned.join(', ')}>
                  {analysis.role_skills_mentioned.length} role skill
                  {analysis.role_skills_mentioned.length === 1 ? '' : 's'}
                </span>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function LatencyPanel({ timings }: { timings: TurnTimings }) {
  const rows = [
    { label: 'Speech recognition (local)', value: timings.stt_ms },
    { label: 'First text token', value: timings.llm_ttft_ms },
    { label: 'First sentence spoken (local)', value: timings.tts_first_ms },
    { label: 'End of speech → first audio', value: timings.e2e_first_audio_ms, headline: true },
    { label: 'Whole turn', value: timings.total_ms },
  ];

  return (
    <Card>
      <CardHeader title="Last turn latency" subtitle="Measured, not estimated" icon={Zap} />
      <div className="card-pad">
        <dl className="space-y-1.5">
          {rows.map((row) => (
            <div
              key={row.label}
              className={`flex items-baseline justify-between gap-2 ${
                row.headline ? 'border-t border-line pt-1.5 font-semibold' : ''
              }`}
            >
              <dt className={`text-xs ${row.headline ? 'text-ink' : 'text-ink-muted'}`}>{row.label}</dt>
              <dd
                className={`mono shrink-0 text-xs ${
                  row.headline
                    ? row.value != null && row.value < 1500
                      ? 'text-[rgb(var(--ok))]'
                      : 'text-[rgb(var(--warn))]'
                    : 'text-ink'
                }`}
              >
                {ms(row.value)}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 border-t border-line pt-2 text-[0.6875rem] leading-snug text-ink-faint">
          {timings.stt_engine} · {timings.tts_engine} · {timings.llm_provider}/{timings.llm_model}
        </p>
      </div>
    </Card>
  );
}

function AnalysisPanel({ analysis }: { analysis: AnswerAnalysis }) {
  return (
    <Card>
      <CardHeader
        title="How your last answer read"
        subtitle="Computed locally in about a millisecond — it steers the next question"
        icon={Activity}
      />
      <div className="card-pad space-y-3">
        <div className="flex items-center gap-3">
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-muted">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${analysis.quality_score * 100}%`,
                backgroundColor:
                  analysis.quality_band === 'strong'
                    ? 'rgb(var(--ok))'
                    : analysis.quality_band === 'adequate'
                      ? 'rgb(var(--warn))'
                      : 'rgb(var(--danger))',
              }}
            />
          </div>
          <Badge
            tone={
              analysis.quality_band === 'strong' ? 'ok' : analysis.quality_band === 'adequate' ? 'warn' : 'danger'
            }
          >
            {analysis.quality_band}
          </Badge>
        </div>

        {analysis.signals.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {analysis.signals.map((signal) => (
              <Badge key={signal} tone="neutral">
                {signal}
              </Badge>
            ))}
          </div>
        )}

        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[0.6875rem]">
          {[
            ['Words', analysis.word_count],
            ['Concrete examples', analysis.specificity_hits],
            ['Structure markers', analysis.structure_hits],
            ['Hedging phrases', analysis.hedge_hits],
          ].map(([label, value]) => (
            <div key={String(label)} className="flex justify-between gap-2">
              <dt className="text-ink-muted">{label}</dt>
              <dd className="mono font-semibold text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </Card>
  );
}

/* ----------------------------------------------------------------- setup -- */

function SetupView({
  roleTitle, setRoleTitle, difficulty, setDifficulty, mode, setMode,
  cvId, setCvId, roleAnalysisId, setRoleAnalysisId, cvs, roles,
  speech, speechLoading, rubric, stages, starting, warming, error,
  recorderStatus, recorderError, onStart,
}: {
  roleTitle: string;
  setRoleTitle: (value: string) => void;
  difficulty: Difficulty;
  setDifficulty: (value: Difficulty) => void;
  mode: InterviewMode;
  setMode: (value: InterviewMode) => void;
  cvId: string;
  setCvId: (value: string) => void;
  roleAnalysisId: string;
  setRoleAnalysisId: (value: string) => void;
  cvs: Array<{ cv_id: string; filename: string; skill_count: number }>;
  roles: Array<{ role_analysis_id: string; role_title: string }>;
  speech: { stt: { installed?: boolean; model_size?: string; enabled: boolean }; tts: { active_engine?: string; enabled: boolean }; voice_ready: boolean; note: string } | null;
  speechLoading: boolean;
  rubric: { categories: Array<{ key: string; name: string; weight_percent: number; description: string }>; disclaimer: string; version: string; calibration_rules?: string[] } | null;
  stages: Array<{ key: string; name: string; goal: string; budget: number; scored: boolean }>;
  starting: boolean;
  warming: boolean;
  error: string | null;
  recorderStatus: string;
  recorderError: string | null;
  onStart: () => void;
}) {
  const voiceBlocked = recorderStatus === 'unsupported' || recorderStatus === 'denied';

  return (
    <>
      <PageHeader
        title="Mock Interview"
        description="A spoken interview that follows the six stages of a real one, adapts its questions to your CV and your previous answers, and scores you against a rubric published before you start."
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Set up your interview" icon={Settings} />
            <div className="card-pad space-y-5">
              <Field label="Role you are interviewing for" hint="Any job title — there is no fixed list">
                <input
                  value={roleTitle}
                  onChange={(event) => setRoleTitle(event.target.value)}
                  placeholder="e.g. Data Analyst"
                  className="input"
                  maxLength={120}
                />
              </Field>

              <Field
                label="Difficulty"
                hint="The interviewer still adapts up or down one level based on how you answer"
              >
                <Select value={difficulty} onChange={setDifficulty} options={DIFFICULTIES} ariaLabel="Difficulty" />
              </Field>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Your CV" hint="Questions are grounded in it">
                  <Select
                    value={cvId}
                    onChange={setCvId}
                    ariaLabel="Select CV"
                    options={[
                      { value: '', label: cvs.length ? 'No CV (generic questions)' : 'No CVs uploaded' },
                      ...cvs.map((cv) => ({ value: cv.cv_id, label: cv.filename })),
                    ]}
                  />
                </Field>
                <Field label="Role requirements" hint="Focuses the technical questions">
                  <Select
                    value={roleAnalysisId}
                    onChange={(value) => {
                      setRoleAnalysisId(value);
                      const match = roles.find((role) => role.role_analysis_id === value);
                      if (match && !roleTitle) setRoleTitle(match.role_title);
                    }}
                    ariaLabel="Select role analysis"
                    options={[
                      { value: '', label: roles.length ? 'None' : 'No roles analysed' },
                      ...roles.map((role) => ({
                        value: role.role_analysis_id,
                        label: role.role_title,
                      })),
                    ]}
                  />
                </Field>
              </div>

              <div>
                <p className="label">Interview mode</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => setMode('voice')}
                    disabled={voiceBlocked}
                    className={`rounded-xl border-2 p-4 text-left transition-colors disabled:opacity-50 ${
                      mode === 'voice' ? 'border-brand-500 bg-brand-500/8' : 'border-line hover:border-brand-300'
                    }`}
                  >
                    <span className="flex items-center gap-2 text-sm font-bold text-ink">
                      <Mic size={15} aria-hidden /> Spoken interview
                    </span>
                    <span className="mt-1 block text-xs leading-snug text-ink-muted">
                      Speak your answers. Local Whisper transcribes them and local Piper speaks the
                      interviewer's replies.
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode('text')}
                    className={`rounded-xl border-2 p-4 text-left transition-colors ${
                      mode === 'text' ? 'border-brand-500 bg-brand-500/8' : 'border-line hover:border-brand-300'
                    }`}
                  >
                    <span className="flex items-center gap-2 text-sm font-bold text-ink">
                      <Keyboard size={15} aria-hidden /> Text interview
                    </span>
                    <span className="mt-1 block text-xs leading-snug text-ink-muted">
                      Type your answers. Useful for troubleshooting, or if you have no microphone.
                    </span>
                  </button>
                </div>
              </div>

              {voiceBlocked && (
                <Notice tone="warn" title="Voice mode is unavailable on this device">
                  {recorderError ?? 'The microphone could not be opened.'} You can still run the full
                  interview in text mode.
                </Notice>
              )}

              {error && (
                <Notice tone="danger" title="Could not start">
                  {error}
                </Notice>
              )}

              <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
                <Button
                  variant="primary"
                  size="lg"
                  icon={mode === 'voice' ? Mic : Keyboard}
                  loading={starting}
                  disabled={roleTitle.trim().length < 2}
                  onClick={onStart}
                >
                  {warming
                    ? 'Loading speech models…'
                    : starting
                      ? 'Starting…'
                      : `Start ${mode === 'voice' ? 'spoken' : 'text'} interview`}
                </Button>
                {mode === 'voice' && (
                  <p className="text-xs text-ink-muted">
                    The first start loads the Whisper and Piper models into memory, which takes a few
                    seconds. This is done before the clock starts so it does not distort the measured
                    latency.
                  </p>
                )}
              </div>
            </div>
          </Card>

          {/* stages */}
          <Card>
            <CardHeader
              title="What the interview covers"
              subtitle="The six stages of a real interview, in order"
              icon={ClipboardList}
            />
            <ol className="divide-y divide-line">
              {stages.map((stage, index) => (
                <li key={stage.key} className="flex items-start gap-3 px-5 py-3">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-surface-muted text-xs font-bold text-ink-muted">
                    {index + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink">
                      {stage.name}
                      <Badge tone="neutral">
                        ~{stage.budget} question{stage.budget === 1 ? '' : 's'}
                      </Badge>
                      {!stage.scored && <Badge tone="neutral">not scored</Badge>}
                    </p>
                    <p className="mt-0.5 text-xs leading-snug text-ink-muted">{stage.goal}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </div>

        {/* ----------------------------------------------------- sidebar -- */}
        <div className="space-y-6">
          <Card>
            <CardHeader title="Local speech engines" icon={Activity} />
            <div className="card-pad space-y-3">
              {speechLoading ? (
                <div className="skeleton h-20" />
              ) : speech ? (
                <>
                  <StatusRow
                    label="Speech recognition"
                    ok={Boolean(speech.stt.installed) && speech.stt.enabled}
                    detail={
                      speech.stt.installed
                        ? `faster-whisper · ${speech.stt.model_size}`
                        : 'faster-whisper not installed'
                    }
                  />
                  <StatusRow
                    label="Speech synthesis"
                    ok={speech.tts.enabled && Boolean(speech.tts.active_engine)}
                    detail={
                      speech.tts.active_engine === 'piper'
                        ? 'Piper neural voice'
                        : speech.tts.active_engine === 'sapi'
                          ? 'Operating-system voice (Piper unavailable)'
                          : 'unavailable'
                    }
                    warn={speech.tts.active_engine === 'sapi'}
                  />
                  <p className="border-t border-line pt-3 text-xs leading-relaxed text-ink-muted">
                    {speech.note}
                  </p>
                  {!speech.voice_ready && (
                    <Notice tone="warn">
                      Voice mode is not fully ready. Check{' '}
                      <Link to="/settings" className="link">
                        Settings
                      </Link>{' '}
                      — you can still use text mode.
                    </Notice>
                  )}
                </>
              ) : (
                <p className="text-sm text-ink-muted">Could not read the speech engine status.</p>
              )}
            </div>
          </Card>

          {rubric && (
            <Card>
              <CardHeader
                title="How you will be scored"
                subtitle={`Rubric v${rubric.version}, fixed before the interview starts`}
                icon={Award}
              />
              <div className="card-pad">
                <Table head={['Category', 'Weight']} dense>
                  {rubric.categories.map((category) => (
                    <tr key={category.key}>
                      <Td dense>
                        <span className="font-medium" title={category.description}>
                          {category.name}
                        </span>
                      </Td>
                      <Td dense className="mono text-xs">
                        {category.weight_percent.toFixed(0)}%
                      </Td>
                    </tr>
                  ))}
                </Table>
                {rubric.calibration_rules && rubric.calibration_rules.length > 0 && (
                  <Collapsible title="Evidence rules" className="mt-3 !border-0 bg-surface-muted">
                    <ul className="list-disc space-y-1 pl-4 text-xs leading-relaxed text-ink-muted">
                      {rubric.calibration_rules.map((rule) => (
                        <li key={rule}>{rule}</li>
                      ))}
                    </ul>
                  </Collapsible>
                )}
                <Collapsible title="Important caveat" className="mt-3 !border-0 bg-surface-muted">
                  <p className="text-xs leading-relaxed text-ink-muted">{rubric.disclaimer}</p>
                </Collapsible>
              </div>
            </Card>
          )}

          <Card>
            <CardHeader title="Before you start" icon={Info} />
            <ul className="card-pad space-y-2 text-xs leading-relaxed text-ink-muted">
              <li className="flex gap-1.5">
                <span aria-hidden>·</span>Use headphones if you can — it stops the interviewer's voice
                being picked up by your microphone.
              </li>
              <li className="flex gap-1.5">
                <span aria-hidden>·</span>Answer in full sentences with concrete examples. The
                assessment rewards specifics over confidence.
              </li>
              <li className="flex gap-1.5">
                <span aria-hidden>·</span>Press the microphone once to start and once to finish each
                answer.
              </li>
              <li className="flex gap-1.5">
                <span aria-hidden>·</span>If recognition mishears you, switch to typing for that turn
                and carry on.
              </li>
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}

function StatusRow({
  label,
  ok,
  detail,
  warn = false,
}: {
  label: string;
  ok: boolean;
  detail: string;
  warn?: boolean;
}) {
  return (
    <div className="flex items-start gap-2">
      {ok && !warn ? (
        <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-[rgb(var(--ok))]" aria-hidden />
      ) : ok && warn ? (
        <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[rgb(var(--warn))]" aria-hidden />
      ) : (
        <MicOff size={14} className="mt-0.5 shrink-0 text-[rgb(var(--danger))]" aria-hidden />
      )}
      <div className="min-w-0">
        <p className="text-[0.8125rem] font-semibold text-ink">{label}</p>
        <p className="text-xs text-ink-muted">{detail}</p>
      </div>
    </div>
  );
}

/**
 * The browser side of the voice interview.
 *
 * `useRecorder` captures the candidate's answer and reports a live input level
 * so the user can see that the microphone is actually working — the single most
 * common cause of "it doesn't work" in a voice demo is a muted or wrong device,
 * and a meter makes that obvious before they speak for a minute.
 *
 * `useAudioQueue` plays the interviewer's sentences strictly in order. Each
 * sentence arrives as its own WAV while later ones are still being generated,
 * so a queue is required: playing them as they arrive would overlap them, and
 * waiting for all of them would throw away the latency the backend worked for.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

/* --------------------------------------------------------------- recorder -- */

export type RecorderStatus = 'idle' | 'requesting' | 'ready' | 'recording' | 'denied' | 'unsupported';

export interface RecorderState {
  status: RecorderStatus;
  level: number;
  seconds: number;
  error: string | null;
  mimeType: string;
  start: () => Promise<void>;
  stop: () => Promise<Blob | null>;
  cancel: () => void;
  prepare: () => Promise<boolean>;
  release: () => void;
  /**
   * When the candidate stopped speaking, as epoch ms: the last moment the input
   * level was above the speech threshold, or the stop time if no speech was
   * heard. Sent with the recording so latency can be measured from real speech end.
   */
  speechEndedAt: () => number;
  /** Called once per recording after `silenceMs` of silence following speech; null disables. */
  setOnSilence: (callback: (() => void) | null) => void;
}

/** Meter level (0-1) above which the input counts as speech. Normal speech is ~0.3-0.7. */
const SPEECH_LEVEL = 0.12;
/** Silence after speech that ends an answer automatically. */
const SILENCE_MS = 1600;
/** Never auto-stop in the first moments, before the candidate has started. */
const MIN_RECORDING_MS = 1500;

/** Candidate container/codec list, best first; browsers differ. */
const PREFERRED_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/mp4',
  '',
];

function pickMimeType(): string {
  if (typeof MediaRecorder === 'undefined') return '';
  for (const type of PREFERRED_MIME_TYPES) {
    if (!type) return '';
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return '';
}

export function useRecorder(maxSeconds = 150): RecorderState {
  const [status, setStatus] = useState<RecorderStatus>('idle');
  const [level, setLevel] = useState(0);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [mimeType, setMimeType] = useState('');

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const timerRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);
  const stopResolveRef = useRef<((blob: Blob | null) => void) | null>(null);
  const heardSpeechRef = useRef(false);
  const lastVoiceAtRef = useRef(0);
  const stoppedAtRef = useRef(0);
  const onSilenceRef = useRef<(() => void) | null>(null);
  const silenceFiredRef = useRef(false);

  useEffect(() => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setStatus('unsupported');
      setError(
        'This browser cannot record audio. Use a recent Chrome, Edge or Firefox, and note that ' +
          'microphone access needs http://localhost (not a file:// page).',
      );
      return;
    }
    if (typeof MediaRecorder === 'undefined') {
      setStatus('unsupported');
      setError('This browser does not support MediaRecorder, so the voice interview cannot record.');
    }
  }, []);

  const stopMeter = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    setLevel(0);
  }, []);

  const runMeter = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;
    const buffer = new Uint8Array(analyser.fftSize);

    const tick = () => {
      analyser.getByteTimeDomainData(buffer);
      // RMS of the waveform, scaled so normal speech lands around 0.3-0.7.
      let sum = 0;
      for (let i = 0; i < buffer.length; i += 1) {
        const centred = (buffer[i] - 128) / 128;
        sum += centred * centred;
      }
      const rms = Math.sqrt(sum / buffer.length);
      const level = Math.min(1, rms * 3.2);
      setLevel(level);

      // Voice activity: remember when speech was last heard and, once the
      // candidate has spoken and then stayed quiet, end the answer for them.
      if (recorderRef.current?.state === 'recording') {
        const now = Date.now();
        if (level > SPEECH_LEVEL) {
          heardSpeechRef.current = true;
          lastVoiceAtRef.current = now;
        } else if (
          heardSpeechRef.current &&
          !silenceFiredRef.current &&
          onSilenceRef.current &&
          now - startedAtRef.current > MIN_RECORDING_MS &&
          now - lastVoiceAtRef.current > SILENCE_MS
        ) {
          silenceFiredRef.current = true;
          onSilenceRef.current();
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const release = useCallback(() => {
    stopMeter();
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    analyserRef.current = null;
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      void audioContextRef.current.close().catch(() => undefined);
    }
    audioContextRef.current = null;
    setStatus((current) => (current === 'unsupported' || current === 'denied' ? current : 'idle'));
  }, [stopMeter]);

  useEffect(() => release, [release]);

  const prepare = useCallback(async (): Promise<boolean> => {
    if (status === 'unsupported') return false;
    if (streamRef.current) return true;

    setStatus('requesting');
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      });
      streamRef.current = stream;

      const AudioCtor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const context = new AudioCtor();
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      analyser.smoothingTimeConstant = 0.7;
      source.connect(analyser);
      audioContextRef.current = context;
      analyserRef.current = analyser;

      const chosen = pickMimeType();
      setMimeType(chosen || 'browser default');
      setStatus('ready');
      runMeter();
      return true;
    } catch (caught: unknown) {
      const name = caught instanceof DOMException ? caught.name : '';
      setStatus('denied');
      setError(
        name === 'NotAllowedError' || name === 'SecurityError'
          ? 'Microphone access was blocked. Allow it in your browser’s address-bar permission icon, then try again. You can also answer by typing.'
          : name === 'NotFoundError'
            ? 'No microphone was found. Connect one and reload, or answer by typing.'
            : 'The microphone could not be opened. You can answer by typing instead.',
      );
      return false;
    }
  }, [status, runMeter]);

  const start = useCallback(async (): Promise<void> => {
    const ready = await prepare();
    if (!ready || !streamRef.current) return;

    chunksRef.current = [];
    const chosen = pickMimeType();
    const recorder = chosen
      ? new MediaRecorder(streamRef.current, { mimeType: chosen, audioBitsPerSecond: 64_000 })
      : new MediaRecorder(streamRef.current);

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      const type = recorder.mimeType || chosen || 'audio/webm';
      const blob = chunksRef.current.length ? new Blob(chunksRef.current, { type }) : null;
      chunksRef.current = [];
      stopResolveRef.current?.(blob);
      stopResolveRef.current = null;
    };
    recorder.onerror = () => {
      setError('Recording failed part-way through. Please try again, or answer by typing.');
      stopResolveRef.current?.(null);
      stopResolveRef.current = null;
      setStatus('ready');
    };

    recorderRef.current = recorder;
    // 250 ms timeslices keep the buffer small and make a long answer resilient.
    recorder.start(250);
    startedAtRef.current = Date.now();
    heardSpeechRef.current = false;
    silenceFiredRef.current = false;
    lastVoiceAtRef.current = 0;
    setSeconds(0);
    setStatus('recording');

    timerRef.current = window.setInterval(() => {
      const elapsed = (Date.now() - startedAtRef.current) / 1000;
      setSeconds(elapsed);
      if (elapsed >= maxSeconds && recorderRef.current?.state === 'recording') {
        recorderRef.current.stop();
      }
    }, 100);
  }, [prepare, maxSeconds]);

  const stop = useCallback((): Promise<Blob | null> => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === 'inactive') return Promise.resolve(null);
    stoppedAtRef.current = Date.now();

    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }

    return new Promise<Blob | null>((resolve) => {
      stopResolveRef.current = resolve;
      try {
        recorder.stop();
      } catch {
        resolve(null);
        stopResolveRef.current = null;
      }
      setStatus('ready');
    });
  }, []);

  const cancel = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      stopResolveRef.current = null;
      chunksRef.current = [];
      try {
        recorder.stop();
      } catch {
        /* already stopped */
      }
    }
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setSeconds(0);
    setStatus((current) => (current === 'recording' ? 'ready' : current));
  }, []);

  const speechEndedAt = useCallback(
    () => (heardSpeechRef.current && lastVoiceAtRef.current ? lastVoiceAtRef.current : stoppedAtRef.current || Date.now()),
    [],
  );

  const setOnSilence = useCallback((callback: (() => void) | null) => {
    onSilenceRef.current = callback;
  }, []);

  return {
    status, level, seconds, error, mimeType, start, stop, cancel, prepare, release, speechEndedAt, setOnSilence,
  };
}

/* ------------------------------------------------------------ audio queue -- */

export interface AudioQueueState {
  enqueue: (base64: string, mime?: string) => void;
  stopAll: () => void;
  playing: boolean;
  queued: number;
  muted: boolean;
  setMuted: (value: boolean) => void;
  unlock: () => Promise<void>;
}

function base64ToBlob(base64: string, mime: string): Blob {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

export function useAudioQueue(): AudioQueueState {
  const [playing, setPlaying] = useState(false);
  const [queued, setQueued] = useState(0);
  const [muted, setMutedState] = useState(false);

  const queueRef = useRef<string[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mutedRef = useRef(false);
  const playingRef = useRef(false);

  const cleanupCurrent = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      if (audio.src) URL.revokeObjectURL(audio.src);
      audio.src = '';
    }
    audioRef.current = null;
  }, []);

  const playNext = useCallback(() => {
    if (mutedRef.current) {
      queueRef.current.forEach((url) => URL.revokeObjectURL(url));
      queueRef.current = [];
      setQueued(0);
      playingRef.current = false;
      setPlaying(false);
      return;
    }

    const next = queueRef.current.shift();
    setQueued(queueRef.current.length);

    if (!next) {
      playingRef.current = false;
      setPlaying(false);
      return;
    }

    const audio = new Audio(next);
    audio.preload = 'auto';
    audioRef.current = audio;
    playingRef.current = true;
    setPlaying(true);

    const advance = () => {
      URL.revokeObjectURL(next);
      audioRef.current = null;
      playNext();
    };
    audio.onended = advance;
    audio.onerror = advance;

    void audio.play().catch(() => {
      // Autoplay blocked until the user has interacted with the page; dropping
      // the chunk is better than stalling the whole reply.
      advance();
    });
  }, []);

  const enqueue = useCallback(
    (base64: string, mime = 'audio/wav') => {
      if (mutedRef.current || !base64) return;
      try {
        const url = URL.createObjectURL(base64ToBlob(base64, mime));
        queueRef.current.push(url);
        setQueued(queueRef.current.length);
        if (!playingRef.current) playNext();
      } catch {
        /* a malformed chunk is skipped rather than breaking playback */
      }
    },
    [playNext],
  );

  const stopAll = useCallback(() => {
    queueRef.current.forEach((url) => URL.revokeObjectURL(url));
    queueRef.current = [];
    setQueued(0);
    cleanupCurrent();
    playingRef.current = false;
    setPlaying(false);
  }, [cleanupCurrent]);

  const setMuted = useCallback(
    (value: boolean) => {
      mutedRef.current = value;
      setMutedState(value);
      if (value) stopAll();
    },
    [stopAll],
  );

  /**
   * Satisfy the browser's autoplay policy.
   *
   * Playing a silent clip inside the click that starts the interview marks the
   * page as user-activated, so the interviewer's first sentence is not blocked.
   */
  const unlock = useCallback(async () => {
    try {
      const silent = new Audio(
        'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA',
      );
      silent.volume = 0;
      await silent.play();
      silent.pause();
    } catch {
      /* non-fatal: the first chunk may be skipped instead */
    }
  }, []);

  useEffect(() => stopAll, [stopAll]);

  return { enqueue, stopAll, playing, queued, muted, setMuted, unlock };
}

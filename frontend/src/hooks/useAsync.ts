/**
 * Data-fetching and microphone hooks.
 *
 * `useAsync` exists so every page gets the same loading / error / retry
 * behaviour without a data-fetching library: the project has one consumer per
 * endpoint, so a 40-line hook is a better trade than another dependency.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiFailure } from '../lib/api';

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  errorCode: string | null;
  reload: () => void;
  setData: (value: T | null) => void;
}

/** Run `loader` on mount and whenever `deps` change. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setErrorCode(null);

    loader()
      .then((result) => {
        if (!cancelled && alive.current) setData(result);
      })
      .catch((caught: unknown) => {
        if (cancelled || !alive.current) return;
        const failure = caught instanceof ApiFailure ? caught : null;
        setError(failure?.message ?? (caught instanceof Error ? caught.message : 'Unexpected error'));
        setErrorCode(failure?.code ?? 'unknown');
      })
      .finally(() => {
        if (!cancelled && alive.current) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((value) => value + 1), []);

  return { data, loading, error, errorCode, reload, setData };
}

/** A manually triggered async action, with its own pending/error state. */
export function useAction<TArgs extends unknown[], TResult>(
  action: (...args: TArgs) => Promise<TResult>,
): {
  run: (...args: TArgs) => Promise<TResult | null>;
  pending: boolean;
  error: string | null;
  reset: () => void;
} {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (...args: TArgs): Promise<TResult | null> => {
      setPending(true);
      setError(null);
      try {
        return await action(...args);
      } catch (caught: unknown) {
        const failure = caught instanceof ApiFailure ? caught : null;
        setError(failure?.message ?? (caught instanceof Error ? caught.message : 'Unexpected error'));
        return null;
      } finally {
        setPending(false);
      }
    },
    [action],
  );

  return { run, pending, error, reset: () => setError(null) };
}

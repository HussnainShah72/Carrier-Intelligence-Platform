/**
 * App-wide shared state.
 *
 * Three things genuinely need to be shared between pages:
 *   - the selected CV and role analysis (the gap page, improvement studio and
 *     interview all build on what the user picked earlier)
 *   - the colour theme
 *   - toasts
 *
 * Selections persist to localStorage so a page refresh mid-demo does not lose
 * the user's context. Everything else is fetched per page.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

/* ----------------------------------------------------------------- Theme -- */

type Theme = 'light' | 'dark';

function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    // Private windows and blocked site data both throw here.
    return fallback;
  }
}

function writeStored(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* non-fatal: the app works without persistence */
  }
}

/* ---------------------------------------------------------------- Toasts -- */

export interface Toast {
  id: number;
  tone: 'info' | 'ok' | 'warn' | 'danger';
  title: string;
  message?: string;
}

/* --------------------------------------------------------------- Context -- */

interface Selection {
  cvId: string;
  cvLabel: string;
  roleAnalysisId: string;
  roleLabel: string;
  lastInterviewId: string;
}

interface AppState {
  theme: Theme;
  toggleTheme: () => void;

  selection: Selection;
  setCv: (id: string, label: string) => void;
  setRole: (id: string, label: string) => void;
  setLastInterview: (id: string) => void;
  clearSelection: () => void;

  toasts: Toast[];
  notify: (toast: Omit<Toast, 'id'>) => void;
  dismiss: (id: number) => void;
}

const EMPTY_SELECTION: Selection = {
  cvId: '',
  cvLabel: '',
  roleAnalysisId: '',
  roleLabel: '',
  lastInterviewId: '',
};

const AppContext = createContext<AppState | null>(null);

const THEME_KEY = 'cip.theme';
const SELECTION_KEY = 'cip.selection';

export function AppProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = readStored<Theme | null>(THEME_KEY, null);
    if (stored === 'light' || stored === 'dark') return stored;
    try {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    } catch {
      return 'light';
    }
  });

  const [selection, setSelection] = useState<Selection>(() =>
    readStored<Selection>(SELECTION_KEY, EMPTY_SELECTION),
  );
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    writeStored(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    writeStored(SELECTION_KEY, selection);
  }, [selection]);

  const toggleTheme = useCallback(() => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  }, []);

  const setCv = useCallback((id: string, label: string) => {
    setSelection((current) => ({ ...current, cvId: id, cvLabel: label }));
  }, []);

  const setRole = useCallback((id: string, label: string) => {
    setSelection((current) => ({ ...current, roleAnalysisId: id, roleLabel: label }));
  }, []);

  const setLastInterview = useCallback((id: string) => {
    setSelection((current) => ({ ...current, lastInterviewId: id }));
  }, []);

  const clearSelection = useCallback(() => setSelection(EMPTY_SELECTION), []);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const notify = useCallback(
    (toast: Omit<Toast, 'id'>) => {
      const id = Date.now() + Math.random();
      setToasts((current) => [...current.slice(-3), { ...toast, id }]);
      const ttl = toast.tone === 'danger' ? 8000 : 4500;
      setTimeout(() => dismiss(id), ttl);
    },
    [dismiss],
  );

  const value = useMemo<AppState>(
    () => ({
      theme,
      toggleTheme,
      selection,
      setCv,
      setRole,
      setLastInterview,
      clearSelection,
      toasts,
      notify,
      dismiss,
    }),
    [theme, toggleTheme, selection, setCv, setRole, setLastInterview, clearSelection, toasts, notify, dismiss],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const context = useContext(AppContext);
  if (!context) throw new Error('useApp must be used inside <AppProvider>');
  return context;
}

/**
 * Application shell: sidebar, top bar, toast host.
 *
 * The sidebar is ordered to match the workflow (CV -> role -> gap -> improve ->
 * interview -> results), because the product's value is the sequence, and a
 * first-time user should be able to read the nav as the set of steps.
 */

import clsx from 'clsx';
import {
  Activity,
  AlertCircle,
  BarChart3,
  Briefcase,
  CheckCircle2,
  ClipboardList,
  FileText,
  Info,
  LayoutDashboard,
  Menu,
  Mic,
  Moon,
  PenLine,
  Settings as SettingsIcon,
  Sun,
  Target,
  TriangleAlert,
  X,
} from 'lucide-react';
import { type ReactNode, useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import { systemApi } from '../lib/api';
import { useApp } from '../lib/store';
import { useAsync } from '../hooks/useAsync';

const NAV_GROUPS: Array<{
  label: string;
  items: Array<{ to: string; label: string; icon: typeof LayoutDashboard; hint: string }>;
}> = [
  {
    label: 'Overview',
    items: [{ to: '/', label: 'Dashboard', icon: LayoutDashboard, hint: 'Your progress at a glance' }],
  },
  {
    label: 'Prepare',
    items: [
      { to: '/cv', label: 'CV Analysis', icon: FileText, hint: 'Upload and parse your CV' },
      { to: '/roles', label: 'Job Role Analysis', icon: Briefcase, hint: 'Live postings + LLM skills' },
      { to: '/gap', label: 'Skill Gap', icon: Target, hint: 'What you match and what is missing' },
      { to: '/improve', label: 'CV Improvement', icon: PenLine, hint: 'Rewrite weak bullet points' },
    ],
  },
  {
    label: 'Practise',
    items: [
      { to: '/interview', label: 'Mock Interview', icon: Mic, hint: 'Spoken, adaptive interview' },
      { to: '/results', label: 'Interview Results', icon: ClipboardList, hint: 'Scores and feedback' },
    ],
  },
  {
    label: 'System',
    items: [
      { to: '/performance', label: 'Performance', icon: BarChart3, hint: 'Measured latency' },
      { to: '/settings', label: 'Settings', icon: SettingsIcon, hint: 'Models, privacy, storage' },
    ],
  },
];

export function Layout({ children }: { children: ReactNode }) {
  const { theme, toggleTheme, toasts, dismiss } = useApp();
  const [open, setOpen] = useState(false);
  const location = useLocation();

  const health = useAsync(() => systemApi.health(false), []);

  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  const degraded = health.data?.status === 'degraded';
  const offline = health.error !== null;

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[17rem_1fr]">
      {/* ------------------------------------------------------- sidebar -- */}
      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-40 flex w-[17rem] flex-col border-r border-line bg-surface transition-transform duration-200 lg:static lg:translate-x-0',
          open ? 'translate-x-0 shadow-pop' : '-translate-x-full',
        )}
      >
        <div className="flex items-center gap-2.5 border-b border-line px-5 py-4">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-600 text-white">
            <Activity size={18} aria-hidden />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-bold leading-tight text-ink">
              Career Intelligence
            </span>
            <span className="block text-[0.6875rem] font-medium uppercase tracking-wider text-ink-faint">
              NLP Course Project
            </span>
          </span>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="ml-auto rounded-lg p-1 text-ink-faint hover:bg-surface-muted lg:hidden"
            aria-label="Close navigation"
          >
            <X size={16} aria-hidden />
          </button>
        </div>

        <nav className="scroll-area flex-1 px-3 py-4" aria-label="Main navigation">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="mb-5 last:mb-0">
              <p className="mb-1.5 px-2 text-[0.6875rem] font-bold uppercase tracking-wider text-ink-faint">
                {group.label}
              </p>
              <ul className="space-y-0.5">
                {group.items.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.to === '/'}
                      className={({ isActive }) =>
                        clsx(
                          'group flex items-start gap-2.5 rounded-xl px-2.5 py-2 transition-colors',
                          isActive
                            ? 'bg-brand-500/12 text-brand-700'
                            : 'text-ink-muted hover:bg-surface-muted hover:text-ink',
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <item.icon
                            size={16}
                            className={clsx('mt-0.5 shrink-0', isActive ? 'text-brand-600' : 'text-ink-faint')}
                            aria-hidden
                          />
                          <span className="min-w-0">
                            <span className="block text-sm font-semibold leading-tight">{item.label}</span>
                            <span className="mt-0.5 block text-[0.6875rem] leading-tight text-ink-faint">
                              {item.hint}
                            </span>
                          </span>
                        </>
                      )}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <EngineStatus
          loading={health.loading}
          offline={offline}
          degraded={degraded}
          provider={health.data?.components.llm.provider}
          model={health.data?.components.llm.model}
          sttReady={Boolean(health.data?.components.speech_recognition.installed)}
          ttsEngine={health.data?.components.text_to_speech.active_engine}
          degradations={health.data?.degradations ?? []}
        />
      </aside>

      {open && (
        <div
          className="fixed inset-0 z-30 bg-slate-950/40 backdrop-blur-sm lg:hidden"
          onClick={() => setOpen(false)}
          aria-hidden
        />
      )}

      {/* ---------------------------------------------------------- main -- */}
      <div className="flex min-h-screen min-w-0 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-surface/85 px-4 py-3 backdrop-blur-md sm:px-6">
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="rounded-lg p-1.5 text-ink-muted hover:bg-surface-muted hover:text-ink lg:hidden"
            aria-label="Open navigation"
          >
            <Menu size={18} aria-hidden />
          </button>

          <Breadcrumb />

          <div className="ml-auto flex items-center gap-2">
            {offline ? (
              <span className="badge-danger hidden sm:inline-flex">
                <AlertCircle size={12} aria-hidden /> Backend offline
              </span>
            ) : degraded ? (
              <span className="badge-warn hidden sm:inline-flex" title={health.data?.degradations.join(' • ')}>
                <TriangleAlert size={12} aria-hidden /> Degraded
              </span>
            ) : health.data ? (
              <span className="badge-ok hidden sm:inline-flex">
                <CheckCircle2 size={12} aria-hidden /> All systems ready
              </span>
            ) : null}

            <button
              type="button"
              onClick={toggleTheme}
              className="rounded-lg p-2 text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink"
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
              title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
            >
              {theme === 'dark' ? <Sun size={17} aria-hidden /> : <Moon size={17} aria-hidden />}
            </button>
          </div>
        </header>

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-[86rem]">{children}</div>
        </main>

        <footer className="border-t border-line px-4 py-4 text-center text-xs text-ink-faint sm:px-6">
          Career Intelligence Platform · Natural Language Processing course project · Speech
          recognition and speech synthesis run locally on this machine
        </footer>
      </div>

      {/* -------------------------------------------------------- toasts -- */}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((toast) => {
          const config = {
            info: { icon: Info, colour: 'var(--info)' },
            ok: { icon: CheckCircle2, colour: 'var(--ok)' },
            warn: { icon: TriangleAlert, colour: 'var(--warn)' },
            danger: { icon: AlertCircle, colour: 'var(--danger)' },
          }[toast.tone];
          const Icon = config.icon;

          return (
            <div
              key={toast.id}
              role="status"
              className="pointer-events-auto flex animate-fade-up items-start gap-2.5 rounded-xl border bg-surface-raised px-4 py-3 shadow-pop"
              style={{ borderColor: `rgb(${config.colour} / 0.3)` }}
            >
              <Icon size={16} className="mt-0.5 shrink-0" style={{ color: `rgb(${config.colour})` }} aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink">{toast.title}</p>
                {toast.message && (
                  <p className="mt-0.5 text-xs leading-snug text-ink-muted">{toast.message}</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                className="shrink-0 rounded-md p-0.5 text-ink-faint hover:bg-surface-muted hover:text-ink"
                aria-label="Dismiss notification"
              >
                <X size={13} aria-hidden />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Breadcrumb() {
  const location = useLocation();
  const all = NAV_GROUPS.flatMap((group) => group.items);
  const current =
    all.find((item) => item.to !== '/' && location.pathname.startsWith(item.to)) ??
    all.find((item) => item.to === location.pathname);

  return (
    <div className="min-w-0">
      <p className="truncate text-sm font-semibold text-ink">{current?.label ?? 'Career Intelligence'}</p>
      <p className="truncate text-xs text-ink-faint">{current?.hint ?? 'Job preparation platform'}</p>
    </div>
  );
}

function EngineStatus({
  loading,
  offline,
  degraded,
  provider,
  model,
  sttReady,
  ttsEngine,
  degradations,
}: {
  loading: boolean;
  offline: boolean;
  degraded: boolean;
  provider?: string;
  model?: string;
  sttReady: boolean;
  ttsEngine?: string;
  degradations: string[];
}) {
  if (loading) {
    return (
      <div className="border-t border-line p-3">
        <div className="skeleton h-16 w-full" />
      </div>
    );
  }

  if (offline) {
    return (
      <div className="border-t border-line p-3">
        <div
          className="rounded-xl border px-3 py-2.5 text-xs leading-snug"
          style={{
            backgroundColor: 'rgb(var(--danger) / 0.08)',
            borderColor: 'rgb(var(--danger) / 0.25)',
          }}
        >
          <p className="font-semibold text-[rgb(var(--danger))]">Backend not reachable</p>
          <p className="mt-1 text-ink-muted">
            Start it with <span className="mono">uvicorn app.main:app --port 8000</span> from the{' '}
            <span className="mono">backend</span> folder.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="border-t border-line p-3">
      <div className="rounded-xl bg-surface-muted px-3 py-2.5">
        <p className="mb-2 text-[0.6875rem] font-bold uppercase tracking-wider text-ink-faint">
          Engines
        </p>
        <dl className="space-y-1.5 text-[0.6875rem]">
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-ink-muted">LLM</dt>
            <dd className="truncate font-semibold text-ink" title={`${provider} / ${model}`}>
              {provider === 'offline' ? 'offline (rules)' : provider}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-ink-muted">Speech in</dt>
            <dd className="font-semibold text-ink">{sttReady ? 'Whisper (local)' : 'unavailable'}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-ink-muted">Speech out</dt>
            <dd className="font-semibold text-ink">
              {ttsEngine === 'piper' ? 'Piper (local)' : ttsEngine === 'sapi' ? 'OS voice (local)' : '—'}
            </dd>
          </div>
        </dl>
        {degraded && degradations.length > 0 && (
          <p
            className="mt-2 border-t pt-2 text-[0.6875rem] leading-snug text-ink-muted"
            style={{ borderColor: 'rgb(var(--line))' }}
          >
            <TriangleAlert size={10} className="mr-1 inline text-[rgb(var(--warn))]" aria-hidden />
            {degradations.length === 1 ? degradations[0] : `${degradations.length} degradations — see Settings`}
          </p>
        )}
      </div>
    </div>
  );
}

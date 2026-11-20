/**
 * Shared UI primitives.
 *
 * Deliberately small and unopinionated: the project needs a consistent visual
 * language across eight pages, which is cheaper to achieve with a handful of
 * well-behaved primitives than with a component library whose defaults would
 * then be fought on every screen. Each one handles its loading, empty and
 * error state, because those are the states a student project usually skips.
 */

import clsx from 'clsx';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Info,
  Loader2,
  type LucideIcon,
  X,
} from 'lucide-react';
import { type ReactNode, useEffect, useId, useRef, useState } from 'react';

/* ------------------------------------------------------------------- Card -- */

export function Card({
  children,
  className,
  as: Tag = 'section',
}: {
  children: ReactNode;
  className?: string;
  as?: 'section' | 'div' | 'article';
}) {
  return <Tag className={clsx('card', className)}>{children}</Tag>;
}

export function CardHeader({
  title,
  subtitle,
  icon: Icon,
  actions,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: LucideIcon;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={clsx('card-header', className)}>
      <div className="flex min-w-0 items-start gap-3">
        {Icon && (
          <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-500/12 text-brand-600">
            <Icon size={18} aria-hidden />
          </span>
        )}
        <div className="min-w-0">
          <h2 className="truncate text-[0.9375rem] font-semibold text-ink">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[0.8125rem] leading-snug text-ink-muted">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}

/* ---------------------------------------------------------------- Buttons -- */

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

export function Button({
  children,
  onClick,
  variant = 'secondary',
  size = 'md',
  icon: Icon,
  iconRight: IconRight,
  loading = false,
  disabled = false,
  type = 'button',
  className,
  title,
  ariaLabel,
}: {
  children?: ReactNode;
  onClick?: () => void;
  variant?: ButtonVariant;
  size?: 'sm' | 'md' | 'lg';
  icon?: LucideIcon;
  iconRight?: LucideIcon;
  loading?: boolean;
  disabled?: boolean;
  type?: 'button' | 'submit';
  className?: string;
  title?: string;
  ariaLabel?: string;
}) {
  const variants: Record<ButtonVariant, string> = {
    primary: 'btn-primary',
    secondary: 'btn-secondary',
    ghost: 'btn-ghost',
    danger: 'btn-danger',
  };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      title={title}
      aria-label={ariaLabel}
      aria-busy={loading || undefined}
      className={clsx(
        variants[variant],
        size === 'sm' && 'btn-sm',
        size === 'lg' && 'btn-lg',
        className,
      )}
    >
      {loading ? (
        <Loader2 size={size === 'sm' ? 13 : 15} className="animate-spin" aria-hidden />
      ) : (
        Icon && <Icon size={size === 'sm' ? 13 : 15} aria-hidden />
      )}
      {children}
      {IconRight && !loading && <IconRight size={size === 'sm' ? 13 : 15} aria-hidden />}
    </button>
  );
}

/* ----------------------------------------------------------------- Badges -- */

export function Badge({
  children,
  tone = 'neutral',
  className,
  title,
}: {
  children: ReactNode;
  tone?: 'neutral' | 'brand' | 'ok' | 'warn' | 'danger' | 'info';
  className?: string;
  title?: string;
}) {
  const tones = {
    neutral: 'badge-neutral',
    brand: 'badge-brand',
    ok: 'badge-ok',
    warn: 'badge-warn',
    danger: 'badge-danger',
    info: 'badge-info',
  };
  return (
    <span className={clsx(tones[tone], className)} title={title}>
      {children}
    </span>
  );
}

export function Dot({ colour, className }: { colour: string; className?: string }) {
  return (
    <span
      className={clsx('inline-block h-2 w-2 shrink-0 rounded-full', className)}
      style={{ backgroundColor: colour }}
      aria-hidden
    />
  );
}

/* ------------------------------------------------------------ Stat tiles -- */

export function StatTile({
  label,
  value,
  unit,
  hint,
  icon: Icon,
  tone = 'neutral',
  className,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: string;
  icon?: LucideIcon;
  tone?: 'neutral' | 'ok' | 'warn' | 'danger' | 'brand';
  className?: string;
}) {
  const tones = {
    neutral: 'text-ink',
    ok: 'text-[rgb(var(--ok))]',
    warn: 'text-[rgb(var(--warn))]',
    danger: 'text-[rgb(var(--danger))]',
    brand: 'text-brand-600',
  };

  return (
    <div className={clsx('card card-pad', className)}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{label}</p>
        {Icon && <Icon size={15} className="shrink-0 text-ink-faint" aria-hidden />}
      </div>
      <p className={clsx('mt-2 flex items-baseline gap-1 text-2xl font-bold leading-none', tones[tone])}>
        {value}
        {unit && <span className="text-sm font-semibold text-ink-faint">{unit}</span>}
      </p>
      {hint && <p className="mt-1.5 text-xs leading-snug text-ink-faint">{hint}</p>}
    </div>
  );
}

/* --------------------------------------------------------------- Progress -- */

export function ProgressBar({
  value,
  max = 100,
  colour,
  height = 8,
  label,
  className,
}: {
  value: number;
  max?: number;
  colour?: string;
  height?: number;
  label?: string;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / (max || 1)) * 100));
  return (
    <div
      className={clsx('w-full overflow-hidden rounded-full bg-surface-muted', className)}
      style={{ height }}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div
        className="h-full rounded-full transition-all duration-500 ease-out"
        style={{ width: `${pct}%`, backgroundColor: colour ?? 'rgb(var(--brand-600))' }}
      />
    </div>
  );
}

export function Ring({
  value,
  size = 112,
  thickness = 9,
  colour,
  children,
  label,
}: {
  value: number;
  size?: number;
  thickness?: number;
  colour?: string;
  children?: ReactNode;
  label?: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;

  return (
    <div className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" role="img" aria-label={label ?? `${pct}%`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgb(var(--line))"
          strokeWidth={thickness}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={colour ?? 'rgb(var(--brand-600))'}
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - pct / 100)}
          style={{ transition: 'stroke-dashoffset 700ms cubic-bezier(.2,.8,.2,1)' }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">{children}</div>
    </div>
  );
}

/* ----------------------------------------------------------------- States -- */

export function Loading({ label = 'Loading…', className }: { label?: string; className?: string }) {
  return (
    <div className={clsx('flex flex-col items-center justify-center gap-3 py-12 text-center', className)}>
      <Loader2 size={24} className="animate-spin text-brand-600" aria-hidden />
      <p className="text-sm text-ink-muted">{label}</p>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('skeleton', className)} aria-hidden />;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx('flex flex-col items-center justify-center px-6 py-14 text-center', className)}>
      {Icon && (
        <span className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-surface-muted text-ink-faint">
          <Icon size={24} aria-hidden />
        </span>
      )}
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {description && (
        <p className="mt-1.5 max-w-md text-sm leading-relaxed text-ink-muted text-pretty">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  className,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div className={clsx('flex flex-col items-center justify-center px-6 py-12 text-center', className)}>
      <span
        className="mb-4 grid h-14 w-14 place-items-center rounded-2xl text-[rgb(var(--danger))]"
        style={{ backgroundColor: 'rgb(var(--danger) / 0.12)' }}
      >
        <AlertCircle size={24} aria-hidden />
      </span>
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {message && <p className="mt-1.5 max-w-md text-sm leading-relaxed text-ink-muted text-pretty">{message}</p>}
      {onRetry && (
        <div className="mt-5">
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- Notices -- */

export function Notice({
  tone = 'info',
  title,
  children,
  className,
  onDismiss,
}: {
  tone?: 'info' | 'warn' | 'danger' | 'ok';
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
  onDismiss?: () => void;
}) {
  const config = {
    info: { icon: Info, colour: 'var(--info)' },
    warn: { icon: AlertTriangle, colour: 'var(--warn)' },
    danger: { icon: AlertCircle, colour: 'var(--danger)' },
    ok: { icon: CheckCircle2, colour: 'var(--ok)' },
  }[tone];
  const Icon = config.icon;

  return (
    <div
      className={clsx('flex items-start gap-3 rounded-xl border px-4 py-3', className)}
      style={{
        backgroundColor: `rgb(${config.colour} / 0.08)`,
        borderColor: `rgb(${config.colour} / 0.25)`,
      }}
      role={tone === 'danger' ? 'alert' : 'status'}
    >
      <Icon size={16} className="mt-0.5 shrink-0" style={{ color: `rgb(${config.colour})` }} aria-hidden />
      <div className="min-w-0 flex-1 text-[0.8125rem] leading-relaxed text-ink">
        {title && <p className="font-semibold">{title}</p>}
        {children}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 rounded-md p-0.5 text-ink-faint transition-colors hover:bg-surface-muted hover:text-ink"
          aria-label="Dismiss"
        >
          <X size={14} aria-hidden />
        </button>
      )}
    </div>
  );
}

/* -------------------------------------------------------------- Collapse -- */

export function Collapsible({
  title,
  subtitle,
  children,
  defaultOpen = false,
  className,
  badge,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  badge?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();

  return (
    <div className={clsx('overflow-hidden rounded-xl border border-line', className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-center justify-between gap-3 bg-surface px-4 py-3 text-left transition-colors hover:bg-surface-muted"
      >
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold text-ink">{title}</span>
          {subtitle && <span className="mt-0.5 block text-xs text-ink-muted">{subtitle}</span>}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {badge}
          <ChevronDown
            size={16}
            className={clsx('text-ink-faint transition-transform duration-200', open && 'rotate-180')}
            aria-hidden
          />
        </span>
      </button>
      {open && (
        <div id={panelId} className="border-t border-line bg-surface-muted/40 px-4 py-4">
          {children}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Tabs -- */

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  className,
}: {
  tabs: Array<{ key: T; label: string; count?: number; icon?: LucideIcon }>;
  active: T;
  onChange: (key: T) => void;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={clsx('no-scrollbar flex gap-1 overflow-x-auto rounded-xl bg-surface-muted p-1', className)}
    >
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const selected = active === tab.key;
        return (
          <button
            key={tab.key}
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(tab.key)}
            className={clsx(
              'flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-[0.8125rem] font-semibold transition-all',
              selected
                ? 'bg-surface text-ink shadow-sm'
                : 'text-ink-muted hover:text-ink',
            )}
          >
            {Icon && <Icon size={14} aria-hidden />}
            {tab.label}
            {tab.count !== undefined && (
              <span
                className={clsx(
                  'rounded-full px-1.5 py-px text-[0.6875rem] font-bold',
                  selected ? 'bg-brand-500/15 text-brand-700' : 'bg-surface text-ink-faint',
                )}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/* ----------------------------------------------------------------- Modal -- */

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  width = 'max-w-lg',
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    ref.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <div
        className="absolute inset-0 bg-slate-950/55 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        className={clsx(
          'relative w-full animate-fade-up rounded-2xl border border-line bg-surface-raised shadow-pop',
          width,
        )}
      >
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-ink-faint transition-colors hover:bg-surface-muted hover:text-ink"
            aria-label="Close dialog"
          >
            <X size={16} aria-hidden />
          </button>
        </header>
        <div className="scroll-area max-h-[65vh] px-5 py-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-5 py-4">{footer}</footer>}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- Fields -- */

export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="label">{label}</label>
      {children}
      {error ? (
        <p className="mt-1 text-xs text-[rgb(var(--danger))]">{error}</p>
      ) : (
        hint && <p className="mt-1 text-xs text-ink-faint">{hint}</p>
      )}
    </div>
  );
}

export function Select<T extends string>({
  value,
  onChange,
  options,
  className,
  ariaLabel,
}: {
  value: T;
  onChange: (value: T) => void;
  options: Array<{ value: T; label: string }>;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value as T)}
      className={clsx('input cursor-pointer', className)}
      aria-label={ariaLabel}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  return (
    <label
      className={clsx(
        'flex cursor-pointer items-start justify-between gap-4',
        disabled && 'cursor-not-allowed opacity-60',
      )}
    >
      <span className="min-w-0">
        <span className="block text-sm font-medium text-ink">{label}</span>
        {description && <span className="mt-0.5 block text-xs leading-snug text-ink-muted">{description}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={clsx(
          'relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors',
          checked ? 'bg-brand-600' : 'bg-line',
        )}
      >
        <span
          className={clsx(
            'absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform',
            checked ? 'translate-x-[1.125rem]' : 'translate-x-0.5',
          )}
        />
      </button>
    </label>
  );
}

/* ------------------------------------------------------------------ Table -- */

export function Table({
  head,
  children,
  className,
  dense = false,
}: {
  head: ReactNode[];
  children: ReactNode;
  className?: string;
  dense?: boolean;
}) {
  return (
    <div className={clsx('overflow-x-auto', className)}>
      <table className="w-full min-w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-line">
            {head.map((cell, index) => (
              <th
                key={index}
                scope="col"
                className={clsx(
                  'whitespace-nowrap px-3 text-xs font-semibold uppercase tracking-wide text-ink-muted',
                  dense ? 'py-2' : 'py-2.5',
                )}
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  );
}

export function Td({
  children,
  className,
  dense = false,
  colSpan,
}: {
  children: ReactNode;
  className?: string;
  dense?: boolean;
  colSpan?: number;
}) {
  return (
    <td colSpan={colSpan} className={clsx('px-3 align-top text-ink', dense ? 'py-1.5' : 'py-2.5', className)}>
      {children}
    </td>
  );
}

/* ---------------------------------------------------------------- Section -- */

export function PageHeader({
  title,
  description,
  actions,
  badge,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  badge?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-bold tracking-tight text-ink sm:text-2xl">{title}</h1>
          {badge}
        </div>
        {description && (
          <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-ink-muted text-pretty">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** Small formatting helpers shared across the UI. */

export function ms(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return '—';
  if (value < 1000) return `${value.toFixed(digits)} ms`;
  return `${(value / 1000).toFixed(value < 10_000 ? 2 : 1)} s`;
}

export function bytes(value: number | null | undefined): string {
  if (!value) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return '—';
  return `${value.toFixed(digits)}%`;
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';

  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 45) return 'just now';
  if (seconds < 90) return 'a minute ago';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function duration(seconds: number | null | undefined): string {
  if (!seconds) return '0s';
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${rest}s`;
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

export function truncate(value: string, limit = 120): string {
  if (!value) return '';
  return value.length <= limit ? value : `${value.slice(0, limit - 1).trimEnd()}…`;
}

export function initials(name: string): string {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function pluralise(count: number, singular: string, plural?: string): string {
  return `${count} ${count === 1 ? singular : plural ?? `${singular}s`}`;
}

/** Download a blob/string as a file from the browser. */
export function downloadFile(content: Blob | string, filename: string, mime = 'text/plain'): void {
  const blob = typeof content === 'string' ? new Blob([content], { type: mime }) : content;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback for browsers/contexts where the async clipboard is unavailable.
    try {
      const area = document.createElement('textarea');
      area.value = text;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(area);
      return ok;
    } catch {
      return false;
    }
  }
}

/* ------------------------------------------------------------- categorical */

/**
 * Stable colour per skill category.
 *
 * Chosen to stay distinguishable in both themes and for the common forms of
 * colour blindness: hue steps are large and lightness varies alongside hue, so
 * the series is still readable if hue information is lost.
 */
export const CATEGORY_COLOURS: Record<string, string> = {
  'Programming Language': '#6366f1',
  Frontend: '#0ea5e9',
  Backend: '#8b5cf6',
  Database: '#0d9488',
  'Cloud & DevOps': '#f59e0b',
  'Data & Analytics': '#10b981',
  'Machine Learning & AI': '#ec4899',
  Security: '#ef4444',
  Tooling: '#64748b',
  'Engineering Practice': '#a855f7',
  'Professional Skill': '#14b8a6',
  'Domain Knowledge': '#f97316',
  Qualification: '#84cc16',
  Other: '#94a3b8',
};

export function categoryColour(category: string): string {
  return CATEGORY_COLOURS[category] ?? CATEGORY_COLOURS.Other;
}

export const STATUS_COLOURS = {
  matched: '#10b981',
  partial: '#f59e0b',
  missing: '#ef4444',
} as const;

export const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low'] as const;

export function severityBadgeClass(severity: string): string {
  switch (severity) {
    case 'critical':
      return 'badge-danger';
    case 'high':
      return 'badge-warn';
    case 'medium':
      return 'badge-info';
    default:
      return 'badge-neutral';
  }
}

export function statusBadgeClass(status: string): string {
  switch (status) {
    case 'matched':
      return 'badge-ok';
    case 'partial':
      return 'badge-warn';
    case 'missing':
      return 'badge-danger';
    default:
      return 'badge-neutral';
  }
}

export function provenanceLabel(provenance: string): string {
  switch (provenance) {
    case 'both':
      return 'Job adverts + LLM';
    case 'scraped':
      return 'Job adverts only';
    case 'llm':
      return 'LLM only';
    default:
      return provenance;
  }
}

export function scoreColour(score: number | null): string {
  if (score === null) return 'var(--ink-faint)';
  if (score >= 4.2) return '#10b981';
  if (score >= 3.4) return '#84cc16';
  if (score >= 2.6) return '#f59e0b';
  return '#ef4444';
}

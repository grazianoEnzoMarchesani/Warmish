/**
 * Tiny toast queue. Replaces the two stacked banners: transient feedback that
 * stacks, auto-dismisses (errors excepted) and never pushes the layout around.
 */
export type ToastKind = 'info' | 'success' | 'error' | 'progress';

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
  progress?: { done: number; total: number };
}

let seq = 0;
export const toasts = $state<Toast[]>([]);

function push(kind: ToastKind, message: string, ttl: number): number {
  const id = ++seq;
  toasts.push({ id, kind, message });
  if (ttl) setTimeout(() => dismiss(id), ttl);
  return id;
}

export function dismiss(id: number): void {
  const i = toasts.findIndex((t) => t.id === id);
  if (i >= 0) toasts.splice(i, 1);
}

export const toast = {
  info: (m: string) => push('info', m, 6000),
  success: (m: string) => push('success', m, 5000),
  error: (m: string) => push('error', m, 0), // sticky until dismissed
};

/** A long-running job: one toast that reports progress, then resolves in place. */
export function progressToast(message: string) {
  const id = push('progress', message, 0);
  return {
    update(done: number, total: number, message?: string) {
      const t = toasts.find((x) => x.id === id);
      if (!t) return;
      t.progress = { done, total };
      if (message) t.message = message;
    },
    finish(kind: Exclude<ToastKind, 'progress'>, message: string) {
      dismiss(id);
      push(kind, message, kind === 'error' ? 0 : 6000);
    },
  };
}

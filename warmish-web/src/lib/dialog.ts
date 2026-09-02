/**
 * `use:dialog` — minimal modal focus management: move focus in on open, keep Tab
 * inside, restore focus to the trigger on close. Escape is handled by each
 * dialog's own keydown.
 */
export function dialog(node: HTMLElement) {
  const opener = document.activeElement as HTMLElement | null;

  const focusables = () =>
    [...node.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    )].filter((el) => el.offsetParent !== null);

  (focusables()[0] ?? node).focus();

  function onKey(e: KeyboardEvent) {
    if (e.key !== 'Tab') return;
    const f = focusables();
    if (f.length === 0) { e.preventDefault(); return; }
    const first = f[0];
    const last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
    else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
  }

  node.addEventListener('keydown', onKey);
  return {
    destroy() {
      node.removeEventListener('keydown', onKey);
      opener?.focus?.();
    },
  };
}

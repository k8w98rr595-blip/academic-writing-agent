"use client";

import { useEffect, useRef, type ReactNode } from "react";

export function ActionDialog({ title, children, busy, onCancel }: {
  title: string; children: ReactNode; busy: boolean; onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = window.document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => { ref.current?.close(); previous?.focus(); };
  }, []);
  return <dialog ref={ref} className="confirmation-dialog" aria-labelledby="confirmation-title" aria-busy={busy}
    onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="confirmation-title">{title}</h2>{children}
  </dialog>;
}

import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";

type Props = { onConfirm: () => void; onCancel: () => void; onUseApiKey: () => void };

export function LowSpecDialog({ onConfirm, onCancel, onUseApiKey }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    backRef.current?.focus();
    return () => previous?.focus?.();
  }, []);

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onCancel();
    } else if (e.key === "Tab") {
      const items = Array.from(ref.current?.querySelectorAll<HTMLElement>("button") ?? []);
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  };

  return (
    <div className="overlay">
      <div
        className="dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="lowspec-title"
        aria-describedby="lowspec-body"
        ref={ref}
        onKeyDown={onKey}
      >
        <h2 id="lowspec-title">Your device may struggle with this model</h2>
        <p id="lowspec-body">
          Your computer's specs are below what this model needs. Running it may make your computer very slow, freeze
          other apps, or crash Folio. Continue at your own risk, or use your own API key instead.
        </p>
        <div className="dialog-actions">
          <button type="button" className="primary" onClick={onConfirm}>
            Download anyway
          </button>
          <button type="button" ref={backRef} onClick={onCancel}>
            Go back
          </button>
          <button type="button" className="linklike" onClick={onUseApiKey}>
            Use an API key instead
          </button>
        </div>
      </div>
    </div>
  );
}

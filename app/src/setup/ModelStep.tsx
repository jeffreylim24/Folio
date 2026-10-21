import { useCallback, useEffect, useState } from "react";
import { api } from "../engine";

type Recommendation = {
  model: { name: string; size_gb: number; min_budget_gb: number; label: string } | null;
  reason: "ok" | "memory" | "disk";
  message: string;
  est_minutes: number | null;
  free_disk_needed_gb: number | null;
};

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong. Please try again.";
}

type Props = { onDone: () => void; onUseApiKey: () => void };

export function ModelStep({ onDone, onUseApiKey }: Props) {
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setRec(null);
    setError(null);
    try {
      const res = await api<{ recommendation: Recommendation }>("/setup/hardware");
      setRec(res.recommendation);
    } catch (e) {
      setError(messageOf(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const download = async (name: string) => {
    setBusy(true);
    setError(null);
    try {
      await api("/setup/model", { method: "PUT", body: JSON.stringify({ model: name }) });
      onDone();
    } catch (e) {
      setError(messageOf(e));
      setBusy(false);
    }
  };

  if (!rec) {
    return (
      <section className="stack" aria-live="polite">
        <h1>Choose your AI model</h1>
        {error ? (
          <>
            <p role="alert" className="error">
              {error}
            </p>
            <button type="button" className="primary" onClick={() => void load()}>
              Retry
            </button>
          </>
        ) : (
          <p>Checking your computer…</p>
        )}
      </section>
    );
  }

  if (rec.reason === "memory" || !rec.model) {
    const disk = rec.reason === "disk";
    return (
      <section className="stack">
        <h1>Choose your AI model</h1>
        <p>{rec.message}</p>
        {disk ? (
          <button type="button" className="primary" onClick={() => void load()}>
            Check again
          </button>
        ) : (
          <button type="button" className="primary" onClick={onUseApiKey}>
            Use an API key instead
          </button>
        )}
      </section>
    );
  }

  const minutes = rec.est_minutes;
  return (
    <section className="stack">
      <h1>Choose your AI model</h1>
      <p>{rec.message}</p>
      <p>
        <strong>{rec.model.label}</strong>
      </p>
      <p>
        {rec.model.size_gb.toFixed(1)} GB
        {minutes !== null && `, about ${minutes} ${minutes === 1 ? "minute" : "minutes"}`}
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button
        type="button"
        className="primary"
        disabled={busy}
        onClick={() => void download(rec.model!.name)}
      >
        Download
      </button>
    </section>
  );
}

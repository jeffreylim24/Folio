import { useEffect, useRef, useState } from "react";
import { api } from "../engine";
import { usePoll } from "./usePoll";

type RawPull = {
  state: "idle" | "downloading" | "done" | "error";
  completed_bytes: number;
  total_bytes: number;
  error: string | null;
};

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong. Please try again.";
}

export function DownloadStep({ onDone }: { onDone: () => void }) {
  const [pull, setPull] = useState<RawPull | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  const finished = useRef(false);

  const poll = async () => {
    try {
      const next = await api<RawPull>("/setup/pull");
      if (!alive.current) return;
      setError(null);
      setPull(next);
      if (next.state === "done" && !finished.current) {
        finished.current = true;
        onDone();
      }
    } catch (e) {
      if (alive.current) setError(messageOf(e));
    }
  };

  useEffect(() => {
    alive.current = true;
    void poll();
    return () => {
      alive.current = false;
    };
    // Initial poll on mount only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  usePoll(() => void poll(), true);

  const retry = async () => {
    try {
      await api("/setup/pull/retry", { method: "POST" });
      setPull(null);
      await poll();
    } catch (e) {
      if (alive.current) setError(messageOf(e));
    }
  };

  const failure = pull?.state === "error" ? (pull.error ?? "The download failed.") : error;
  const percent =
    pull && pull.total_bytes > 0
      ? Math.floor((pull.completed_bytes / pull.total_bytes) * 100)
      : 0;

  return (
    <section className="stack" aria-live="polite">
      <h1>Downloading your AI model</h1>
      {failure ? (
        <>
          <p role="alert" className="error">
            {failure}
          </p>
          <button type="button" className="primary" onClick={() => void retry()}>
            Retry
          </button>
        </>
      ) : (
        <>
          <progress max={100} value={percent} />
          <p>{percent}%</p>
        </>
      )}
      <p>
        It's safe to close Folio; the download picks up where it left off.
      </p>
    </section>
  );
}

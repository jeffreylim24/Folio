import { useEffect, useState } from "react";
import { api } from "../engine";

type Result = { status: "testing" } | { status: "ok" } | { status: "error"; message: string };

export function ReadyStep({ onDone }: { onDone: () => void }) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result>({ status: "testing" });

  useEffect(() => {
    let cancelled = false;
    setResult({ status: "testing" });
    api("/setup/test", { method: "POST" })
      .then(() => !cancelled && setResult({ status: "ok" }))
      .catch((e: unknown) => {
        if (cancelled) return;
        setResult({
          status: "error",
          message:
            e instanceof Error ? e.message : "Something went wrong. Please try again.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (result.status === "testing") {
    return (
      <section className="stack" aria-live="polite">
        <h1>Almost there</h1>
        <p>Making sure everything works...</p>
      </section>
    );
  }
  if (result.status === "error") {
    return (
      <section className="stack">
        <h1>That didn't work</h1>
        <p role="alert" className="error">
          {result.message}
        </p>
        <button type="button" className="primary" onClick={() => setAttempt((n) => n + 1)}>
          Retry
        </button>
      </section>
    );
  }
  return (
    <section className="stack">
      <h1>You're all set</h1>
      <p>Folio can talk to its AI. Let's get started.</p>
      <button type="button" className="primary" onClick={onDone}>
        Open Folio
      </button>
    </section>
  );
}


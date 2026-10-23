import { useEffect, useState } from "react";
import { api } from "../engine";
import { StepShell } from "../ui/StepShell";
import type { StepPosition } from "./flow";

type Result = { status: "testing" } | { status: "ok" } | { status: "error"; message: string };

type Props = {
  position: StepPosition;
  onDone: () => void;
  /** Back to picking another model; only offered for API providers. */
  onChooseModel?: () => void;
  /** Back to choosing between running privately and an API key. */
  onChangeProvider: () => void;
};

export function ReadyStep({ position, onDone, onChooseModel, onChangeProvider }: Props) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result>({ status: "testing" });

  useEffect(() => {
    let cancelled = false;
    setResult({ status: "testing" });
    api("/setup/test", { method: "POST" }, 180_000)
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
      <StepShell step={position} title="Almost there" live="polite">
        <div className="spinner" aria-hidden="true" />
        <p>Making sure everything works...</p>
      </StepShell>
    );
  }
  if (result.status === "error") {
    return (
      <StepShell step={position} title="That didn't work">
        <p role="alert" className="error">
          {result.message}
        </p>
        <button type="button" className="primary" onClick={() => setAttempt((n) => n + 1)}>
          Retry
        </button>
        {onChooseModel && (
          <button type="button" onClick={onChooseModel}>
            Choose a different model
          </button>
        )}
        <button type="button" onClick={onChangeProvider}>
          Change how Folio's AI runs
        </button>
      </StepShell>
    );
  }
  return (
    <StepShell step={position} title="You're all set" lede="Folio can talk to its AI. Let's get started.">
      <svg className="check-mark" viewBox="0 0 56 56" aria-hidden="true">
        <circle cx="28" cy="28" r="26" />
        <path d="M17 29l8 8 14-17" />
      </svg>
      <button type="button" className="primary" onClick={onDone}>
        Open Folio
      </button>
    </StepShell>
  );
}


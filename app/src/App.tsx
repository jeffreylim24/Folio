import { useCallback, useEffect, useState } from "react";
import { getEngineInfo, restartEngine } from "./engine";
import { SetupWizard } from "./setup/SetupWizard";
import "./App.css";

type Status = { kind: "starting" } | { kind: "ready" } | { kind: "error"; detail: string };

function describe(e: unknown): string {
  return typeof e === "string" ? e : e instanceof Error ? e.message : "";
}

export default function App() {
  const [status, setStatus] = useState<Status>({ kind: "starting" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatus({ kind: "starting" });
    getEngineInfo().then(
      () => !cancelled && setStatus({ kind: "ready" }),
      (e: unknown) => !cancelled && setStatus({ kind: "error", detail: describe(e) }),
    );
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const onEngineProblem = useCallback(
    (detail: string) => setStatus({ kind: "error", detail }),
    [],
  );

  async function retry() {
    try {
      await restartEngine();
    } catch (e) {
      setStatus({ kind: "error", detail: describe(e) });
      return;
    }
    setAttempt((n) => n + 1);
  }

  if (status.kind === "starting") {
    return (
      <main className="page" aria-busy="true">
        <p>Starting Folio...</p>
      </main>
    );
  }
  if (status.kind === "error") {
    return (
      <main className="page stack">
        <h1>Folio's engine didn't start</h1>
        <p>Folio needs its background engine to work. Trying again often fixes this.</p>
        {status.detail && <p className="detail">{status.detail}</p>}
        <button type="button" className="primary" onClick={() => void retry()}>
          Retry
        </button>
      </main>
    );
  }
  return <SetupWizard onEngineProblem={onEngineProblem} />;
}

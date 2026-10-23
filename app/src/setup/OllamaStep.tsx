import { useCallback, useEffect, useRef, useState } from "react";
import { api, type OllamaStatus } from "../engine";
import { ProgressBar } from "../ui/ProgressBar";
import { StepShell } from "../ui/StepShell";
import type { StepPosition } from "./flow";
import { isWindows } from "../platform";
import { usePoll } from "./usePoll";

type RawStatus = { installed: boolean; running: boolean };
type Job = "install" | "update";
type InstallStatus = {
  state: "idle" | "downloading" | "stopping" | "installing" | "starting" | "done" | "error";
  progress: number;
  message: string | null;
};

type View =
  | { kind: "checking" }
  | { kind: "starting" }
  | { kind: "didnt-start" }
  | { kind: "not-installed" }
  | { kind: "outdated"; version: string | null; updatable: boolean }
  | { kind: "installing"; job: Job; status: InstallStatus | null }
  | { kind: "install-error"; job: Job; message: string };

const MIN_VERSION = "0.32.12";

const INSTALL_LABEL: Record<string, string> = {
  downloading: "Downloading Ollama",
  stopping: "Closing Ollama…",
  installing: "Installing Ollama",
  starting: "Starting Ollama…",
};

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong. Please try again.";
}

type Props = { position: StepPosition; onDone: () => void; onUseApiKey: () => void };

export function OllamaStep({ position, onDone, onUseApiKey }: Props) {
  const [view, setView] = useState<View>({ kind: "checking" });
  const alive = useRef(true);
  const finished = useRef(false);
  const finish = useCallback(() => {
    if (finished.current) return;
    finished.current = true;
    onDone();
  }, [onDone]);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const check = useCallback(async () => {
    setView({ kind: "checking" });
    try {
      const status = await api<RawStatus & Partial<OllamaStatus>>("/setup/ollama");
      if (!alive.current) return;
      if (!status.installed) return setView({ kind: "not-installed" });
      if (status.outdated) {
        return setView({
          kind: "outdated",
          version: status.version ?? null,
          updatable: Boolean(status.updatable),
        });
      }
      if (status.running) return finish();
      setView({ kind: "starting" });
      const started = await api<{ running: boolean }>(
        "/setup/ollama/start",
        { method: "POST" },
        45_000,
      );
      if (!alive.current) return;
      if (started.running) finish();
      else setView({ kind: "didnt-start" });
    } catch (e) {
      if (alive.current) setView({ kind: "install-error", job: "install", message: messageOf(e) });
    }
  }, [finish]);

  useEffect(() => {
    void check();
    // Only on mount; later checks are button-driven.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async (job: Job) => {
    setView({ kind: "installing", job, status: null });
    try {
      await api(job === "update" ? "/setup/ollama/update" : "/setup/ollama/install", {
        method: "POST",
      });
    } catch (e) {
      if (alive.current) setView({ kind: "install-error", job, message: messageOf(e) });
    }
  };

  // Answers only count while the screen is still showing the install.
  const whileInstalling = (next: (job: Job) => View) => (v: View) =>
    v.kind === "installing" ? next(v.job) : v;
  const pollInstall = async () => {
    try {
      const status = await api<InstallStatus>("/setup/ollama/install");
      if (!alive.current) return;
      if (status.state === "done") return finish();
      if (status.state === "error") {
        return setView(
          whileInstalling((job) => ({
            kind: "install-error",
            job,
            message: status.message ?? "Something went wrong. Please try again.",
          })),
        );
      }
      setView(whileInstalling((job) => ({ kind: "installing", job, status })));
    } catch (e) {
      if (alive.current) {
        setView(whileInstalling((job) => ({ kind: "install-error", job, message: messageOf(e) })));
      }
    }
  };
  usePoll(pollInstall, view.kind === "installing");

  if (view.kind === "checking" || view.kind === "starting") {
    return (
      <StepShell step={position} title="Setting up Ollama" live="polite">
        <p>{view.kind === "starting" ? "Starting Ollama…" : "Checking for Ollama…"}</p>
      </StepShell>
    );
  }
  const apiKeyButton = (
    <button type="button" onClick={onUseApiKey}>
      Use an API key instead
    </button>
  );
  if (view.kind === "didnt-start") {
    return (
      <StepShell step={position} title="Setting up Ollama">
        <p role="alert" className="error">
          Ollama didn't start. Try opening it from{" "}
          {isWindows() ? "the Start menu" : "your Applications folder"}, then click Check again.
        </p>
        <button type="button" className="primary" onClick={() => void check()}>
          Check again
        </button>
        {apiKeyButton}
      </StepShell>
    );
  }
  if (view.kind === "outdated") {
    return (
      <StepShell
        step={position}
        title="Ollama needs an update"
        lede={`Your Ollama${view.version ? ` is version ${view.version}` : " is out of date"}. Folio needs version ${MIN_VERSION} or newer to run models.`}
      >
        {view.updatable ? (
          <>
            <p className="detail">
              Folio will close Ollama, install the newest version and start it again.
            </p>
            <button type="button" className="primary" onClick={() => void run("update")}>
              Update Ollama
            </button>
          </>
        ) : (
          <>
            <p className="warning">
              Download the latest version from ollama.com/download and install it, then click Check
              again.
            </p>
            <button type="button" className="primary" onClick={() => void check()}>
              Check again
            </button>
          </>
        )}
        {apiKeyButton}
      </StepShell>
    );
  }
  if (view.kind === "installing") {
    const s = view.status;
    const updating = view.job === "update";
    const percent = s ? Math.floor(s.progress * 100) : 0;
    const showPercent = !s || s.state === "downloading";
    const known = showPercent || s?.state === "done";
    return (
      <StepShell
        step={position}
        title={updating ? "Updating Ollama" : "Installing Ollama"}
        live="polite"
      >
        <p>
          {s && INSTALL_LABEL[s.state] ? INSTALL_LABEL[s.state] : "Getting started…"}
          {showPercent && ` ${percent}%`}
        </p>
        <ProgressBar
          value={known ? s?.progress ?? 0 : undefined}
          label={updating ? "Updating Ollama" : "Installing Ollama"}
        />
      </StepShell>
    );
  }
  const updateFailed = view.kind === "install-error" && view.job === "update";
  return (
    <StepShell
      step={position}
      title={updateFailed ? "Ollama needs an update" : "Install Ollama"}
      lede={
        updateFailed
          ? undefined
          : "Ollama is the free app that runs AI models privately on your computer."
      }
    >
      {view.kind === "install-error" && (
        <p role="alert" className="error">
          {view.message}
        </p>
      )}
      <button
        type="button"
        className="primary"
        onClick={() => void run(updateFailed ? "update" : "install")}
      >
        {view.kind === "install-error" ? "Retry" : "Install Ollama"}
      </button>
      {apiKeyButton}
    </StepShell>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type OllamaStatus } from "../engine";
import { isWindows } from "../platform";
import { usePoll } from "./usePoll";

type RawStatus = { installed: boolean; running: boolean };
type InstallStatus = {
  state: "idle" | "downloading" | "installing" | "starting" | "done" | "error";
  progress: number;
  message: string | null;
};

type View =
  | { kind: "checking" }
  | { kind: "starting" }
  | { kind: "didnt-start" }
  | { kind: "not-installed" }
  | { kind: "installing"; status: InstallStatus | null }
  | { kind: "install-error"; message: string };

const INSTALL_LABEL: Record<string, string> = {
  downloading: "Downloading Ollama",
  installing: "Installing Ollama",
  starting: "Starting Ollama…",
};

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong. Please try again.";
}

type Props = { onDone: () => void; onUseApiKey: () => void };

export function OllamaStep({ onDone, onUseApiKey }: Props) {
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
      if (status.running) return finish();
      setView({ kind: "starting" });
      const started = await api<{ running: boolean }>("/setup/ollama/start", { method: "POST" });
      if (!alive.current) return;
      if (started.running) finish();
      else setView({ kind: "didnt-start" });
    } catch (e) {
      if (alive.current) setView({ kind: "install-error", message: messageOf(e) });
    }
  }, [finish]);

  useEffect(() => {
    void check();
    // Only on mount; later checks are button-driven.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const install = async () => {
    setView({ kind: "installing", status: null });
    try {
      await api("/setup/ollama/install", { method: "POST" });
    } catch (e) {
      if (alive.current) setView({ kind: "install-error", message: messageOf(e) });
    }
  };

  // Answers only count while the screen is still showing the install.
  const whileInstalling = (next: View) => (v: View) =>
    v.kind === "installing" ? next : v;
  const pollInstall = async () => {
    try {
      const status = await api<InstallStatus>("/setup/ollama/install");
      if (!alive.current) return;
      if (status.state === "done") return finish();
      if (status.state === "error") {
        return setView(
          whileInstalling({
            kind: "install-error",
            message: status.message ?? "Something went wrong. Please try again.",
          }),
        );
      }
      setView(whileInstalling({ kind: "installing", status }));
    } catch (e) {
      if (alive.current) {
        setView(whileInstalling({ kind: "install-error", message: messageOf(e) }));
      }
    }
  };
  usePoll(pollInstall, view.kind === "installing");

  if (view.kind === "checking" || view.kind === "starting") {
    return (
      <section className="stack" aria-live="polite">
        <h1>Setting up Ollama</h1>
        <p>{view.kind === "starting" ? "Starting Ollama…" : "Checking for Ollama…"}</p>
      </section>
    );
  }
  if (view.kind === "didnt-start") {
    return (
      <section className="stack">
        <h1>Setting up Ollama</h1>
        <p role="alert" className="error">
          Ollama didn't start. Try opening it from{" "}
          {isWindows() ? "the Start menu" : "your Applications folder"}, then click Check again.
        </p>
        <button type="button" className="primary" onClick={() => void check()}>
          Check again
        </button>
        <button type="button" onClick={onUseApiKey}>
          Use an API key instead
        </button>
      </section>
    );
  }
  if (view.kind === "installing") {
    const s = view.status;
    const percent = s ? Math.floor(s.progress * 100) : 0;
    return (
      <section className="stack" aria-live="polite">
        <h1>Installing Ollama</h1>
        <p>
          {s && INSTALL_LABEL[s.state] ? INSTALL_LABEL[s.state] : "Getting started…"}
          {(!s || s.state === "downloading") && ` ${percent}%`}
        </p>
        <progress max={100} value={percent} />
      </section>
    );
  }
  return (
    <section className="stack">
      <h1>Install Ollama</h1>
      <p>
        Ollama is the free app that runs AI models privately on your computer.
      </p>
      {view.kind === "install-error" && (
        <p role="alert" className="error">
          {view.message}
        </p>
      )}
      <button type="button" className="primary" onClick={() => void install()}>
        {view.kind === "install-error" ? "Retry" : "Install Ollama"}
      </button>
      <button type="button" onClick={onUseApiKey}>
        Use an API key instead
      </button>
    </section>
  );
}

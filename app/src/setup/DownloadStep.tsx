import { useEffect, useRef, useState } from "react";
import { api } from "../engine";
import { ProgressBar } from "../ui/ProgressBar";
import { StepShell } from "../ui/StepShell";
import type { StepPosition } from "./flow";
import { DownloadArt } from "./DownloadArt";
import { TIPS } from "./tips";
import { usePoll } from "./usePoll";

type RawPull = {
  state: "idle" | "downloading" | "stalled" | "done" | "error";
  completed_bytes: number;
  total_bytes: number;
  error: string | null;
  resuming?: boolean;
};

const TIP_MS = 10_000;
const WINDOW_MS = 30_000;
const MIN_SAMPLE_MS = 5_000;

type Sample = { t: number; bytes: number };

const defaultRandomIndex = (n: number) => Math.floor(Math.random() * n);

function formatSize(done: number, total: number): string {
  if (total >= 1e9) return `${(done / 1e9).toFixed(1)} of ${(total / 1e9).toFixed(1)} GB`;
  return `${Math.round(done / 1e6)} of ${Math.round(total / 1e6)} MB`;
}

function formatLeft(seconds: number): string {
  if (seconds < 60) return "Less than a minute left";
  return `About ${Math.round(seconds / 60)} min left`;
}

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong. Please try again.";
}

type Props = {
  position: StepPosition;
  onDone: () => void;
  onUseApiKey: () => void;
  /** Picks the first tip. Injectable so tests are deterministic. */
  randomIndex?: (count: number) => number;
};

export function DownloadStep({ position, onDone, onUseApiKey, randomIndex = defaultRandomIndex }: Props) {
  const [pull, setPull] = useState<RawPull | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tip, setTip] = useState(() => randomIndex(TIPS.length));
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const samples = useRef<Sample[]>([]);
  const alive = useRef(true);
  const finished = useRef(false);
  // "idle" means nothing has started the download (e.g. Ollama was not running
  // when Folio opened). Ask the engine to start it, but only once.
  const kicked = useRef(false);
  // Bumped by Retry so answers to earlier requests are dropped.
  const generation = useRef(0);

  // Bytes per second over the last 30 s of polls; hidden until 5 s of samples.
  const trackSpeed = (next: RawPull) => {
    if (next.state !== "downloading" || next.resuming) {
      samples.current = [];
      setSecondsLeft(null);
      return;
    }
    const now = Date.now();
    const kept = samples.current.filter((s) => now - s.t <= WINDOW_MS);
    kept.push({ t: now, bytes: next.completed_bytes });
    samples.current = kept;
    const first = kept[0];
    const dt = now - first.t;
    const rate = dt > 0 ? ((next.completed_bytes - first.bytes) / dt) * 1000 : 0;
    if (dt >= MIN_SAMPLE_MS && rate > 0 && next.total_bytes > 0) {
      setSecondsLeft((next.total_bytes - next.completed_bytes) / rate);
    } else {
      setSecondsLeft(null);
    }
  };

  const poll = async () => {
    const mine = generation.current;
    try {
      const next = await api<RawPull>("/setup/pull");
      if (!alive.current || mine !== generation.current) return;
      setError(null);
      setPull(next);
      trackSpeed(next);
      if (next.state === "done" && !finished.current) {
        finished.current = true;
        onDone();
      }
      if (next.state === "idle" && !kicked.current) {
        kicked.current = true;
        void retry();
      }
    } catch (e) {
      if (alive.current && mine === generation.current) setError(messageOf(e));
    }
  };

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  usePoll(poll, true, true);

  const retry = async () => {
    generation.current += 1;
    samples.current = [];
    try {
      await api("/setup/pull/retry", { method: "POST" });
      setPull(null);
      await poll();
    } catch (e) {
      if (alive.current) setError(messageOf(e));
    }
  };

  const failure = pull?.state === "error" ? (pull.error ?? "The download failed.") : error;
  const stalled = !failure && pull?.state === "stalled";
  const resuming = !failure && !stalled && pull?.resuming === true;
  const showTips = !failure && !stalled;
  const known = pull !== null && pull.total_bytes > 0;
  const fraction = known ? pull.completed_bytes / pull.total_bytes : 0;
  const percent = Math.floor(fraction * 100);

  useEffect(() => {
    if (!showTips) return;
    const id = setInterval(() => setTip((t) => (t + 1) % TIPS.length), TIP_MS);
    return () => clearInterval(id);
  }, [showTips]);

  return (
    <StepShell step={position} title="Downloading your AI model" live="polite">
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
          <DownloadArt paused={stalled} />
          <ProgressBar value={fraction} label="Download progress" />
          <div className="download-meta">
            <span>{percent}%</span>
            {resuming && <span>Resuming…</span>}
          </div>
          {known && !resuming && (
            <p className="download-meta">
              <span>{formatSize(pull.completed_bytes, pull.total_bytes)}</span>
              {secondsLeft !== null && !stalled && <span>{formatLeft(secondsLeft)}</span>}
            </p>
          )}
          {stalled && (
            <p className="warning paused-note">
              Download paused. Check your internet connection. It'll pick up where it left off when you're back online.
            </p>
          )}
          {showTips && (
            <p className="download-tip" data-testid="tip" key={tip}>
              {TIPS[tip]}
            </p>
          )}
        </>
      )}
      <p>
        It's safe to close Folio; the download picks up where it left off.
      </p>
      <button type="button" onClick={onUseApiKey}>
        Use an API key instead
      </button>
    </StepShell>
  );
}

import { invoke } from "@tauri-apps/api/core";

export type ProviderName =
  | "ollama"
  | "anthropic"
  | "openai"
  | "gemini"
  | "openai_compatible";

export type Settings = {
  provider: ProviderName | null;
  model: string | null;
  baseUrl: string | null;
  setupComplete: boolean;
};

export type OllamaStatus = {
  installed: boolean;
  running: boolean;
  version: string | null;
  appPath: string | null;
  outdated: boolean;
  updatable: boolean;
};

export type PullStatus = {
  state: "idle" | "downloading" | "stalled" | "done" | "error";
  model: string | null;
  completedBytes: number;
  totalBytes: number;
  error: string | null;
  resuming: boolean;
};

export type SetupState = {
  settings: Settings;
  hasApiKey: boolean;
  ollama: OllamaStatus | null;
  pull: PullStatus;
};

export class EngineError extends Error {
  kind: string;
  constructor(kind: string, message: string) {
    super(message);
    this.name = "EngineError";
    this.kind = kind;
  }
}

type EngineInfo = { port: number; token: string };

let cachedInfo: Promise<EngineInfo> | null = null;

export function getEngineInfo(): Promise<EngineInfo> {
  if (!cachedInfo) {
    const pending = invoke<EngineInfo>("engine_info");
    cachedInfo = pending;
    // Do not cache a failure: the next call should ask again.
    pending.catch(() => {
      if (cachedInfo === pending) cachedInfo = null;
    });
  }
  return cachedInfo;
}

export function resetEngineCache(): void {
  cachedInfo = null;
}

export async function restartEngine(): Promise<void> {
  resetEngineCache();
  await invoke("restart_engine");
}

const NETWORK_MESSAGE =
  "Folio couldn't reach its engine. Please try again.";
const GENERIC_MESSAGE = "Something went wrong. Please try again.";

async function toEngineError(res: Response): Promise<EngineError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // fall through to the generic message
  }
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (typeof b.message === "string") {
      return new EngineError(typeof b.kind === "string" ? b.kind : "other", b.message);
    }
    if (typeof b.detail === "string") return new EngineError("other", b.detail);
  }
  return new EngineError("other", GENERIC_MESSAGE);
}

const TIMEOUT_MESSAGE = "Folio's engine took too long to answer. Please try again.";

export async function api<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = 15_000,
): Promise<T> {
  const { port, token } = await getEngineInfo();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const controller = new AbortController();
  const callerSignal = init.signal;
  const onCallerAbort = () => controller.abort();
  if (callerSignal) {
    if (callerSignal.aborted) controller.abort();
    else callerSignal.addEventListener("abort", onCallerAbort);
  }
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    let res: Response;
    try {
      res = await fetch(`http://127.0.0.1:${port}${path}`, {
        ...init,
        headers,
        signal: controller.signal,
      });
    } catch {
      if (timedOut) throw new EngineError("timeout", TIMEOUT_MESSAGE);
      if (callerSignal?.aborted) throw new DOMException("The request was aborted.", "AbortError");
      throw new EngineError("network", NETWORK_MESSAGE);
    }
    if (!res.ok) throw await toEngineError(res);
    return (await res.json()) as T;
  } catch (e) {
    if (timedOut && !(e instanceof EngineError && e.kind === "timeout")) {
      throw new EngineError("timeout", TIMEOUT_MESSAGE);
    }
    throw e;
  } finally {
    clearTimeout(timer);
    callerSignal?.removeEventListener("abort", onCallerAbort);
  }
}

export function jsonBody(value: unknown): RequestInit {
  return { method: "POST", body: JSON.stringify(value) };
}

type RawState = {
  settings: {
    provider: ProviderName | null;
    model: string | null;
    base_url: string | null;
    setup_complete: boolean;
  };
  has_api_key: boolean;
  ollama: {
    installed: boolean;
    running: boolean;
    version: string | null;
    app_path: string | null;
    outdated: boolean;
    updatable: boolean;
  } | null;
  pull: {
    state: PullStatus["state"];
    model: string | null;
    completed_bytes: number;
    total_bytes: number;
    error: string | null;
    resuming: boolean;
  };
};

export async function getSetupState(): Promise<SetupState> {
  const raw = await api<RawState>("/setup/state");
  return {
    settings: {
      provider: raw.settings.provider,
      model: raw.settings.model,
      baseUrl: raw.settings.base_url,
      setupComplete: raw.settings.setup_complete,
    },
    hasApiKey: raw.has_api_key,
    ollama: raw.ollama && {
      installed: raw.ollama.installed,
      running: raw.ollama.running,
      version: raw.ollama.version,
      appPath: raw.ollama.app_path,
      outdated: raw.ollama.outdated,
      updatable: raw.ollama.updatable,
    },
    pull: {
      state: raw.pull.state,
      model: raw.pull.model,
      completedBytes: raw.pull.completed_bytes,
      totalBytes: raw.pull.total_bytes,
      error: raw.pull.error,
      resuming: raw.pull.resuming,
    },
  };
}

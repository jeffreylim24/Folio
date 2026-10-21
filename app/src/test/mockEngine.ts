import { vi } from "vitest";

export type Reply = { status?: number; body: unknown };
export type Routes = Record<string, Reply | (() => Reply)>;

export const IDLE_PULL = {
  state: "idle",
  model: null,
  completed_bytes: 0,
  total_bytes: 0,
  error: null,
};

export function rawState(over: Record<string, unknown> = {}) {
  return {
    settings: { provider: null, model: null, base_url: null, setup_complete: false },
    has_api_key: false,
    ollama: { installed: true, running: true, version: "0.1", app_path: null },
    pull: IDLE_PULL,
    ...over,
  };
}

/** Stubs global fetch. Keys look like "GET /setup/state". Returns the mock. */
export function stubFetch(routes: Routes) {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    const key = `${init?.method ?? "GET"} ${path}`;
    const route = routes[key];
    if (!route) throw new Error(`unexpected request: ${key}`);
    const reply = typeof route === "function" ? route() : route;
    return new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

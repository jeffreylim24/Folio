import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async () => ({ port: 1234, token: "t" })),
}));

import { api, resetEngineCache } from "./engine";

beforeEach(() => {
  resetEngineCache();
  vi.useFakeTimers();
  vi.stubGlobal(
    "fetch",
    vi.fn((_url: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        // Like real fetch, reject at once if the signal is already aborted.
        if (init?.signal?.aborted) reject(new DOMException("aborted", "AbortError"));
        init?.signal?.addEventListener("abort", () =>
          reject(new DOMException("aborted", "AbortError")),
        );
      });
    }),
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("api timeouts", () => {
  it("api times out", async () => {
    const p = api("/slow");
    const caught = p.catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(15_000);
    const err = (await caught) as { kind: string; message: string };
    expect(err.kind).toBe("timeout");
    expect(err.message).toBe("Folio's engine took too long to answer. Please try again.");
  });

  it("api passes custom timeout", async () => {
    let settled = false;
    const p = api("/slow", {}, 30_000);
    p.catch(() => {}).finally(() => {
      settled = true;
    });
    await vi.advanceTimersByTimeAsync(15_000);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(15_000);
    expect(settled).toBe(true);
  });

  it("rejects as an abort when the caller aborts", async () => {
    const ctl = new AbortController();
    const caught = api("/slow", { signal: ctl.signal }).catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(100);
    ctl.abort();
    const err = (await caught) as { name: string; kind?: string };
    expect(err.name).toBe("AbortError");
    expect(err.kind).toBeUndefined();
  });

  it("rejects immediately for an already-aborted signal", async () => {
    const ctl = new AbortController();
    ctl.abort();
    const err = (await api("/slow", { signal: ctl.signal }).catch((e: unknown) => e)) as {
      name: string;
    };
    expect(err.name).toBe("AbortError");
  });

  it("still reports a plain fetch failure as network", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("boom"); }));
    const err = (await api("/x").catch((e: unknown) => e)) as { kind: string };
    expect(err.kind).toBe("network");
  });
});

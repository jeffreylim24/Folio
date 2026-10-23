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
});

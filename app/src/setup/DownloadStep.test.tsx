import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { resetEngineCache } from "../engine";
import { stubFetch } from "../test/mockEngine";
import { DownloadStep } from "./DownloadStep";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

const pull = (state: string, completed: number, total: number, error: string | null = null) => ({
  body: { state, model: "qwen3:14b", completed_bytes: completed, total_bytes: total, error },
});
const settle = (ms = 0) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
const count = (mock: ReturnType<typeof stubFetch>, key: string) =>
  mock.mock.calls.filter(([url, init]) => `${init?.method ?? "GET"} ${new URL(url).pathname}` === key).length;

beforeEach(() => {
  vi.useFakeTimers();
  resetEngineCache();
  vi.mocked(invoke).mockResolvedValue({ port: 1, token: "t" });
  vi.unstubAllGlobals();
});
afterEach(() => vi.useRealTimers());

describe("DownloadStep", () => {
  it("polls once a second and shows a floored percent", async () => {
    const fetchMock = stubFetch({ "GET /setup/pull": pull("downloading", 2, 3) });
    render(<DownloadStep onDone={() => {}} />);
    await settle();
    expect(screen.getByText("66%")).toBeTruthy();
    expect(screen.getByText(/the download picks up where it left off/)).toBeTruthy();
    expect(count(fetchMock, "GET /setup/pull")).toBe(1);
    await settle(1000);
    expect(count(fetchMock, "GET /setup/pull")).toBe(2);
    await settle(1000);
    expect(count(fetchMock, "GET /setup/pull")).toBe(3);
  });

  it("shows 0% when the total is not known yet", async () => {
    stubFetch({ "GET /setup/pull": pull("downloading", 0, 0) });
    render(<DownloadStep onDone={() => {}} />);
    await settle();
    expect(screen.getByText("0%")).toBeTruthy();
  });

  it("continues when the download is done", async () => {
    stubFetch({ "GET /setup/pull": pull("done", 3, 3) });
    const onDone = vi.fn();
    render(<DownloadStep onDone={onDone} />);
    await settle();
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("shows the error and retries", async () => {
    let failing = true;
    const fetchMock = stubFetch({
      "GET /setup/pull": () => (failing ? pull("error", 1, 3, "Not enough disk space.") : pull("downloading", 1, 3)),
      "POST /setup/pull/retry": { status: 202, body: { started: true } },
    });
    render(<DownloadStep onDone={() => {}} />);
    await settle();
    expect(screen.getByRole("alert").textContent).toBe("Not enough disk space.");
    failing = false;
    await act(async () => { screen.getByRole("button", { name: "Retry" }).click(); });
    await settle(1000);
    expect(count(fetchMock, "POST /setup/pull/retry")).toBe(1);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("33%")).toBeTruthy();
  });

  it("stops polling on unmount", async () => {
    const fetchMock = stubFetch({ "GET /setup/pull": pull("downloading", 1, 3) });
    const { unmount } = render(<DownloadStep onDone={() => {}} />);
    await settle();
    unmount();
    await settle(3000);
    expect(count(fetchMock, "GET /setup/pull")).toBe(1);
  });

  it("keeps only one request in flight when the engine is slow", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", (url: string) => {
      calls.push(new URL(url).pathname);
      return new Promise<Response>(() => {});
    });
    render(<DownloadStep onDone={() => {}} />);
    await settle(5000);
    expect(calls.filter((c) => c === "/setup/pull")).toHaveLength(1);
  });

  it("ignores a response that was requested before Retry", async () => {
    const pending: Array<(r: Response) => void> = [];
    const reply = (body: object) =>
      new Response(JSON.stringify(body), { status: 200 });
    const pullBody = (state: string, completed: number, error: string | null) => ({
      state, model: "m", completed_bytes: completed, total_bytes: 3, error,
    });
    let gets = 0;
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      if (path === "/setup/pull/retry") return Promise.resolve(reply({ started: true }));
      if (init?.method) throw new Error("unexpected");
      gets += 1;
      if (gets === 1) return Promise.resolve(reply(pullBody("error", 1, "Old error")));
      return new Promise<Response>((resolve) => pending.push(resolve));
    });
    render(<DownloadStep onDone={() => {}} />);
    await settle();
    expect(screen.getByRole("alert").textContent).toBe("Old error");
    await settle(1000); // tick: GET #2 stays open
    expect(pending).toHaveLength(1);
    await act(async () => { screen.getByRole("button", { name: "Retry" }).click(); });
    await settle(); // retry's own poll: GET #3
    expect(pending).toHaveLength(2);
    await act(async () => { pending[1](reply(pullBody("downloading", 1, null))); });
    await act(async () => { pending[0](reply(pullBody("error", 1, "Old error"))); });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("33%")).toBeTruthy();
  });
});

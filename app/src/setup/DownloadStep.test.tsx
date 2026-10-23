import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { resetEngineCache } from "../engine";
import { stubFetch } from "../test/mockEngine";
import { DownloadStep } from "./DownloadStep";
import { TIPS } from "./tips";

const POSITION = { n: 1, total: 5, label: "Test" };

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

const pull = (state: string, completed: number, total: number, error: string | null = null) => ({
  body: { state, model: "qwen3:14b", completed_bytes: completed, total_bytes: total, error },
});
const pullX = (state: string, completed: number, total: number, extra: object = {}) => ({
  body: { state, model: "qwen3:14b", completed_bytes: completed, total_bytes: total, error: null, resuming: false, ...extra },
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
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
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
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle();
    expect(screen.getByText("0%")).toBeTruthy();
  });

  it("continues when the download is done", async () => {
    stubFetch({ "GET /setup/pull": pull("done", 3, 3) });
    const onDone = vi.fn();
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={onDone} />);
    await settle();
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("shows the error and retries", async () => {
    let failing = true;
    const fetchMock = stubFetch({
      "GET /setup/pull": () => (failing ? pull("error", 1, 3, "Not enough disk space.") : pull("downloading", 1, 3)),
      "POST /setup/pull/retry": { status: 202, body: { started: true } },
    });
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
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
    const { unmount } = render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
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
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
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
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
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

  it("starts the download once when the engine reports idle", async () => {
    const fetchMock = stubFetch({
      "GET /setup/pull": pull("idle", 0, 0),
      "POST /setup/pull/retry": { status: 202, body: { started: true } },
    });
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle();
    await settle(3000);
    expect(count(fetchMock, "POST /setup/pull/retry")).toBe(1);
  });

  it("does not retry on its own while downloading", async () => {
    const fetchMock = stubFetch({ "GET /setup/pull": pull("downloading", 1, 3) });
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle(3000);
    expect(count(fetchMock, "POST /setup/pull/retry")).toBe(0);
  });

  it("offers an API key instead", async () => {
    stubFetch({ "GET /setup/pull": pull("downloading", 1, 3) });
    const onUseApiKey = vi.fn();
    render(<DownloadStep position={POSITION} onUseApiKey={onUseApiKey} onDone={() => {}} />);
    await settle();
    await act(async () => { screen.getByRole("button", { name: "Use an API key instead" }).click(); });
    expect(onUseApiKey).toHaveBeenCalledTimes(1);
  });

  it("does not make the whole card a live region, only the status messages", async () => {
    stubFetch({ "GET /setup/pull": pull("downloading", 2, 3) });
    const { container } = render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle();
    expect(container.querySelector("[aria-live]")).toBeNull();
    expect(screen.getByText("66%").closest("[role=status]")).toBeNull();
    expect(screen.getByTestId("tip").closest("[role=status]")).toBeNull();
  });

  it("keeps the last percentage visible next to an error", async () => {
    stubFetch({
      "GET /setup/pull": {
        body: { state: "error", completed_bytes: 600, total_bytes: 1000, error: "The download was interrupted." },
      },
    });
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle();
    expect(screen.getByRole("alert").textContent).toBe("The download was interrupted.");
    expect(screen.getByText("60%")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("stalled shows a paused message, keeps the percent, and hides tips and Retry", async () => {
    stubFetch({ "GET /setup/pull": pullX("stalled", 600, 1000) });
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} randomIndex={() => 0} />);
    await settle();
    expect(screen.getByText("Download paused. Check your internet connection. It'll pick up where it left off when you're back online.")).toBeTruthy();
    expect(screen.getByText("60%")).toBeTruthy();
    expect(screen.queryByTestId("tip")).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("goes back to normal when a stalled download starts moving", async () => {
    let state = "stalled";
    stubFetch({ "GET /setup/pull": () => pullX(state, 600, 1000) });
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} randomIndex={() => 0} />);
    await settle();
    expect(screen.getByText(/Download paused/)).toBeTruthy();
    state = "downloading";
    await settle(1000);
    expect(screen.queryByText(/Download paused/)).toBeNull();
    expect(screen.getByTestId("tip").textContent).toBe(TIPS[0]);
  });

  it("shows Resuming with the last saved progress", async () => {
    stubFetch({ "GET /setup/pull": pullX("downloading", 600, 1000, { resuming: true }) });
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} randomIndex={() => 0} />);
    await settle();
    expect(screen.getByText("Resuming…")).toBeTruthy();
    expect(screen.getByText("60%")).toBeTruthy();
  });

  it("rotates the tip every 10 seconds", async () => {
    stubFetch({ "GET /setup/pull": pullX("downloading", 1, 3) });
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} randomIndex={() => 2} />);
    await settle();
    expect(screen.getByTestId("tip").textContent).toBe(TIPS[2]);
    await settle(9000);
    expect(screen.getByTestId("tip").textContent).toBe(TIPS[2]);
    await settle(1000);
    expect(screen.getByTestId("tip").textContent).toBe(TIPS[3]);
  });

  it("shows size and time left once there are 5 seconds of samples", async () => {
    let n = 0;
    stubFetch({ "GET /setup/pull": () => pullX("downloading", 600_000_000 + 1_000_000 * n++, 1_000_000_000) });
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} randomIndex={() => 0} />);
    await settle();
    expect(screen.getByText("0.6 of 1.0 GB")).toBeTruthy();
    expect(screen.queryByText(/min left|Less than a minute left/)).toBeNull();
    await settle(2000);
    expect(screen.queryByText(/min left|Less than a minute left/)).toBeNull();
    await settle(4000);
    expect(screen.getByText(/^About \d+ min left$/)).toBeTruthy();
  });

  it("does not show time left while resuming", async () => {
    let n = 0;
    stubFetch({ "GET /setup/pull": () => pullX("downloading", 600_000_000 + 1_000_000 * n++, 1_000_000_000, { resuming: true }) });
    render(<DownloadStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} randomIndex={() => 0} />);
    await settle(7000);
    expect(screen.queryByText(/min left|Less than a minute left/)).toBeNull();
  });
});

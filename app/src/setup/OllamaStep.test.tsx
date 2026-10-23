import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { resetEngineCache } from "../engine";
import { stubFetch } from "../test/mockEngine";
import { OllamaStep } from "./OllamaStep";

const POSITION = { n: 1, total: 5, label: "Test" };

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

const status = (over: Record<string, unknown>) => ({
  installed: true,
  running: false,
  version: null,
  app_path: null,
  ...over,
});

const outdatedStatus = (over: Record<string, unknown> = {}) =>
  status({ running: true, outdated: true, updatable: true, version: "0.30.0", ...over });

const settle = (ms = 0) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
const click = (name: string) =>
  act(async () => { screen.getByRole("button", { name }).click(); });
const calls = (mock: ReturnType<typeof stubFetch>, key: string) =>
  mock.mock.calls.filter(([url, init]) => `${init?.method ?? "GET"} ${new URL(url).pathname}` === key);

beforeEach(() => {
  vi.useFakeTimers();
  resetEngineCache();
  vi.mocked(invoke).mockResolvedValue({ port: 1, token: "t" });
  vi.unstubAllGlobals();
});
afterEach(() => vi.useRealTimers());

describe("OllamaStep", () => {
  it("auto-starts installed Ollama and continues when it runs", async () => {
    const fetchMock = stubFetch({
      "GET /setup/ollama": { body: status({}) },
      "POST /setup/ollama/start": { body: { running: true } },
    });
    const onDone = vi.fn();
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={onDone} />);
    await settle();
    expect(calls(fetchMock, "POST /setup/ollama/start")).toHaveLength(1);
    await settle();
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("shows Starting Ollama while it starts", async () => {
    const inner = stubFetch({
      "GET /setup/ollama": { body: status({}) },
      "POST /setup/ollama/start": { body: { running: true } },
    });
    // Hold the start request open so the in-between screen stays visible.
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") await gate;
      return inner(url, init);
    });
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle();
    expect(screen.getByText("Starting Ollama…")).toBeTruthy();
    release();
    await settle();
  });

  it("offers Check again when Ollama didn't start", async () => {
    let running = false;
    const fetchMock = stubFetch({
      "GET /setup/ollama": () => ({ body: status({ running }) }),
      "POST /setup/ollama/start": { body: { running: false } },
    });
    const onDone = vi.fn();
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={onDone} />);
    await settle();
    expect(
      screen.getByText(
        "Ollama didn't start. Try opening it from your Applications folder, then click Check again.",
      ),
    ).toBeTruthy();
    expect(onDone).not.toHaveBeenCalled();
    running = true;
    await click("Check again");
    await settle();
    expect(calls(fetchMock, "GET /setup/ollama")).toHaveLength(2);
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("explains Ollama and installs it, polling once a second", async () => {
    let poll = 0;
    const fetchMock = stubFetch({
      "GET /setup/ollama": { body: status({ installed: false }) },
      "POST /setup/ollama/install": { status: 202, body: { started: true } },
      "GET /setup/ollama/install": () => {
        poll += 1;
        return poll < 2
          ? { body: { state: "downloading", progress: 0.4, message: null } }
          : { body: { state: "done", progress: 1, message: null } };
      },
    });
    const onDone = vi.fn();
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={onDone} />);
    await settle();
    expect(screen.getByText(/the free app that runs AI models privately on your computer/)).toBeTruthy();
    await click("Install Ollama");
    await settle();
    expect(calls(fetchMock, "GET /setup/ollama/install")).toHaveLength(0);
    await settle(1000);
    expect(calls(fetchMock, "GET /setup/ollama/install")).toHaveLength(1);
    expect(screen.getByText(/40%/)).toBeTruthy();
    await settle(1000);
    expect(calls(fetchMock, "GET /setup/ollama/install")).toHaveLength(2);
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("shows an install error and retries", async () => {
    let fail = true;
    const fetchMock = stubFetch({
      "GET /setup/ollama": { body: status({ installed: false }) },
      "POST /setup/ollama/install": { status: 202, body: { started: true } },
      "GET /setup/ollama/install": () =>
        fail
          ? { body: { state: "error", progress: 0, message: "The download failed." } }
          : { body: { state: "downloading", progress: 0.1, message: null } },
    });
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle();
    await click("Install Ollama");
    await settle(1000);
    expect(screen.getByRole("alert").textContent).toBe("The download failed.");
    fail = false;
    await click("Retry");
    await settle(1000);
    expect(calls(fetchMock, "POST /setup/ollama/install")).toHaveLength(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("stops polling on unmount", async () => {
    const fetchMock = stubFetch({
      "GET /setup/ollama": { body: status({ installed: false }) },
      "POST /setup/ollama/install": { status: 202, body: { started: true } },
      "GET /setup/ollama/install": { body: { state: "downloading", progress: 0.1, message: null } },
    });
    const { unmount } = render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle();
    await click("Install Ollama");
    await settle(1000);
    unmount();
    await settle(3000);
    expect(calls(fetchMock, "GET /setup/ollama/install")).toHaveLength(1);
  });

  it("keeps only one install poll in flight and calls onDone once", async () => {
    const pending: Array<(r: Response) => void> = [];
    const ok = (body: object, status = 200) =>
      new Response(JSON.stringify(body), { status });
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${new URL(url).pathname}`;
      if (key === "GET /setup/ollama") return Promise.resolve(ok(status({ installed: false })));
      if (key === "POST /setup/ollama/install") return Promise.resolve(ok({ started: true }, 202));
      if (key === "GET /setup/ollama/install") return new Promise<Response>((r) => pending.push(r));
      throw new Error(`unexpected ${key}`);
    });
    const onDone = vi.fn();
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={onDone} />);
    await settle();
    await click("Install Ollama");
    await settle(5000);
    expect(pending).toHaveLength(1);
    await act(async () => { pending[0](ok({ state: "done", progress: 1, message: null })); });
    await settle(3000);
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("does not poll until the install request has returned", async () => {
    const polls: Array<(r: Response) => void> = [];
    let failInstall: (r: Response) => void = () => {};
    const ok = (body: object, st = 200) => new Response(JSON.stringify(body), { status: st });
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${new URL(url).pathname}`;
      if (key === "GET /setup/ollama") return Promise.resolve(ok(status({ installed: false })));
      if (key === "POST /setup/ollama/install")
        return new Promise<Response>((r) => (failInstall = r));
      if (key === "GET /setup/ollama/install") return new Promise<Response>((r) => polls.push(r));
      throw new Error(`unexpected ${key}`);
    });
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle();
    await click("Install Ollama");
    await settle(3000);
    expect(polls).toHaveLength(0);
    await act(async () => { failInstall(ok({ detail: "Install is unavailable." }, 400)); });
    expect(screen.getByRole("alert").textContent).toBe("Install is unavailable.");
    await settle(3000);
    expect(polls).toHaveLength(0);
  });

  it("does not show the previous attempt's error after Retry", async () => {
    let attempt = 0;
    let posted = 0;
    const fetchMock = stubFetch({
      "GET /setup/ollama": { body: outdatedStatus() },
      "POST /setup/ollama/update": () => {
        posted += 1;
        return { status: 202, body: { started: true } };
      },
      "GET /setup/ollama/install": () => {
        // Server state is stale ("error") until a new update has been posted.
        attempt = posted;
        return attempt < 2
          ? { body: { state: "error", progress: 0, message: "The update failed." } }
          : { body: { state: "downloading", progress: 0.2, message: null } };
      },
    });
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle();
    await click("Update Ollama");
    await settle(1000);
    expect(screen.getByRole("alert").textContent).toBe("The update failed.");
    await click("Retry");
    await settle(1000);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText(/20%/)).toBeTruthy();
    expect(calls(fetchMock, "POST /setup/ollama/update")).toHaveLength(2);
  });

  it("re-checks Ollama after an update and only then moves on", async () => {
    let outdated = true;
    const onDone = vi.fn();
    const fetchMock = stubFetch({
      "GET /setup/ollama": () => ({ body: outdatedStatus({ outdated }) }),
      "POST /setup/ollama/update": { status: 202, body: { started: true } },
      "GET /setup/ollama/install": () => {
        outdated = false;
        return { body: { state: "done", progress: 1, message: null } };
      },
    });
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={onDone} />);
    await settle();
    await click("Update Ollama");
    await settle(1000);
    await settle();
    expect(calls(fetchMock, "GET /setup/ollama")).toHaveLength(2);
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("stays blocked if Ollama is still outdated after the update finishes", async () => {
    const onDone = vi.fn();
    stubFetch({
      "GET /setup/ollama": { body: outdatedStatus() },
      "POST /setup/ollama/update": { status: 202, body: { started: true } },
      "GET /setup/ollama/install": { body: { state: "done", progress: 1, message: null } },
    });
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={onDone} />);
    await settle();
    await click("Update Ollama");
    await settle(1000);
    await settle();
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Ollama needs an update" })).toBeTruthy();
  });

  it("moves on from Check again once Ollama is up to date", async () => {
    let outdated = true;
    const onDone = vi.fn();
    stubFetch({ "GET /setup/ollama": () => ({ body: outdatedStatus({ updatable: false, outdated }) }) });
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={onDone} />);
    await settle();
    outdated = false;
    await click("Check again");
    await settle();
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("shows the engine's message when the update is refused, with Retry and API key", async () => {
    const fetchMock = stubFetch({
      "GET /setup/ollama": { body: outdatedStatus() },
      "POST /setup/ollama/update": {
        status: 400,
        body: { detail: "Folio can only update Ollama installed the standard way." },
      },
    });
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle();
    await click("Update Ollama");
    expect(screen.getByRole("alert").textContent).toBe(
      "Folio can only update Ollama installed the standard way.",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Use an API key instead" })).toBeTruthy();
    await click("Retry");
    expect(calls(fetchMock, "POST /setup/ollama/update")).toHaveLength(2);
  });

  it("offers an API key instead while Ollama is not installed or didn't start", async () => {
    stubFetch({ "GET /setup/ollama": { body: status({ installed: false }) } });
    const onUseApiKey = vi.fn();
    const { unmount } = render(<OllamaStep position={POSITION} onUseApiKey={onUseApiKey} onDone={() => {}} />);
    await settle();
    await click("Use an API key instead");
    expect(onUseApiKey).toHaveBeenCalledTimes(1);
    unmount();

    stubFetch({
      "GET /setup/ollama": { body: status({}) },
      "POST /setup/ollama/start": { body: { running: false } },
    });
    render(<OllamaStep position={POSITION} onUseApiKey={onUseApiKey} onDone={() => {}} />);
    await settle();
    await click("Use an API key instead");
    expect(onUseApiKey).toHaveBeenCalledTimes(2);
  });

  it("points Windows users to the Start menu when Ollama didn't start", async () => {
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/120.0",
    );
    stubFetch({
      "GET /setup/ollama": { body: status({}) },
      "POST /setup/ollama/start": { body: { running: false } },
    });
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle();
    expect(
      screen.getByText(
        "Ollama didn't start. Try opening it from the Start menu, then click Check again.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/Applications/)).toBeNull();
    vi.restoreAllMocks();
  });


  it("blocks an outdated standard install and offers an update", async () => {
    const onDone = vi.fn();
    stubFetch({ "GET /setup/ollama": { body: outdatedStatus() } });
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={onDone} />);
    await settle();
    expect(screen.getByRole("heading", { name: "Ollama needs an update" })).toBeTruthy();
    expect(document.body.textContent).toContain("0.30.0");
    expect(document.body.textContent).toContain("0.32.12");
    expect(screen.getByRole("button", { name: "Update Ollama" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Use an API key instead" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /continue/i })).toBeNull();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("runs the update through its stages and finishes", async () => {
    const states = [
      { state: "downloading", progress: 0.5, message: null },
      { state: "stopping", progress: 1, message: null },
      { state: "installing", progress: 1, message: null },
      { state: "starting", progress: 1, message: null },
      { state: "done", progress: 1, message: null },
    ];
    let i = 0;
    const fetchMock = stubFetch({
      "GET /setup/ollama": () => ({ body: outdatedStatus({ outdated: i < states.length }) }),
      "POST /setup/ollama/update": { status: 202, body: { started: true } },
      "GET /setup/ollama/install": () => ({ body: states[Math.min(i++, states.length - 1)] }),
    });
    const onDone = vi.fn();
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={onDone} />);
    await settle();
    await click("Update Ollama");
    expect(calls(fetchMock, "POST /setup/ollama/update")).toHaveLength(1);
    await settle(1000);
    expect(screen.getByText(/50%/)).toBeTruthy();
    await settle(1000);
    expect(screen.getByText("Closing Ollama…")).toBeTruthy();
    await settle(1000);
    expect(screen.getByText("Installing Ollama")).toBeTruthy();
    await settle(1000);
    expect(screen.getByText("Starting Ollama…")).toBeTruthy();
    expect(onDone).not.toHaveBeenCalled();
    await settle(1000);
    await settle();
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("shows an update failure with Retry that re-posts the update", async () => {
    const fetchMock = stubFetch({
      "GET /setup/ollama": { body: outdatedStatus() },
      "POST /setup/ollama/update": { status: 202, body: { started: true } },
      "GET /setup/ollama/install": {
        body: { state: "error", progress: 0, message: "The update failed." },
      },
    });
    const onUseApiKey = vi.fn();
    render(<OllamaStep position={POSITION} onUseApiKey={onUseApiKey} onDone={() => {}} />);
    await settle();
    await click("Update Ollama");
    await settle(1000);
    expect(screen.getByRole("alert").textContent).toBe("The update failed.");
    expect(screen.getByRole("button", { name: "Use an API key instead" })).toBeTruthy();
    await click("Retry");
    expect(calls(fetchMock, "POST /setup/ollama/update")).toHaveLength(2);
    expect(calls(fetchMock, "POST /setup/ollama/install")).toHaveLength(0);
  });

  it("gives instructions for an outdated install Folio can't update", async () => {
    const fetchMock = stubFetch({
      "GET /setup/ollama": { body: outdatedStatus({ updatable: false }) },
    });
    render(<OllamaStep position={POSITION} onUseApiKey={() => {}} onDone={() => {}} />);
    await settle();
    expect(
      screen.getByText(
        "Download the latest version from ollama.com/download and install it, then click Check again.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Update Ollama" })).toBeNull();
    expect(screen.getByRole("button", { name: "Use an API key instead" })).toBeTruthy();
    await click("Check again");
    expect(calls(fetchMock, "GET /setup/ollama")).toHaveLength(2);
  });
});

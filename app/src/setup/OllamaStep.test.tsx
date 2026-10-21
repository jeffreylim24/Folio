import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { resetEngineCache } from "../engine";
import { stubFetch } from "../test/mockEngine";
import { OllamaStep } from "./OllamaStep";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

const status = (over: Record<string, unknown>) => ({
  installed: true,
  running: false,
  version: null,
  app_path: null,
  ...over,
});

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
    render(<OllamaStep onDone={onDone} />);
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
    render(<OllamaStep onDone={() => {}} />);
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
    render(<OllamaStep onDone={onDone} />);
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
    render(<OllamaStep onDone={onDone} />);
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
    render(<OllamaStep onDone={() => {}} />);
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
    const { unmount } = render(<OllamaStep onDone={() => {}} />);
    await settle();
    await click("Install Ollama");
    await settle(1000);
    unmount();
    await settle(3000);
    expect(calls(fetchMock, "GET /setup/ollama/install")).toHaveLength(1);
  });
});

import { describe, expect, it } from "vitest";
import type { SetupState } from "../engine";
import { nextStep } from "./flow";

const running = { installed: true, running: true, version: "0.1", appPath: null };
const idle = { state: "idle", model: null, completedBytes: 0, totalBytes: 0, error: null } as const;

function make(over: Omit<Partial<SetupState>, "settings"> & { settings?: Partial<SetupState["settings"]> } = {}): SetupState {
  const { settings, ...rest } = over;
  return {
    settings: { provider: null, model: null, baseUrl: null, setupComplete: false, ...settings },
    hasApiKey: false,
    ollama: running,
    pull: idle,
    ...rest,
  };
}

describe("nextStep", () => {
  it("asks for a provider first", () => {
    expect(nextStep(make())).toBe("provider");
  });

  it("asks for an API key when the API provider has no key or model", () => {
    expect(nextStep(make({ settings: { provider: "anthropic" } }))).toBe("api-key");
    expect(nextStep(make({ settings: { provider: "anthropic", model: "m" } }))).toBe("api-key");
    expect(nextStep(make({ settings: { provider: "openai" }, hasApiKey: true }))).toBe("api-key");
  });

  it("is ready once an API provider has a key and model", () => {
    const s = make({ settings: { provider: "anthropic", model: "m" }, hasApiKey: true });
    expect(nextStep(s)).toBe("ready");
  });

  it("needs Ollama installed and running", () => {
    const s = { provider: "ollama" } as const;
    expect(nextStep(make({ settings: s, ollama: null }))).toBe("ollama");
    expect(nextStep(make({ settings: s, ollama: { ...running, installed: false, running: false } }))).toBe("ollama");
    expect(nextStep(make({ settings: s, ollama: { ...running, running: false } }))).toBe("ollama");
  });

  it("asks for a model once Ollama is running", () => {
    expect(nextStep(make({ settings: { provider: "ollama" } }))).toBe("model");
  });

  it("waits for the download until it is done", () => {
    const settings = { provider: "ollama", model: "qwen3:8b" } as const;
    expect(nextStep(make({ settings }))).toBe("download");
    expect(nextStep(make({ settings, pull: { ...idle, state: "downloading" } }))).toBe("download");
    expect(nextStep(make({ settings, pull: { ...idle, state: "error" } }))).toBe("download");
    expect(nextStep(make({ settings, pull: { ...idle, state: "done" } }))).toBe("ready");
  });

  it("goes home when setup is complete", () => {
    expect(nextStep(make({ settings: { setupComplete: true } }))).toBe("home");
  });

  it("only trusts setup_complete when it is exactly true", () => {
    const bad = (v: unknown) => make({ settings: { setupComplete: v as boolean } });
    expect(nextStep(bad("false"))).toBe("provider");
    expect(nextStep(bad(1))).toBe("provider");
    expect(nextStep(bad("yes"))).toBe("provider");
  });

  it("falls back to provider for an unknown provider value", () => {
    const s = make({ settings: { provider: "bogus" as never } });
    expect(nextStep(s)).toBe("provider");
  });
});

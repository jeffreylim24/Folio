import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { resetEngineCache } from "../engine";
import { rawState, stubFetch } from "../test/mockEngine";
import { SetupWizard } from "./SetupWizard";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

beforeEach(() => {
  resetEngineCache();
  vi.mocked(invoke).mockResolvedValue({ port: 1, token: "t" });
  vi.unstubAllGlobals();
});

const WARNING =
  "Using your own API key sends your resume and knowledge base to the provider you choose. Your data leaves your device and is handled under that provider's terms. Use at your own risk.";

function wizard() {
  return render(<SetupWizard onEngineProblem={() => {}} />);
}

describe("SetupWizard routing", () => {
  it("shows two provider options and withholds the form until the warning is acknowledged", async () => {
    stubFetch({ "GET /setup/state": { body: rawState() } });
    wizard();
    expect(await screen.findByText("Run privately on this computer (recommended)")).toBeTruthy();
    expect(screen.queryByLabelText("API key")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /Use my own API key/ }));
    expect(screen.getByText(WARNING)).toBeTruthy();
    const key = screen.getByLabelText("API key");
    expect(key.matches(":disabled")).toBe(true);

    await userEvent.click(screen.getByLabelText("I understand my data will leave this device"));
    expect(key.matches(":disabled")).toBe(false);
  });

  it("saves Run privately in the engine and goes to the Ollama step", async () => {
    const missing = { installed: false, running: false, version: null, app_path: null };
    let provider: string | null = null;
    const fetchMock = stubFetch({
      "GET /setup/state": () => ({
        body: rawState({
          ollama: missing,
          settings: { provider, model: null, base_url: null, setup_complete: false },
        }),
      }),
      "PUT /setup/provider": () => {
        provider = "ollama";
        return { body: { ok: true } };
      },
      "GET /setup/ollama": { body: missing },
    });
    wizard();
    await userEvent.click(await screen.findByRole("button", { name: /Run privately/ }));
    expect(await screen.findByRole("button", { name: "Install Ollama" })).toBeTruthy();
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(new URL(put![0]).pathname).toBe("/setup/provider");
    expect(JSON.parse(put![1]!.body as string)).toEqual({ provider: "ollama" });
  });

  it("goes to the model step when Ollama is running", async () => {
    let provider: string | null = null;
    stubFetch({
      "GET /setup/state": () => ({
        body: rawState({ settings: { provider, model: null, base_url: null, setup_complete: false } }),
      }),
      "PUT /setup/provider": () => {
        provider = "ollama";
        return { body: { ok: true } };
      },
      "GET /setup/hardware": { body: { device: { total_ram_gb: 8, usable_gb: 4, free_disk_gb: 100, chip_label: "Chip", chip_note: "" }, recommended: null, reason: "memory", message: "Not enough memory.", tiers: [], models: [] } },
    });
    wizard();
    await userEvent.click(await screen.findByRole("button", { name: /Run privately/ }));
    expect(await screen.findByText("Not enough memory.")).toBeTruthy();
  });

  it("reports an engine problem if Run privately can't be saved", async () => {
    stubFetch({
      "GET /setup/state": { body: rawState() },
      "PUT /setup/provider": { status: 500, body: { detail: "Disk is read-only." } },
    });
    const onEngineProblem = vi.fn();
    render(<SetupWizard onEngineProblem={onEngineProblem} />);
    await userEvent.click(await screen.findByRole("button", { name: /Run privately/ }));
    await waitFor(() => expect(onEngineProblem).toHaveBeenCalledWith("Disk is read-only."));
  });

  it("can leave a failing API setup for another model or another provider", async () => {
    const apiState = rawState({
      settings: { provider: "openai", model: "text-embedding-3-small", base_url: null, setup_complete: false },
      has_api_key: true,
    });
    stubFetch({
      "GET /setup/state": { body: apiState },
      "POST /setup/test": { status: 400, body: { kind: "other", message: "That model can't chat." } },
    });
    wizard();
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Choose a different model" }));
    expect(await screen.findByText(WARNING)).toBeTruthy();
    expect(screen.getByLabelText("API key")).toBeTruthy();
  });

  it("can change how Folio's AI runs after the test fails", async () => {
    stubFetch({
      "GET /setup/state": {
        body: rawState({
          settings: { provider: "ollama", model: "qwen3:8b", base_url: null, setup_complete: false },
          pull: { state: "done", model: "qwen3:8b", completed_bytes: 1, total_bytes: 1, error: null },
        }),
      },
      "POST /setup/test": { status: 400, body: { kind: "network", message: "Couldn't reach Ollama." } },
    });
    wizard();
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Change how Folio's AI runs" }));
    expect(await screen.findByText("How should Folio's AI run?")).toBeTruthy();
  });

  it("lets a local user pick a different model after the test fails", async () => {
    stubFetch({
      "GET /setup/state": {
        body: rawState({
          settings: { provider: "ollama", model: "qwen3:8b", base_url: null, setup_complete: false },
          pull: { state: "done", model: "qwen3:8b", completed_bytes: 1, total_bytes: 1, error: null },
        }),
      },
      "POST /setup/test": { status: 400, body: { kind: "network", message: "Couldn't reach Ollama." } },
    });
    wizard();
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Choose a different model" }));
    expect(await screen.findByRole("heading", { name: "Choose your AI model" })).toBeTruthy();
  });

  it("shows the update screen when Ollama starts but turns out to be too old", async () => {
    let reads = 0;
    stubFetch({
      "GET /setup/state": {
        body: rawState({
          settings: { provider: "ollama", model: null, base_url: null, setup_complete: false },
          ollama: { installed: true, running: false, version: null, app_path: "/x", outdated: false, updatable: true },
        }),
      },
      "GET /setup/ollama": () => ({
        body:
          reads++ === 0
            ? { installed: true, running: false, version: null, app_path: "/x", outdated: false, updatable: true }
            : { installed: true, running: true, version: "0.30.0", app_path: "/x", outdated: true, updatable: true },
      }),
      "POST /setup/ollama/start": { body: { running: true } },
    });
    wizard();
    expect(await screen.findByText("Ollama needs an update")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Update Ollama" })).toBeTruthy();
  });

  it("offers an API key instead during the download", async () => {
    stubFetch({
      "GET /setup/state": {
        body: rawState({ settings: { provider: "ollama", model: "qwen3:8b", base_url: null, setup_complete: false } }),
      },
      "GET /setup/pull": { body: { state: "downloading", model: "qwen3:8b", completed_bytes: 1, total_bytes: 4, error: null } },
    });
    wizard();
    await userEvent.click(await screen.findByRole("button", { name: "Use an API key instead" }));
    expect(await screen.findByText(WARNING)).toBeTruthy();
  });

  it("resumes at the download step", async () => {
    stubFetch({
      "GET /setup/state": {
        body: rawState({ settings: { provider: "ollama", model: "qwen3:8b", base_url: null, setup_complete: false } }),
      },
      "GET /setup/pull": { body: { state: "downloading", model: "qwen3:8b", completed_bytes: 1, total_bytes: 4, error: null } },
    });
    wizard();
    expect(await screen.findByText("25%")).toBeTruthy();
  });

  it("can switch to the API-key path without an engine call", async () => {
    const fetchMock = stubFetch({
      "GET /setup/state": { body: rawState({ settings: { provider: "ollama", model: null, base_url: null, setup_complete: false } }) },
      "GET /setup/hardware": { body: { device: { total_ram_gb: 8, usable_gb: 4, free_disk_gb: 100, chip_label: "Chip", chip_note: "" }, recommended: null, reason: "memory", message: "Not enough memory.", tiers: [], models: [] } },
    });
    wizard();
    await userEvent.click(await screen.findByRole("button", { name: "Use an API key instead" }));
    expect(await screen.findByText(WARNING)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("completes the API-key path, re-fetching state after each step", async () => {
    let calls = 0;
    const apiState = {
      settings: { provider: "anthropic", model: "claude-x", base_url: null, setup_complete: false },
      has_api_key: true,
    };
    stubFetch({
      "GET /setup/state": () => ({ body: ++calls === 1 ? rawState() : rawState(apiState) }),
      "POST /setup/api-provider": { body: { models: ["claude-x"] } },
      "PUT /setup/api-model": { body: { ok: true } },
      "POST /setup/test": { body: { reply: "ready" } },
    });
    wizard();
    await userEvent.click(await screen.findByRole("button", { name: /Use my own API key/ }));
    await userEvent.click(screen.getByLabelText("I understand my data will leave this device"));
    await userEvent.type(screen.getByLabelText("API key"), "sk-123");
    await userEvent.click(screen.getByRole("button", { name: "Check my key" }));
    await userEvent.selectOptions(await screen.findByLabelText("Model"), "claude-x");
    expect(await screen.findByText("You're all set")).toBeTruthy();
  });

  it("shows Home once setup is complete", async () => {
    stubFetch({
      "GET /setup/state": { body: rawState({ settings: { provider: "ollama", model: "m", base_url: null, setup_complete: true } }) },
    });
    wizard();
    await waitFor(() => expect(screen.getByText("Folio is ready")).toBeTruthy());
  });
});

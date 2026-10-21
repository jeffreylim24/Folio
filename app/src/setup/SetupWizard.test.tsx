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

  it("goes to the Ollama step when running privately is chosen", async () => {
    stubFetch({ "GET /setup/state": { body: rawState({ ollama: { installed: false, running: false, version: null, app_path: null } }) } });
    wizard();
    await userEvent.click(await screen.findByRole("button", { name: /Run privately/ }));
    expect(await screen.findByText("Step: ollama")).toBeTruthy();
  });

  it("goes to the model step when Ollama is running", async () => {
    stubFetch({ "GET /setup/state": { body: rawState() } });
    wizard();
    await userEvent.click(await screen.findByRole("button", { name: /Run privately/ }));
    expect(await screen.findByText("Step: model")).toBeTruthy();
  });

  it("resumes at the download step", async () => {
    stubFetch({
      "GET /setup/state": {
        body: rawState({ settings: { provider: "ollama", model: "qwen3:8b", base_url: null, setup_complete: false } }),
      },
    });
    wizard();
    expect(await screen.findByText("Step: download")).toBeTruthy();
  });

  it("can switch to the API-key path without an engine call", async () => {
    const fetchMock = stubFetch({ "GET /setup/state": { body: rawState({ settings: { provider: "ollama", model: null, base_url: null, setup_complete: false } }) } });
    wizard();
    await userEvent.click(await screen.findByRole("button", { name: "Use an API key instead" }));
    expect(await screen.findByText(WARNING)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
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

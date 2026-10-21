import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import App from "./App";
import { resetEngineCache } from "./engine";
import { rawState, stubFetch } from "./test/mockEngine";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
const invokeMock = vi.mocked(invoke);

beforeEach(() => {
  resetEngineCache();
  invokeMock.mockReset();
  vi.unstubAllGlobals();
});

describe("engine startup", () => {
  it("shows engine error with retry", async () => {
    invokeMock.mockImplementation(async (cmd) => {
      if (cmd === "engine_info") throw "port in use";
      return undefined;
    });
    render(<App />);
    expect(await screen.findByText(/Folio's engine didn't start/)).toBeTruthy();
    expect(screen.getByText("port in use")).toBeTruthy();

    // After a restart the engine comes up and the wizard appears.
    invokeMock.mockImplementation(async (cmd) =>
      cmd === "engine_info" ? { port: 1234, token: "t" } : undefined,
    );
    stubFetch({ "GET /setup/state": { body: rawState() } });
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(invokeMock).toHaveBeenCalledWith("restart_engine");
    expect(await screen.findByText("Run privately on this computer (recommended)")).toBeTruthy();
  });

  it("sends the bearer token to the engine", async () => {
    invokeMock.mockResolvedValue({ port: 4321, token: "secret" });
    const fetchMock = stubFetch({ "GET /setup/state": { body: rawState() } });
    render(<App />);
    await screen.findByText("Use my own API key");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:4321/setup/state");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer secret");
  });

  it("caches engine_info between calls", async () => {
    invokeMock.mockResolvedValue({ port: 4321, token: "secret" });
    stubFetch({ "GET /setup/state": { body: rawState() } });
    render(<App />);
    await screen.findByText("Use my own API key");
    await waitFor(() => expect(invokeMock).toHaveBeenCalledTimes(1));
  });
});

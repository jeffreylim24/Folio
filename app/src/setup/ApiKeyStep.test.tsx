import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { resetEngineCache } from "../engine";
import { stubFetch } from "../test/mockEngine";
import { ApiKeyStep } from "./ApiKeyStep";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

beforeEach(() => {
  resetEngineCache();
  vi.mocked(invoke).mockResolvedValue({ port: 1, token: "t" });
  vi.unstubAllGlobals();
});

describe("ApiKeyStep", () => {
  it("offers the four providers and shows a base URL only for OpenAI-compatible", async () => {
    render(<ApiKeyStep onDone={() => {}} />);
    const options = screen.getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Anthropic", "OpenAI", "Google Gemini", "Other OpenAI-compatible"]);
    expect(screen.queryByLabelText("Base URL")).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText("Provider"), "Other OpenAI-compatible");
    expect(screen.getByLabelText("Base URL")).toBeTruthy();
  });

  it("shows the engine's message when the key is rejected", async () => {
    stubFetch({
      "POST /setup/api-provider": {
        status: 400,
        body: { kind: "auth", message: "That API key wasn't accepted." },
      },
    });
    render(<ApiKeyStep onDone={() => {}} />);
    await userEvent.type(screen.getByLabelText("API key"), "bad");
    await userEvent.click(screen.getByRole("button", { name: "Check my key" }));
    expect((await screen.findByRole("alert")).textContent).toBe("That API key wasn't accepted.");
  });

  it("shows plain FastAPI detail errors too", async () => {
    stubFetch({
      "POST /setup/api-provider": { status: 400, body: { detail: "A base URL is required for this provider." } },
    });
    render(<ApiKeyStep onDone={() => {}} />);
    await userEvent.selectOptions(screen.getByLabelText("Provider"), "Other OpenAI-compatible");
    await userEvent.type(screen.getByLabelText("API key"), "k");
    await userEvent.click(screen.getByRole("button", { name: "Check my key" }));
    expect((await screen.findByRole("alert")).textContent).toBe("A base URL is required for this provider.");
  });

  it("lists models on success and saves the chosen one", async () => {
    const onDone = vi.fn();
    const fetchMock = stubFetch({
      "POST /setup/api-provider": { body: { models: ["m1", "m2"] } },
      "PUT /setup/api-model": { body: { ok: true } },
    });
    render(<ApiKeyStep onDone={onDone} />);
    await userEvent.type(screen.getByLabelText("API key"), "sk-1");
    await userEvent.click(screen.getByRole("button", { name: "Check my key" }));
    await userEvent.selectOptions(await screen.findByLabelText("Model"), "m2");

    const put = fetchMock.mock.calls.find(([u, i]) => u.endsWith("/setup/api-model") && i?.method === "PUT");
    expect(JSON.parse(put![1]!.body as string)).toEqual({ model: "m2" });
    expect(onDone).toHaveBeenCalled();
    const post = fetchMock.mock.calls.find(([u]) => u.endsWith("/setup/api-provider"));
    expect(JSON.parse(post![1]!.body as string)).toEqual({ provider: "anthropic", api_key: "sk-1", base_url: null });
  });

  it("stays disabled when asked to", () => {
    render(<ApiKeyStep disabled onDone={() => {}} />);
    expect(screen.getByLabelText("API key").matches(":disabled")).toBe(true);
  });
});

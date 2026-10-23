import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { resetEngineCache } from "../engine";
import { stubFetch } from "../test/mockEngine";
import { ReadyStep } from "./ReadyStep";

const POSITION = { n: 1, total: 5, label: "Test" };

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

beforeEach(() => {
  resetEngineCache();
  vi.mocked(invoke).mockResolvedValue({ port: 1, token: "t" });
  vi.unstubAllGlobals();
});

describe("ReadyStep", () => {
  it("tests the connection and confirms success", async () => {
    const fetchMock = stubFetch({ "POST /setup/test": { body: { reply: "ready" } } });
    const onDone = vi.fn();
    render(<ReadyStep position={POSITION} onChangeProvider={() => {}} onDone={onDone} />);
    expect(await screen.findByText("You're all set")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Open Folio" }));
    expect(onDone).toHaveBeenCalled();
  });

  it("offers a different model or a different setup after success too", async () => {
    stubFetch({ "POST /setup/test": { body: { reply: "ready" } } });
    const onChooseModel = vi.fn();
    const onChangeProvider = vi.fn();
    render(
      <ReadyStep position={POSITION} onDone={() => {}} onChooseModel={onChooseModel} onChangeProvider={onChangeProvider} />,
    );
    await screen.findByText("You're all set");
    await userEvent.click(screen.getByRole("button", { name: "Choose a different model" }));
    expect(onChooseModel).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Change how Folio's AI runs" }));
    expect(onChangeProvider).toHaveBeenCalledTimes(1);
  });

  it("shows the error and retries", async () => {
    let fail = true;
    stubFetch({
      "POST /setup/test": () =>
        fail
          ? { status: 400, body: { kind: "network", message: "Couldn't reach the provider." } }
          : { body: { reply: "ready" } },
    });
    render(<ReadyStep position={POSITION} onChangeProvider={() => {}} onDone={() => {}} />);
    expect((await screen.findByRole("alert")).textContent).toBe("Couldn't reach the provider.");
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("You're all set")).toBeTruthy();
  });

  it("offers a different model or a different setup after an error", async () => {
    stubFetch({
      "POST /setup/test": { status: 400, body: { kind: "other", message: "That model can't chat." } },
    });
    const onChooseModel = vi.fn();
    const onChangeProvider = vi.fn();
    render(
      <ReadyStep position={POSITION} onDone={() => {}} onChooseModel={onChooseModel} onChangeProvider={onChangeProvider} />,
    );
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Choose a different model" }));
    expect(onChooseModel).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Change how Folio's AI runs" }));
    expect(onChangeProvider).toHaveBeenCalledTimes(1);
  });

  it("hides Choose a different model when no handler is given", async () => {
    stubFetch({
      "POST /setup/test": { status: 400, body: { kind: "network", message: "Couldn't reach Ollama." } },
    });
    render(<ReadyStep position={POSITION} onDone={() => {}} onChangeProvider={() => {}} />);
    await screen.findByRole("alert");
    expect(screen.queryByRole("button", { name: "Choose a different model" })).toBeNull();
    expect(screen.getByRole("button", { name: "Change how Folio's AI runs" })).toBeTruthy();
  });
});

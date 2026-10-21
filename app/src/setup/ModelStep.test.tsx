import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { resetEngineCache } from "../engine";
import { stubFetch } from "../test/mockEngine";
import { ModelStep } from "./ModelStep";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

beforeEach(() => {
  resetEngineCache();
  vi.mocked(invoke).mockResolvedValue({ port: 1, token: "t" });
  vi.unstubAllGlobals();
});

const hardware = (rec: Record<string, unknown>) => ({
  body: {
    hardware: {},
    recommendation: {
      model: null,
      reason: "ok",
      message: "",
      est_minutes: null,
      free_disk_needed_gb: null,
      ...rec,
    },
  },
});

const okRec = (minutes: number) =>
  hardware({
    model: { name: "qwen3:14b", size_gb: 9.3, min_budget_gb: 12, label: "Qwen 3 (14B)" },
    message: "We recommend the Qwen 3 (14B) model (9.3 GB). Download takes about 12 minutes.",
    est_minutes: minutes,
  });

describe("ModelStep", () => {
  it("shows the recommendation and starts the download", async () => {
    const fetchMock = stubFetch({
      "GET /setup/hardware": okRec(12),
      "PUT /setup/model": { status: 202, body: { started: true } },
    });
    const onDone = vi.fn();
    render(<ModelStep onDone={onDone} onUseApiKey={() => {}} />);
    expect(await screen.findByText(/We recommend the Qwen 3 \(14B\) model/)).toBeTruthy();
    expect(screen.getByText("Qwen 3 (14B)")).toBeTruthy();
    expect(screen.getByText("9.3 GB, about 12 minutes")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Download" }));
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(put[1]!.body as string)).toEqual({ model: "qwen3:14b" });
    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("says about 1 minute in the singular", async () => {
    stubFetch({ "GET /setup/hardware": okRec(1) });
    render(<ModelStep onDone={() => {}} onUseApiKey={() => {}} />);
    expect(await screen.findByText("9.3 GB, about 1 minute")).toBeTruthy();
  });

  it("shows the engine's message when another download is running", async () => {
    stubFetch({
      "GET /setup/hardware": okRec(12),
      "PUT /setup/model": { status: 409, body: { detail: "Another model is already downloading." } },
    });
    const onDone = vi.fn();
    render(<ModelStep onDone={onDone} onUseApiKey={() => {}} />);
    await userEvent.click(await screen.findByRole("button", { name: "Download" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Another model is already downloading.");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("offers the API-key path when memory is too low", async () => {
    stubFetch({
      "GET /setup/hardware": hardware({
        reason: "memory",
        message: "This computer doesn't have enough memory.",
      }),
    });
    const onUseApiKey = vi.fn();
    render(<ModelStep onDone={() => {}} onUseApiKey={onUseApiKey} />);
    expect(await screen.findByText("This computer doesn't have enough memory.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Download" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Use an API key instead" }));
    expect(onUseApiKey).toHaveBeenCalled();
  });

  it("asks to free disk space and checks again", async () => {
    let calls = 0;
    stubFetch({
      "GET /setup/hardware": () =>
        ++calls === 1
          ? hardware({ reason: "disk", message: "Free up 4.5 GB and try again.", free_disk_needed_gb: 4.5 })
          : okRec(12),
    });
    render(<ModelStep onDone={() => {}} onUseApiKey={() => {}} />);
    expect(await screen.findByText(/Free up 4\.5 GB and try again\./)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Download" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(await screen.findByRole("button", { name: "Download" })).toBeTruthy();
  });
});

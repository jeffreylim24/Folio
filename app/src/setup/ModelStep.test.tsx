import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { resetEngineCache } from "../engine";
import { stubFetch } from "../test/mockEngine";
import { ModelStep } from "./ModelStep";
import type { Advice, ModelOption } from "./modelTypes";

const POSITION = { n: 1, total: 5, label: "Test" };

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

beforeEach(() => {
  resetEngineCache();
  vi.mocked(invoke).mockResolvedValue({ port: 1, token: "t" });
  vi.unstubAllGlobals();
});

const opt = (over: Partial<ModelOption>): ModelOption => ({
  tag: "x:1b",
  name: "x:1b",
  maker: "Maker",
  blurb: "A model.",
  tier: null,
  download_gb: 1,
  needed_gb: 2,
  recommended_gb: 4,
  est_minutes: 3,
  fit: "ok",
  note: "Fine.",
  disk_short_gb: null,
  ...over,
});

const SMALL = opt({
  tag: "qwen3.5:4b-q4_K_M", name: "qwen3.5:4b", maker: "Alibaba", tier: "small",
  download_gb: 3.3, needed_gb: 4.9, est_minutes: 6, note: "Fastest, but weaker.",
});
const BALANCED = opt({
  tag: "qwen3.5:9b-q4_K_M", name: "qwen3.5:9b", maker: "Alibaba", tier: "balanced",
  download_gb: 6.6, needed_gb: 8.2, est_minutes: 12, note: "It needs about 8 GB and you have 16 GB usable.",
});
const BEST = opt({
  tag: "qwen3.8:27b-q4_K_M", name: "qwen3.8:27b", maker: "Alibaba", tier: "best",
  download_gb: 18, needed_gb: 20.2, est_minutes: 31, fit: "no", note: "Needs more than you have.",
});
const GEMMA = opt({
  tag: "gemma4:12b-q4_K_M", name: "gemma4:12b", maker: "Google", blurb: "Google's mid-size model.",
  download_gb: 8, needed_gb: 9.8, recommended_gb: 14,
});
const MINISTRAL = opt({ tag: "ministral:14b", name: "ministral:14b", maker: "Mistral", fit: "tight", needed_gb: 12.8 });

const advice = (over: Partial<Advice> = {}): { body: Advice } => ({
  body: {
    device: {
      total_ram_gb: 24, usable_gb: 16.1, free_disk_gb: 212,
      chip_label: "Apple M5", chip_note: "Shares memory with the graphics chip",
    },
    recommended: BALANCED.tag,
    reason: "ok",
    message: "We recommend qwen3.5:9b for your device.",
    tiers: [SMALL, BALANCED, BEST],
    models: [SMALL, BALANCED, GEMMA, MINISTRAL, BEST],
    ...over,
  },
});

const setup = (a = advice(), onDone = vi.fn(), onUseApiKey = vi.fn()) => {
  const fetchMock = stubFetch({
    "GET /setup/hardware": a,
    "PUT /setup/model": { status: 202, body: { started: true } },
  });
  render(<ModelStep position={POSITION} onDone={onDone} onUseApiKey={onUseApiKey} />);
  return { fetchMock, onDone, onUseApiKey };
};

const puts = (m: ReturnType<typeof stubFetch>) => m.mock.calls.filter(([, init]) => init?.method === "PUT");

describe("ModelStep", () => {
  it("shows device strip and three cards with model names", async () => {
    setup();
    expect(await screen.findByText("24 GB")).toBeTruthy();
    expect(screen.getByText("≈16.1 GB usable for AI")).toBeTruthy();
    expect(screen.getByText("Apple M5")).toBeTruthy();
    expect(screen.getByText("Plenty for any option")).toBeTruthy();
    for (const n of ["qwen3.5:4b", "qwen3.5:9b", "qwen3.8:27b"]) expect(screen.getByText(n)).toBeTruthy();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
  });

  it("recommended card is selected with its reason", async () => {
    setup();
    const card = await screen.findByRole("radio", { checked: true });
    expect(card.textContent).toContain("Recommended for you");
    expect(card.textContent).toContain("Why: It needs about 8 GB and you have 16 GB usable.");
    expect(screen.getByRole("button", { name: "Download Balanced (qwen3.5:9b)" })).toBeTruthy();
  });

  it("too-big card says so and download says anyway", async () => {
    setup();
    const best = (await screen.findByText("qwen3.8:27b")).closest("[role=radio]") as HTMLElement;
    await userEvent.click(best);
    expect(within(best).getByText("Too big for your device")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Download Best quality anyway (qwen3.8:27b)" })).toBeTruthy();
  });

  it("picker lists models grouped by fit and shows an info card", async () => {
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /Let me pick my own model/ }));
    const list = screen.getByRole("listbox");
    for (const h of ["Runs well on your device", "Might be slow", "Too big for your device"]) {
      expect(within(list).getByText(h)).toBeTruthy();
    }
    await userEvent.click(within(list).getByRole("option", { name: /gemma4:12b/ }));
    expect(screen.queryByRole("radio", { checked: true })).toBeNull();
    for (const k of ["Download", "Minimum", "Recommended", "Your device"]) {
      expect(screen.getAllByText(k).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("9.8 GB")).toBeTruthy();
    expect(screen.getByText("14 GB")).toBeTruthy();
    expect(screen.getByText("16.1 GB")).toBeTruthy();
    expect(screen.getByText("Google's mid-size model.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Download gemma4:12b" })).toBeTruthy();
  });

  it("picker supports the keyboard", async () => {
    setup();
    const btn = await screen.findByRole("button", { name: /Let me pick my own model/ });
    btn.focus();
    await userEvent.keyboard("{ArrowDown}");
    const options = screen.getAllByRole("option");
    expect(document.activeElement).toBe(options[0]);
    await userEvent.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(options[1]);
    await userEvent.keyboard("{ArrowUp}{ArrowUp}");
    expect(document.activeElement).toBe(options[options.length - 1]);
    await userEvent.keyboard("{Escape}");
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    await userEvent.keyboard("{ArrowDown}");
    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: /Download qwen3.5:4b/ })).toBeTruthy();
  });

  it("download sends the selected tag", async () => {
    const { fetchMock, onDone } = setup();
    await userEvent.click(await screen.findByRole("button", { name: /^Download Balanced/ }));
    const put = puts(fetchMock);
    expect(put).toHaveLength(1);
    expect(JSON.parse(put[0][1]!.body as string)).toEqual({ model: "qwen3.5:9b-q4_K_M" });
    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("no recommendation", async () => {
    const { onUseApiKey } = setup(
      advice({ recommended: null, reason: "memory", message: "This computer is short on memory." }),
    );
    expect(await screen.findByText("This computer is short on memory.")).toBeTruthy();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(screen.queryByRole("radio", { checked: true })).toBeNull();
    expect((screen.getByRole("button", { name: /^Download/ }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Use an API key instead" }));
    expect(onUseApiKey).toHaveBeenCalled();
  });

  it("too-big choice asks for confirmation", async () => {
    const { fetchMock } = setup();
    const best = (await screen.findByText("qwen3.8:27b")).closest("[role=radio]") as HTMLElement;
    await userEvent.click(best);
    await userEvent.click(screen.getByRole("button", { name: /^Download Best quality anyway/ }));
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByRole("heading", { name: "Your device may struggle with this model" })).toBeTruthy();
    expect(dialog.textContent).toContain(
      "Your computer's specs are below what this model needs. Running it may make your computer very slow, freeze other apps, or crash Folio. Continue at your own risk, or use your own API key instead.",
    );
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(puts(fetchMock)).toHaveLength(0);

    await userEvent.click(within(dialog).getByRole("button", { name: "Go back" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(puts(fetchMock)).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: /^Download Best quality anyway/ }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /^Download Best quality anyway/ }));
    await userEvent.click(screen.getByRole("button", { name: "Download anyway" }));
    expect(puts(fetchMock)).toHaveLength(1);
    expect(JSON.parse(puts(fetchMock)[0][1]!.body as string)).toEqual({ model: "qwen3.8:27b-q4_K_M" });
  });

  it("dialog offers the API key path", async () => {
    const { onUseApiKey } = setup();
    await userEvent.click((await screen.findByText("qwen3.8:27b")).closest("[role=radio]") as HTMLElement);
    await userEvent.click(screen.getByRole("button", { name: /^Download Best quality anyway/ }));
    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Use an API key instead" }));
    expect(onUseApiKey).toHaveBeenCalled();
  });

  it("no recommendation also asks for confirmation", async () => {
    const small = { ...SMALL, fit: "tight" as const };
    const { fetchMock } = setup(
      advice({ recommended: null, reason: "memory", message: "Short on memory.", tiers: [small, BALANCED, BEST] }),
    );
    await userEvent.click((await screen.findByText("qwen3.5:4b")).closest("[role=radio]") as HTMLElement);
    await userEvent.click(screen.getByRole("button", { name: /^Download Small/ }));
    expect(screen.getByRole("alertdialog")).toBeTruthy();
    expect(puts(fetchMock)).toHaveLength(0);
  });

  it("recommended choice downloads without a dialog", async () => {
    const { fetchMock } = setup();
    await userEvent.click(await screen.findByRole("button", { name: /^Download Balanced/ }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(puts(fetchMock)).toHaveLength(1);
  });

  it("disk short disables download", async () => {
    const short = { ...BEST, fit: "ok" as const, disk_short_gb: 1.5 };
    setup(advice({ tiers: [SMALL, BALANCED, short], models: [SMALL, BALANCED, short] }));
    expect(await screen.findByText("Not enough for every option")).toBeTruthy();
    await userEvent.click((await screen.findByText("qwen3.8:27b")).closest("[role=radio]") as HTMLElement);
    expect((screen.getByRole("button", { name: /^Download Best/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Free up 1.5 GB of disk space to download this one.")).toBeTruthy();
    await userEvent.click(screen.getByText("qwen3.5:4b").closest("[role=radio]") as HTMLElement);
    expect((screen.getByRole("button", { name: /^Download Small/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("disk short offers Check again, which keeps the choice once space is free", async () => {
    const short = { ...BEST, fit: "ok" as const, disk_short_gb: 1.5 };
    const freed = { ...BEST, fit: "ok" as const };
    let calls = 0;
    stubFetch({
      "GET /setup/hardware": () =>
        ++calls === 1
          ? advice({ tiers: [SMALL, BALANCED, short], models: [SMALL, BALANCED, short] })
          : advice({ tiers: [SMALL, BALANCED, freed], models: [SMALL, BALANCED, freed] }),
    });
    render(<ModelStep position={POSITION} onDone={() => {}} onUseApiKey={() => {}} />);
    await userEvent.click((await screen.findByText("qwen3.8:27b")).closest("[role=radio]") as HTMLElement);
    expect((screen.getByRole("button", { name: /^Download Best/ }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Check again" }));
    const btn = (await screen.findByRole("button", { name: /^Download Best/ })) as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    expect(screen.queryByText(/Free up/)).toBeNull();
  });

  it("reason disk explains how much to free and can check again", async () => {
    const short = { ...BALANCED, disk_short_gb: 2.5 };
    setup(
      advice({
        reason: "disk",
        message: "Free up 2.5 GB to download qwen3.5:9b.",
        tiers: [SMALL, short, BEST],
        models: [SMALL, short, BEST],
      }),
    );
    expect(await screen.findByText("Free up 2.5 GB to download qwen3.5:9b.")).toBeTruthy();
    expect(screen.getByText(/Free up 2.5 GB of disk space/)).toBeTruthy();
    expect((screen.getByRole("button", { name: /^Download Balanced/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("button", { name: "Check again" })).toBeTruthy();
  });

  it("only the recommended model gets the Recommended badge, in cards and info card", async () => {
    setup();
    const small = (await screen.findByText("qwen3.5:4b")).closest("[role=radio]") as HTMLElement;
    expect(within(small).getByText("Fits easily").className).toContain("easy");
    expect(screen.getAllByText("Recommended for you")).toHaveLength(1);
    expect(screen.queryByText(/change this later in Settings/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Let me pick my own model/ }));
    await userEvent.click(screen.getByRole("option", { name: /gemma4:12b/ }));
    const badge = within(document.querySelector(".info") as HTMLElement).getByText("Fits easily");
    expect(badge.className).toContain("easy");
    await userEvent.click(document.querySelector(".combo-btn") as HTMLElement);
    await userEvent.click(screen.getByRole("option", { name: /qwen3.5:9b/ }));
    const info = document.querySelector(".info") as HTMLElement;
    expect(within(info).getByText("Recommended for you").className).toContain("rec");
  });

  it("shows the engine's message when the download is refused", async () => {
    stubFetch({
      "GET /setup/hardware": advice(),
      "PUT /setup/model": { status: 409, body: { detail: "Another model is already downloading." } },
    });
    const onDone = vi.fn();
    render(<ModelStep position={POSITION} onDone={onDone} onUseApiKey={() => {}} />);
    await userEvent.click(await screen.findByRole("button", { name: /^Download Balanced/ }));
    expect((await screen.findByRole("alert")).textContent).toBe("Another model is already downloading.");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("shows an error and retries when the check fails", async () => {
    let calls = 0;
    stubFetch({
      "GET /setup/hardware": () =>
        ++calls === 1 ? { status: 500, body: { detail: "Could not check your computer." } } : advice(),
    });
    render(<ModelStep position={POSITION} onDone={() => {}} onUseApiKey={() => {}} />);
    expect((await screen.findByRole("alert")).textContent).toBe("Could not check your computer.");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("qwen3.5:9b")).toBeTruthy();
  });
});

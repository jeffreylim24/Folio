import type { SetupState } from "../engine";

export type Step =
  | "provider"
  | "api-key"
  | "ollama"
  | "model"
  | "download"
  | "ready"
  | "home";

export const API_PROVIDERS: string[] = ["anthropic", "openai", "gemini", "openai_compatible"];

// Settings come from a file on disk and are not type-checked by the engine,
// so every field is checked defensively here.
export function nextStep(s: SetupState): Step {
  if (s.settings.setupComplete === true) return "home";
  const { provider, model } = s.settings;
  const hasModel = typeof model === "string" && model !== "";

  if (provider === "ollama") {
    if (!s.ollama || !s.ollama.installed || !s.ollama.running || s.ollama.outdated === true) {
      return "ollama";
    }
    if (!hasModel) return "model";
    if (s.pull.state !== "done") return "download";
    return "ready";
  }
  if (typeof provider === "string" && API_PROVIDERS.includes(provider)) {
    return s.hasApiKey === true && hasModel ? "ready" : "api-key";
  }
  return "provider";
}

export type StepPosition = { n: number; total: number; label: string };

const LOCAL_STEPS: Partial<Record<Step, StepPosition>> = {
  provider: { n: 1, total: 5, label: "How Folio's AI runs" },
  "api-key": { n: 1, total: 5, label: "How Folio's AI runs" },
  ollama: { n: 2, total: 5, label: "Set up Ollama" },
  model: { n: 3, total: 5, label: "Choose a model" },
  download: { n: 4, total: 5, label: "Download" },
  ready: { n: 5, total: 5, label: "Finish" },
};

export function stepPosition(step: Step, apiPath: boolean): StepPosition {
  if (apiPath) {
    return step === "ready"
      ? { n: 2, total: 2, label: "Finish" }
      : { n: 1, total: 2, label: "How Folio's AI runs" };
  }
  return LOCAL_STEPS[step] ?? { n: 1, total: 5, label: "How Folio's AI runs" };
}

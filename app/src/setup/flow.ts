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

// The first screen has no total: until a path is chosen we don't know how
// many steps follow. The Ollama step only counts when it was needed.
export type StepPosition = { n: number; total?: number; label: string };

const CHOOSE: StepPosition = { n: 1, label: "How Folio's AI runs" };
const LOCAL_LABELS: [Step, string][] = [
  ["ollama", "Set up Ollama"],
  ["model", "Choose a model"],
  ["download", "Download"],
  ["ready", "Finish"],
];

export function stepPosition(step: Step, apiPath: boolean, withOllama: boolean): StepPosition {
  if (step === "provider" || step === "api-key") return CHOOSE;
  if (apiPath) return step === "ready" ? { n: 2, total: 2, label: "Finish" } : CHOOSE;
  const steps = LOCAL_LABELS.filter(([s]) => s !== "ollama" || withOllama || step === "ollama");
  const i = steps.findIndex(([s]) => s === step);
  if (i === -1) return CHOOSE;
  return { n: i + 2, total: steps.length + 1, label: steps[i][1] };
}

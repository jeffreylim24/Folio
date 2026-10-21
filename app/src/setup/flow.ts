import type { SetupState } from "../engine";

export type Step =
  | "provider"
  | "api-key"
  | "ollama"
  | "model"
  | "download"
  | "ready"
  | "home";

const API_PROVIDERS = ["anthropic", "openai", "gemini", "openai_compatible"];

// Settings come from a file on disk and are not type-checked by the engine,
// so every field is checked defensively here.
export function nextStep(s: SetupState): Step {
  if (s.settings.setupComplete === true) return "home";
  const { provider, model } = s.settings;
  const hasModel = typeof model === "string" && model !== "";

  if (provider === "ollama") {
    if (!s.ollama || !s.ollama.installed || !s.ollama.running) return "ollama";
    if (!hasModel) return "model";
    if (s.pull.state !== "done") return "download";
    return "ready";
  }
  if (typeof provider === "string" && API_PROVIDERS.includes(provider)) {
    return s.hasApiKey === true && hasModel ? "ready" : "api-key";
  }
  return "provider";
}

import { useCallback, useEffect, useState } from "react";
import { api, getSetupState, type SetupState } from "../engine";
import { Home } from "../Home";
import { API_PROVIDERS, nextStep, stepPosition, type Step } from "./flow";
import { DownloadStep } from "./DownloadStep";
import { ModelStep } from "./ModelStep";
import { OllamaStep } from "./OllamaStep";
import { ProviderChoice } from "./ProviderChoice";
import { ReadyStep } from "./ReadyStep";

export function SetupWizard({ onEngineProblem }: { onEngineProblem: (message: string) => void }) {
  const [state, setState] = useState<SetupState | null>(null);
  // A screen the user asked for that the saved state would not pick
  // (e.g. "Use an API key instead"); cleared whenever state is re-fetched.
  const [override, setOverride] = useState<Step | null>(null);

  const refresh = useCallback(async () => {
    try {
      setState(await getSetupState());
      setOverride(null);
    } catch (e) {
      onEngineProblem(e instanceof Error ? e.message : "Unknown error");
    }
  }, [onEngineProblem]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!state) {
    return (
      <main className="page" aria-busy="true">
        <div className="card centered screen" role="status">
          <div className="spinner" aria-hidden="true" />
          <p>Loading...</p>
        </div>
      </main>
    );
  }

  const step = override ?? nextStep(state);
  // Saved right away so a relaunch (e.g. after installing Ollama) resumes here.
  const chooseLocal = async () => {
    try {
      await api("/setup/provider", {
        method: "PUT",
        body: JSON.stringify({ provider: "ollama" }),
      });
    } catch (e) {
      onEngineProblem(e instanceof Error ? e.message : "Unknown error");
      return;
    }
    await refresh();
  };
  const apiDone = () => void refresh();
  const useApiKey = () => setOverride("api-key");
  const changeProvider = () => setOverride("provider");
  const usesApiKey =
    typeof state.settings.provider === "string" &&
    API_PROVIDERS.includes(state.settings.provider);

  const apiPath = step === "api-key" || usesApiKey;
  const position = stepPosition(step, apiPath);

  return (
    <main className="page">
      <div key={step} className="screen">
        {step === "provider" && (
          <ProviderChoice
            position={position}
            onChooseLocal={() => void chooseLocal()}
            onDone={apiDone}
          />
        )}
        {step === "api-key" && (
          <ProviderChoice
            position={position}
            initial="api"
            onChooseLocal={() => void chooseLocal()}
            onDone={apiDone}
          />
        )}
        {step === "ollama" && (
          <OllamaStep position={position} onDone={refresh} onUseApiKey={useApiKey} />
        )}
        {step === "model" && (
          <ModelStep position={position} onDone={refresh} onUseApiKey={useApiKey} />
        )}
        {step === "download" && (
          <DownloadStep position={position} onDone={refresh} onUseApiKey={useApiKey} />
        )}
        {step === "ready" && (
          <ReadyStep
            position={position}
            onDone={refresh}
            onChooseModel={usesApiKey ? useApiKey : undefined}
            onChangeProvider={changeProvider}
          />
        )}
        {step === "home" && <Home />}
      </div>
    </main>
  );
}

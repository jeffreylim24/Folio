import { useCallback, useEffect, useState } from "react";
import { getSetupState, type SetupState } from "../engine";
import { Home } from "../Home";
import { nextStep, type Step } from "./flow";
import { ProviderChoice } from "./ProviderChoice";
import { ReadyStep } from "./ReadyStep";
import { StepPlaceholder } from "./StepPlaceholder";

export function SetupWizard({ onEngineProblem }: { onEngineProblem: (message: string) => void }) {
  const [state, setState] = useState<SetupState | null>(null);
  // Choices made on screen that the engine does not know about yet.
  const [localChosen, setLocalChosen] = useState(false);
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
        <p>Loading...</p>
      </main>
    );
  }

  // "Run privately" is only saved in the engine once a model is chosen, so
  // until then the wizard treats it as chosen locally.
  const effective: SetupState =
    localChosen && state.settings.provider !== "ollama"
      ? { ...state, settings: { ...state.settings, provider: "ollama", model: null } }
      : state;
  const step = override ?? nextStep(effective);
  const chooseLocal = () => {
    setOverride(null);
    setLocalChosen(true);
  };
  const apiDone = () => {
    setLocalChosen(false);
    void refresh();
  };
  // Task 10's setup screens call this for "use an API key instead".
  const useApiKey = () => setOverride("api-key");

  return (
    <main className="page">
      {step === "provider" && (
        <ProviderChoice onChooseLocal={chooseLocal} onDone={apiDone} />
      )}
      {step === "api-key" && (
        <ProviderChoice initial="api" onChooseLocal={chooseLocal} onDone={apiDone} />
      )}
      {(step === "ollama" || step === "model" || step === "download") && (
        <StepPlaceholder step={step} onUseApiKey={useApiKey} />
      )}
      {step === "ready" && <ReadyStep onDone={refresh} />}
      {step === "home" && <Home />}
    </main>
  );
}

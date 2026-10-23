import { useState } from "react";
import { StepShell } from "../ui/StepShell";
import { ApiKeyStep } from "./ApiKeyStep";
import type { StepPosition } from "./flow";

type Props = {
  position: StepPosition;
  initial?: "api";
  onChooseLocal: () => void;
  onDone: () => void;
};

export const API_WARNING =
  "Using your own API key sends your resume and knowledge base to the provider you choose. Your data leaves your device and is handled under that provider's terms. Use at your own risk.";

export function ProviderChoice({ position, initial, onChooseLocal, onDone }: Props) {
  const [showApi, setShowApi] = useState(initial === "api");
  const [understood, setUnderstood] = useState(false);

  return (
    <StepShell
      step={position}
      title="How should Folio's AI run?"
      lede="You can only pick one for now. Both work the same once set up."
    >
      <div className="choices">
        <button type="button" className="choice" onClick={onChooseLocal}>
          <strong>Run privately on this computer (recommended)</strong>
          <span>Your resume never leaves your device. Needs a one-time download.</span>
        </button>
        <button
          type="button"
          className="choice"
          aria-pressed={showApi}
          onClick={() => setShowApi(true)}
        >
          <strong>Use my own API key</strong>
          <span>Connect an account you already have with an AI provider.</span>
        </button>
      </div>
      {showApi && (
        <div className="stack">
          <p className="warning">{API_WARNING}</p>
          <label className="check">
            <input
              type="checkbox"
              checked={understood}
              onChange={(e) => setUnderstood(e.target.checked)}
            />
            <span>I understand my data will leave this device</span>
          </label>
          <ApiKeyStep disabled={!understood} onDone={onDone} />
        </div>
      )}
    </StepShell>
  );
}

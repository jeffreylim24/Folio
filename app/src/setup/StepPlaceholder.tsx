// Temporary stand-in; Task 10 replaces it with OllamaStep, ModelStep and DownloadStep.
type Props = {
  step: "ollama" | "model" | "download";
  onUseApiKey: () => void;
};

export function StepPlaceholder({ step, onUseApiKey }: Props) {
  return (
    <section className="stack">
      <h1>Step: {step}</h1>
      <button type="button" onClick={onUseApiKey}>
        Use an API key instead
      </button>
    </section>
  );
}

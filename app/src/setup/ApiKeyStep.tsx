import { useState, type FormEvent } from "react";
import { api, EngineError, jsonBody, type ProviderName } from "../engine";

const PROVIDERS: { value: ProviderName; label: string }[] = [
  { value: "anthropic", label: "Anthropic" },
  { value: "openai", label: "OpenAI" },
  { value: "gemini", label: "Google Gemini" },
  { value: "openai_compatible", label: "Other OpenAI-compatible" },
];

type Props = { disabled?: boolean; onDone: () => void };

function messageOf(e: unknown): string {
  return e instanceof EngineError || e instanceof Error
    ? e.message
    : "Something went wrong. Please try again.";
}

export function ApiKeyStep({ disabled = false, onDone }: Props) {
  const [provider, setProvider] = useState<ProviderName>("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [models, setModels] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connect(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ models: string[] }>(
        "/setup/api-provider",
        jsonBody({
          provider,
          api_key: apiKey,
          base_url: provider === "openai_compatible" ? baseUrl : null,
        }),
        30_000,
      );
      setModels(res.models);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  async function chooseModel(model: string) {
    if (!model) return;
    setBusy(true);
    setError(null);
    try {
      await api("/setup/api-model", {
        method: "PUT",
        body: JSON.stringify({ model }),
      });
      onDone();
    } catch (err) {
      setError(messageOf(err));
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={connect}>
      <fieldset className="stack" disabled={disabled || busy}>
        <label className="field">
          <span>Provider</span>
          <select
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value as ProviderName);
              setModels(null);
            }}
          >
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        {provider === "openai_compatible" && (
          <label className="field">
            <span>Base URL</span>
            <input
              type="url"
              value={baseUrl}
              placeholder="https://example.com/v1"
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </label>
        )}
        <label className="field">
          <span>API key</span>
          <input
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </label>
        <button type="submit" className="primary" disabled={!apiKey.trim()}>
          {busy && !models ? "Checking..." : "Check my key"}
        </button>
        {models && (
          <label className="field">
            <span>Model</span>
            <select
              defaultValue=""
              onChange={(e) => void chooseModel(e.target.value)}
            >
              <option value="" disabled>
                Choose a model
              </option>
              {models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
        )}
      </fieldset>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}

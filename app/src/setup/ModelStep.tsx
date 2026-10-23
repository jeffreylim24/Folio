import { useCallback, useEffect, useState } from "react";
import type { KeyboardEvent } from "react";
import { api } from "../engine";
import { Badge } from "../ui/Badge";
import { FitBar } from "../ui/FitBar";
import { StepShell } from "../ui/StepShell";
import type { StepPosition } from "./flow";
import { LowSpecDialog } from "./LowSpecDialog";
import { ModelPicker } from "./ModelPicker";
import { badgeFor, TIER_NAMES } from "./modelTypes";
import type { Advice, ModelOption } from "./modelTypes";

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong. Please try again.";
}

type Choice = { tag: string; via: "card" | "picker" };
type Props = { position: StepPosition; onDone: () => void; onUseApiKey: () => void };

export function ModelStep({ position, onDone, onUseApiKey }: Props) {
  const [advice, setAdvice] = useState<Advice | null>(null);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const load = useCallback(async (keep?: Choice | null) => {
    setAdvice(null);
    setError(null);
    try {
      const a = await api<Advice>("/setup/hardware");
      setAdvice(a);
      const onCard = a.tiers.some((t) => t.tag === a.recommended);
      const kept = keep && [...a.tiers, ...a.models].some((m) => m.tag === keep.tag) ? keep : null;
      setChoice(kept ?? (a.recommended ? { tag: a.recommended, via: onCard ? "card" : "picker" } : null));
    } catch (e) {
      setError(messageOf(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const download = async (tag: string) => {
    setConfirming(false);
    setBusy(true);
    setError(null);
    try {
      await api("/setup/model", { method: "PUT", body: JSON.stringify({ model: tag }) });
      onDone();
    } catch (e) {
      setError(messageOf(e));
      setBusy(false);
    }
  };

  if (!advice) {
    return (
      <StepShell step={position} title="Choose your AI model" live="polite">
        {error ? (
          <>
            <p role="alert" className="error">
              {error}
            </p>
            <button type="button" className="primary" onClick={() => void load()}>
              Retry
            </button>
          </>
        ) : (
          <p>Checking your computer…</p>
        )}
      </StepShell>
    );
  }

  const { device, tiers, models } = advice;
  const find = (tag: string): ModelOption | undefined =>
    models.find((m) => m.tag === tag) ?? tiers.find((m) => m.tag === tag);
  const picked = choice ? find(choice.tag) : undefined;
  const diskShort = models.some((m) => m.disk_short_gb !== null) || tiers.some((m) => m.disk_short_gb !== null);

  let label = "Download";
  if (picked && choice) {
    const anyway = picked.fit === "no" ? " anyway" : "";
    label =
      choice.via === "card" && picked.tier
        ? `Download ${TIER_NAMES[picked.tier]}${anyway} (${picked.name})`
        : `Download ${picked.name}${anyway}`;
  }
  const blocked = picked?.disk_short_gb != null ? picked.disk_short_gb : null;

  const onCta = () => {
    if (!picked) return;
    if (picked.fit === "no" || advice.reason === "memory") setConfirming(true);
    else void download(picked.tag);
  };

  const onCardKey = (e: KeyboardEvent, i: number) => {
    const step = e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : e.key === "ArrowUp" || e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = tiers[(i + step + tiers.length) % tiers.length];
    setChoice({ tag: next.tag, via: "card" });
    const radios = e.currentTarget.parentElement?.querySelectorAll<HTMLElement>('[role="radio"]');
    radios?.[(i + step + tiers.length) % tiers.length]?.focus();
  };

  const checkedIdx = tiers.findIndex((t) => choice?.via === "card" && t.tag === choice.tag);

  return (
    <StepShell
      step={position}
      title="Pick the AI model Folio runs on your computer"
      lede={advice.message}
    >
      <div className="specs">
        <div className="spec">
          <div className="k">Memory</div>
          <div className="v">{device.total_ram_gb} GB</div>
          <div className="s">≈{device.usable_gb} GB usable for AI</div>
        </div>
        <div className="spec">
          <div className="k">Chip</div>
          <div className="v">{device.chip_label}</div>
          <div className="s">{device.chip_note}</div>
        </div>
        <div className="spec">
          <div className="k">Free disk</div>
          <div className="v">{device.free_disk_gb} GB</div>
          <div className="s">{diskShort ? "Not enough for every option" : "Plenty for any option"}</div>
        </div>
      </div>

      <div className="tiers" role="radiogroup" aria-label="Model size">
        {tiers.map((t, i) => {
          const checked = i === checkedIdx;
          const recommended = t.tag === advice.recommended;
          return (
            <button
              type="button"
              key={t.tag}
              role="radio"
              aria-checked={checked}
              tabIndex={checked || (checkedIdx === -1 && i === 0) ? 0 : -1}
              className={`tier${t.fit === "no" ? " toobig" : ""}`}
              onClick={() => setChoice({ tag: t.tag, via: "card" })}
              onKeyDown={(e) => onCardKey(e, i)}
            >
              <div className="row">
                <span className="tname">{t.tier ? TIER_NAMES[t.tier] : t.name}</span>
                <span className="tag">{t.name}</span>
                <Badge kind={badgeFor(t.fit, recommended).kind}>{badgeFor(t.fit, recommended).label}</Badge>
              </div>
              <div className="meta">
                {t.download_gb} GB download · about {t.est_minutes} min · needs ~{t.needed_gb} GB memory
              </div>
              <div className="why">{recommended ? <><b>Why:</b> {t.note}</> : t.note}</div>
              <FitBar neededGb={t.needed_gb} usableGb={device.usable_gb} fit={t.fit} />
            </button>
          );
        })}
      </div>

      <ModelPicker
        models={models}
        selected={choice?.via === "picker" ? choice.tag : null}
        usableGb={device.usable_gb}
        recommendedTag={advice.recommended}
        onSelect={(tag) => setChoice({ tag, via: "picker" })}
      />

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {blocked !== null && (
        <p className="warning">
          Free up {blocked} GB of disk space to download this one.{" "}
          <button type="button" className="linklike" onClick={() => void load(choice)}>
            Check again
          </button>
        </p>
      )}
      <button type="button" className="cta" disabled={!picked || busy || blocked !== null} onClick={onCta}>
        {label}
      </button>
      <p className="sub">
        Prefer not to run AI on your computer?{" "}
        <button type="button" className="linklike" onClick={onUseApiKey}>
          Use an API key instead
        </button>
      </p>

      {confirming && picked && (
        <LowSpecDialog
          onConfirm={() => void download(picked.tag)}
          onCancel={() => setConfirming(false)}
          onUseApiKey={onUseApiKey}
        />
      )}
    </StepShell>
  );
}

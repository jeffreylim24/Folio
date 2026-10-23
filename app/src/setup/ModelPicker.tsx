import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Badge } from "../ui/Badge";
import { FitBar } from "../ui/FitBar";
import { badgeFor } from "./modelTypes";
import type { Fit, ModelOption } from "./modelTypes";

const GROUPS: { fit: Fit; title: string }[] = [
  { fit: "ok", title: "Runs well on your device" },
  { fit: "tight", title: "Might be slow" },
  { fit: "no", title: "Too big for your device" },
];

type Props = {
  models: ModelOption[];
  /** Tag of the model picked here, or null when the choice (if any) is a card. */
  selected: string | null;
  usableGb: number;
  recommendedTag: string | null;
  onSelect: (tag: string) => void;
};

export function ModelPicker({ models, selected, usableGb, recommendedTag, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const idBase = useId();
  const current = models.find((m) => m.tag === selected) ?? null;
  const badge = current ? badgeFor(current.fit, current.tag === recommendedTag) : null;

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const wantFocus = useRef(false);

  // Once the options exist, focus the chosen (or first) one.
  useEffect(() => {
    if (!open || !wantFocus.current) return;
    wantFocus.current = false;
    const opts = options();
    (opts.find((o) => o.dataset.tag === selected) ?? opts[0])?.focus();
  }, [open, selected]);

  const options = () => Array.from(listRef.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? []);

  const openAndFocus = () => {
    wantFocus.current = true;
    setOpen(true);
  };

  const close = () => {
    setOpen(false);
    btnRef.current?.focus();
  };

  const onBtnKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      openAndFocus();
    } else if (e.key === "Escape" && open) {
      e.preventDefault();
      close();
    }
  };

  const onListKey = (e: KeyboardEvent) => {
    const opts = options();
    const i = opts.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      opts[(i + 1) % opts.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      opts[(i - 1 + opts.length) % opts.length]?.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      opts[0]?.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      opts[opts.length - 1]?.focus();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  };

  const choose = (tag: string) => {
    onSelect(tag);
    close();
  };

  return (
    <div className="own" ref={rootRef}>
      <div className={`combo${open ? " open" : ""}`}>
        <button
          type="button"
          ref={btnRef}
          className="combo-btn"
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={() => (open ? setOpen(false) : openAndFocus())}
          onKeyDown={onBtnKey}
        >
          {current ? (
            <span className="chosen">
              <span className={`dot ${current.fit}`} style={{ marginRight: "0.5rem" }} />
              <span className="nm">{current.name}</span>
            </span>
          ) : (
            <span className="ph">Let me pick my own model</span>
          )}
          <span className="caret" aria-hidden="true">
            ▾
          </span>
        </button>
        <div
          className="list"
          role="listbox"
          aria-label="Models"
          ref={listRef}
          aria-hidden={!open}
          onKeyDown={onListKey}
        >
          {open && GROUPS.map(({ fit, title }) => {
            const inGroup = models.filter((m) => m.fit === fit);
            if (inGroup.length === 0) return null;
            const gid = `${idBase}-${fit}`;
            return (
              <div role="group" aria-labelledby={gid} key={fit}>
                <div className="group" id={gid}>
                  {title}
                </div>
                {inGroup.map((m) => (
                  <button
                    type="button"
                    role="option"
                    key={m.tag}
                    data-tag={m.tag}
                    aria-selected={m.tag === selected}
                    tabIndex={-1}
                    className={`opt${m.tag === selected ? " active" : ""}`}
                    onClick={() => choose(m.tag)}
                  >
                    <span className={`dot ${m.fit}`} />
                    <span className="nm">{m.name}</span>
                    <span className="mk">{m.maker}</span>
                    <span className="sz">{m.download_gb} GB</span>
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      </div>
      {current && (
        <div className="info" key={current.tag}>
          <div className="row">
            <span className="tname">{current.name}</span>
            <span className="meta">by {current.maker}</span>
            {badge && <Badge kind={badge.kind}>{badge.label}</Badge>}
          </div>
          <div className="grid">
            <div className="cell">
              <div className="k">Download</div>
              <div className="v">{current.download_gb} GB</div>
            </div>
            <div className="cell">
              <div className="k">Minimum</div>
              <div className="v">{current.needed_gb} GB</div>
            </div>
            <div className="cell">
              <div className="k">Recommended</div>
              <div className="v">{current.recommended_gb} GB</div>
            </div>
            <div className="cell">
              <div className="k">Your device</div>
              <div className="v">{usableGb} GB</div>
            </div>
          </div>
          <FitBar neededGb={current.needed_gb} usableGb={usableGb} fit={current.fit} />
          <p className="blurb">{current.blurb}</p>
        </div>
      )}
    </div>
  );
}

import type { ReactNode } from "react";
import type { StepPosition } from "../setup/flow";

type Props = {
  step: StepPosition;
  title: string;
  lede?: ReactNode;
  children?: ReactNode;
  /** Passed through to the card, e.g. "polite" for screens that update by themselves. */
  live?: "polite";
};

export function StepShell({ step, title, lede, children, live }: Props) {
  return (
    <section className="card" aria-live={live}>
      <div className="eyebrow">
        Step {step.n}
        {step.total ? ` of ${step.total}` : ""} · {step.label}
      </div>
      <h1>{title}</h1>
      {lede && <p className="lede">{lede}</p>}
      <div className="stack">{children}</div>
    </section>
  );
}

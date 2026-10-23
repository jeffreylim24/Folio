import type { ReactNode } from "react";
import { Check, Gauge, Sparkles, TriangleAlert } from "lucide-react";
import type { BadgeKind } from "../setup/modelTypes";

const ICONS = { rec: Sparkles, easy: Check, tight: Gauge, no: TriangleAlert };

export function Badge({ kind, children }: { kind: BadgeKind; children: ReactNode }) {
  const Icon = ICONS[kind];
  return (
    <span className={`badge ${kind}`}>
      <Icon aria-hidden="true" />
      {children}
    </span>
  );
}

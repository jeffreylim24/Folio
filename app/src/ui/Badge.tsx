import type { ReactNode } from "react";

export function Badge({ kind, children }: { kind: "rec" | "easy" | "tight" | "no"; children: ReactNode }) {
  return <span className={`badge ${kind}`}>{children}</span>;
}

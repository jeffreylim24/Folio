import { useEffect, useState } from "react";

type Props = { neededGb: number; usableGb: number; fit: "ok" | "tight" | "no" };

const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

export function FitBar({ neededGb, usableGb, fit }: Props) {
  const scale = Math.max(28, neededGb * 1.1);
  const target = Math.min(100, (neededGb / scale) * 100);
  const limit = Math.min(100, (usableGb / scale) * 100);
  // Start empty so the bar fills in once it appears.
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setWidth(target));
    return () => cancelAnimationFrame(id);
  }, [target]);

  return (
    <div className="fit">
      <div className="bar">
        <div className={`fill ${fit}`} style={{ width: `${width}%` }} />
        <div className="limit" style={{ left: `${limit}%` }} />
      </div>
      <div className="fitlabel">
        <span>{fmt(neededGb)} GB needed</span>
        <span>{fmt(usableGb)} GB usable</span>
      </div>
    </div>
  );
}

import { useEffect, useRef } from "react";

/**
 * Calls `tick` once a second while `enabled` (and once right away if
 * `immediate`). A tick is skipped while the previous one is still pending, so
 * a slow engine never sees stacked requests. Stops on unmount.
 */
export function usePoll(
  tick: () => Promise<void>,
  enabled: boolean,
  immediate = false,
): void {
  const latest = useRef(tick);
  latest.current = tick;
  const inFlight = useRef(false);
  useEffect(() => {
    if (!enabled) return;
    const run = () => {
      if (inFlight.current) return;
      inFlight.current = true;
      latest.current().finally(() => {
        inFlight.current = false;
      });
    };
    if (immediate) run();
    const id = setInterval(run, 1000);
    return () => clearInterval(id);
  }, [enabled, immediate]);
}

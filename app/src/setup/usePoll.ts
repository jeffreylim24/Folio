import { useEffect, useRef } from "react";

/** Calls `tick` once a second while `enabled`; stops on unmount. */
export function usePoll(tick: () => void, enabled: boolean): void {
  const latest = useRef(tick);
  latest.current = tick;
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => latest.current(), 1000);
    return () => clearInterval(id);
  }, [enabled]);
}

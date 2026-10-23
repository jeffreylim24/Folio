// Mirrors the JSON returned by GET /setup/hardware (snake_case, as sent).
export type Fit = "ok" | "tight" | "no";
export type Tier = "small" | "balanced" | "best";

export type Device = {
  total_ram_gb: number;
  usable_gb: number;
  free_disk_gb: number;
  chip_label: string;
  chip_note: string;
};

export type ModelOption = {
  tag: string;
  name: string;
  maker: string;
  blurb: string;
  tier: Tier | null;
  download_gb: number;
  needed_gb: number;
  recommended_gb: number;
  est_minutes: number;
  fit: Fit;
  note: string;
  disk_short_gb: number | null;
};

export type Advice = {
  device: Device;
  recommended: string | null;
  reason: "ok" | "memory" | "disk";
  message: string;
  tiers: ModelOption[];
  models: ModelOption[];
};

export const TIER_NAMES: Record<Tier, string> = {
  small: "Small",
  balanced: "Balanced",
  best: "Best quality",
};

export const FIT_LABELS: Record<Fit, string> = {
  ok: "Fits easily",
  tight: "Might be slow",
  no: "Too big for your device",
};

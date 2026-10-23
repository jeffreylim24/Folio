type Props = {
  /** 0..1. Leave out when the length of the wait isn't known. */
  value?: number;
  label: string;
};

export function ProgressBar({ value, label }: Props) {
  const known = value !== undefined;
  const percent = known ? Math.max(0, Math.min(100, Math.floor(value * 100))) : undefined;
  return (
    <div
      className={`progressbar${known ? "" : " indeterminate"}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      <div className="progressfill" style={known ? { width: `${percent}%` } : undefined} />
    </div>
  );
}

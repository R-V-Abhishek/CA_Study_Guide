interface ProgressRingProps {
  percentage: number;
  size?: number;
  strokeWidth?: number;
  showText?: boolean;
  subtext?: string;
  className?: string;
}

export function ProgressRing({
  percentage,
  size = 72,
  strokeWidth = 6,
  showText = true,
  subtext,
  className = "",
}: ProgressRingProps) {
  const normalizedPct = Math.min(100, Math.max(0, percentage));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (normalizedPct / 100) * circumference;

  // Colour transitions from red (0–33%) through amber (33–66%) to emerald/green (66–100%)
  const color =
    normalizedPct >= 66
      ? "text-emerald-500 stroke-emerald-500"
      : normalizedPct >= 33
      ? "text-amber-500 stroke-amber-500"
      : "text-rose-500 stroke-rose-500";

  return (
    <div
      className={`relative inline-flex items-center justify-center ${className}`}
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="transform -rotate-90"
      >
        {/* Track circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={strokeWidth}
          className="stroke-stone-200 dark:stroke-stone-800"
          fill="transparent"
        />
        {/* Progress arc */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          className={`${color} transition-all duration-700 ease-out`}
          fill="transparent"
        />
      </svg>
      {showText && (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-xs font-bold tracking-tight text-stone-900 dark:text-stone-100">
            {Math.round(normalizedPct)}%
          </span>
          {subtext && (
            <span className="text-[10px] text-stone-400 font-medium leading-none mt-0.5">
              {subtext}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

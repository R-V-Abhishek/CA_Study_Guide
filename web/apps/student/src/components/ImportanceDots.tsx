export function ImportanceDots({
  score,
  size = "md",
}: {
  score: number;
  size?: "sm" | "md" | "lg";
}) {
  const filled = Math.round(score * 5);
  const color =
    score >= 0.8
      ? "text-red-600 dark:text-red-500"
      : score >= 0.6
      ? "text-orange-500"
      : score >= 0.4
      ? "text-amber-500"
      : "text-stone-400 dark:text-stone-500";
  const sizes = { sm: "text-xs gap-0.5", md: "text-sm gap-1", lg: "text-base gap-1.5" };

  return (
    <span
      className={`inline-flex items-center ${sizes[size]}`}
      title={`Importance: ${Math.round(score * 100)}%`}
      aria-label={`Importance rating: ${filled} out of 5 stars`}
    >
      {[1, 2, 3, 4, 5].map((i) => (
        <span
          key={i}
          className={i <= filled ? color : "text-stone-200 dark:text-stone-800"}
        >
          ●
        </span>
      ))}
    </span>
  );
}

export function getImportanceLabel(score: number): {
  label: string;
  color: string;
  bg: string;
} {
  if (score >= 0.8) {
    return {
      label: "Critical",
      color: "text-red-700 dark:text-red-400",
      bg: "bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-900/50",
    };
  }
  if (score >= 0.6) {
    return {
      label: "High Yield",
      color: "text-orange-700 dark:text-orange-400",
      bg: "bg-orange-50 dark:bg-orange-950/40 border-orange-200 dark:border-orange-900/50",
    };
  }
  if (score >= 0.4) {
    return {
      label: "Medium",
      color: "text-amber-700 dark:text-amber-400",
      bg: "bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-900/50",
    };
  }
  return {
    label: "Low",
    color: "text-stone-600 dark:text-stone-400",
    bg: "bg-stone-50 dark:bg-stone-800/40 border-stone-200 dark:border-stone-700/50",
  };
}

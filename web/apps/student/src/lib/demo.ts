/**
 * Demo Mode helper
 * Activated by ?demo=true query param or VITE_DEMO_MODE=true env var
 */
export const isDemoMode = (): boolean => {
  if (typeof window === "undefined") return false;
  return (
    new URLSearchParams(window.location.search).get("demo") === "true" ||
    import.meta.env.VITE_DEMO_MODE === "true"
  );
};

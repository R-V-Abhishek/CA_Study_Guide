import { useEffect, useState } from 'react';

export type ThemePreference = 'system' | 'light' | 'dark';
const preferenceKey = 'caf_theme';
const themeEvent = 'caf-theme-changed';

function readPreference(): ThemePreference {
  let value: string | null = null;
  try { value = localStorage.getItem(preferenceKey); } catch { return 'dark'; }
  return value === 'light' || value === 'dark' || value === 'system' ? value : 'dark';
}

/** Both workspaces default to dark; System is an explicit preference. */
export function useTheme() {
  const [preference, setPreference] = useState<ThemePreference>(readPreference);
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
      const current = readPreference();
      setPreference(current);
      document.documentElement.classList.toggle('dark', current === 'dark' || (current === 'system' && media.matches));
    };
    apply();
    media.addEventListener('change', apply);
    window.addEventListener('storage', apply);
    window.addEventListener(themeEvent, apply);
    return () => {
      media.removeEventListener('change', apply);
      window.removeEventListener('storage', apply);
      window.removeEventListener(themeEvent, apply);
    };
  }, []);
  const choose = (next: ThemePreference) => {
    localStorage.setItem(preferenceKey, next);
    window.dispatchEvent(new Event(themeEvent));
  };
  return { preference, choose };
}

export function ThemeControl() {
  const { preference, choose } = useTheme();
  return <label className="theme-control">Appearance
    <select aria-label="Appearance" value={preference} onChange={event => choose(event.target.value as ThemePreference)}>
      <option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option>
    </select>
  </label>;
}

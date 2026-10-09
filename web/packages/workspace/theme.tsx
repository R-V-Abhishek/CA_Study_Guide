import { useEffect, useState } from 'react';

export type ThemePreference = 'system' | 'light' | 'dark';
const preferenceKey = 'caf_theme';
const themeEvent = 'caf-theme-changed';

function readPreference(): ThemePreference {
  const value = localStorage.getItem(preferenceKey);
  return value === 'light' || value === 'dark' ? value : 'system';
}

/** Both workspaces follow the OS until a person explicitly chooses a theme. */
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
    if (next === 'system') localStorage.removeItem(preferenceKey);
    else localStorage.setItem(preferenceKey, next);
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

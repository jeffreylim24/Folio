export type Theme = "light" | "dark";

const KEY = "folio-theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

// Storage can throw (private mode, blocked site data); the app still works
// without it and simply follows the system theme.
export function savedTheme(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // Not remembered across launches; fine.
  }
}

export function systemTheme(): Theme {
  return typeof matchMedia === "function" && matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

/** Sets the theme on <html>; null goes back to following the system. */
export function applyTheme(theme: Theme | null): void {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

import { useState } from "react";
import { Moon, Sun } from "lucide-react";
import { applyTheme, saveTheme, savedTheme, systemTheme, type Theme } from "../theme";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => savedTheme() ?? systemTheme());
  const next: Theme = theme === "dark" ? "light" : "dark";

  const toggle = () => {
    applyTheme(next);
    saveTheme(next);
    setTheme(next);
  };

  return (
    <button type="button" className="theme-toggle" aria-label={`Switch to ${next} mode`} onClick={toggle}>
      {theme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
    </button>
  );
}

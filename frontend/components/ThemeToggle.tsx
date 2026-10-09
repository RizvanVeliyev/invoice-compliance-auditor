"use client";

import { useEffect, useState } from "react";
import Icon from "@/components/Icon";
import { useI18n } from "@/lib/i18n";

type Theme = "light" | "dark";

/** Light / dark switch. The first paint is handled by the small script in the layout. */
export default function ThemeToggle() {
  const { t } = useI18n();
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  }, []);

  function flip() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("ledger.theme", next);
    } catch {
      /* the choice lasts for this page only */
    }
  }

  const label = t(theme === "dark" ? "theme.to_light" : "theme.to_dark");
  return (
    <button type="button" className="icon-btn" onClick={flip} aria-label={label} title={label}>
      <Icon name={theme === "dark" ? "sun" : "moon"} />
    </button>
  );
}

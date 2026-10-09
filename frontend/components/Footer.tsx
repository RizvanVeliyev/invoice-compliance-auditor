"use client";

import { useI18n } from "@/lib/i18n";

export default function Footer() {
  const { t } = useI18n();
  return (
    <footer className="foot">
      <span>{t("footer.policy")}</span>
      <span>{t("footer.principle")}</span>
    </footer>
  );
}

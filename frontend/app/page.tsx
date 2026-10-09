"use client";

import Link from "next/link";
import HeroDemo from "@/components/HeroDemo";
import PolicyList from "@/components/PolicyList";
import { useI18n } from "@/lib/i18n";

export default function Home() {
  const { t } = useI18n();
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <h1>{t("home.h1")}</h1>
          <p className="lede">{t("home.lede")}</p>
          <div className="cta-row">
            <Link href="/submit" className="btn btn-primary">
              {t("nav.submit")}
            </Link>
            <Link href="/audit" className="btn btn-ghost">
              {t("home.cta_audit")}
            </Link>
            <Link href="/login?register" className="btn btn-ghost">
              {t("home.cta_register")}
            </Link>
          </div>
        </div>
        <HeroDemo />
      </section>

      <section className="steps" aria-labelledby="how">
        <h2 id="how">{t("home.how")}</h2>
        <ol>
          {[1, 2, 3].map((n) => (
            <li key={n}>
              <h3>{t(`home.s${n}_t`)}</h3>
              <p>{t(`home.s${n}_p`)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="rules" aria-labelledby="rules">
        <h2 id="rules">{t("home.rules")}</h2>
        <PolicyList />
      </section>
    </>
  );
}

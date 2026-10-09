import Link from "next/link";
import HeroDemo from "@/components/HeroDemo";
import PolicyList from "@/components/PolicyList";

export default function Home() {
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <h1>Every invoice checked against policy before anyone pays it.</h1>
          <p className="lede">
            Employees send their invoice as a PDF. Ledger reads it, applies the expense policy, and alerts the
            audit team when a rule is broken, naming the rule and showing the numbers.
          </p>
          <div className="cta-row">
            <Link href="/submit" className="btn btn-primary">
              Submit an invoice
            </Link>
            <Link href="/audit" className="btn btn-ghost">
              Open the audit desk
            </Link>
          </div>
        </div>
        <HeroDemo />
      </section>

      <section className="steps" aria-labelledby="how">
        <h2 id="how">What happens to a submitted invoice</h2>
        <ol>
          <li>
            <h3>The AI reads it</h3>
            <p>
              Vendor, amount, dates, nights, guests and approvals are pulled from the PDF, a photo or an email,
              in English, Azerbaijani or Russian.
            </p>
          </li>
          <li>
            <h3>The policy decides</h3>
            <p>
              Fixed rules do the maths: per person, per night, approval levels, approved vendors. Text hidden in
              the invoice can&apos;t change the outcome.
            </p>
          </li>
          <li>
            <h3>The audit team is alerted</h3>
            <p>
              Clean invoices pass. Anything flagged or unclear lands on the audit desk with the reason, ready to
              approve or reject.
            </p>
          </li>
        </ol>
      </section>

      <section className="rules" aria-labelledby="rules">
        <h2 id="rules">The rules being enforced</h2>
        <PolicyList />
      </section>
    </>
  );
}

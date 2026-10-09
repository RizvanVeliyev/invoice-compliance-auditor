import type { Metadata } from "next";
import "@fontsource/familjen-grotesk/400.css";
import "@fontsource/familjen-grotesk/500.css";
import "@fontsource/familjen-grotesk/600.css";
import "@fontsource/familjen-grotesk/700.css";
import "@fontsource/courier-prime/400.css";
import "@fontsource/courier-prime/700.css";
import "./globals.css";
import Nav from "@/components/Nav";
import { ToastProvider } from "@/components/Toasts";

export const metadata: Metadata = {
  title: "Ledger — Invoice Compliance Auditor",
  description:
    "Employees send invoice PDFs; Ledger checks each one against the expense policy and alerts the audit team.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ToastProvider>
          <a className="skip" href="#main">
            Skip to content
          </a>
          <Nav />
          <main id="main">{children}</main>
          <footer className="foot">
            <span>Ledger checks invoices against Nordvik Holdings expense policy v2.4.</span>
            <span>The AI reads the document; the policy rules decide.</span>
          </footer>
        </ToastProvider>
      </body>
    </html>
  );
}

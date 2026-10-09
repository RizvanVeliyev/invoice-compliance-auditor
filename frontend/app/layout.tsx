import type { Metadata } from "next";
import "@fontsource/familjen-grotesk/400.css";
import "@fontsource/familjen-grotesk/500.css";
import "@fontsource/familjen-grotesk/600.css";
import "@fontsource/familjen-grotesk/700.css";
import "@fontsource/courier-prime/400.css";
import "@fontsource/courier-prime/700.css";
import "./globals.css";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";
import { AuthProvider } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";
import { ToastProvider } from "@/components/Toasts";

export const metadata: Metadata = {
  title: "FiscalAI — Invoice Compliance Auditor",
  description:
    "Employees send invoice PDFs; FiscalAI checks each one against the expense policy and alerts the audit team.",
};

// Runs before the page is drawn: the saved choice, otherwise the system setting.
const THEME_BOOT = `try{var t=localStorage.getItem("ledger.theme");if(t!=="dark"&&t!=="light")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body>
        <I18nProvider>
          <AuthProvider>
            <ToastProvider>
              <Nav />
              <main id="main">{children}</main>
              <Footer />
            </ToastProvider>
          </AuthProvider>
        </I18nProvider>
      </body>
    </html>
  );
}

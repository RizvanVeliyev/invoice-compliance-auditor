/** The FiscalAI mark: a paper receipt with a torn lower edge, two printed lines and a check. */
export function LogoMark({ size = 30 }: { size?: number }) {
  return (
    <svg className="logo-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden focusable="false">
      <path
        className="logo-paper"
        d="M7 3.5h18a2 2 0 0 1 2 2V28l-3.67-2.2L19.67 28 16 25.8 12.33 28 8.67 25.8 5 28V5.5a2 2 0 0 1 2-2z"
      />
      <path className="logo-line" d="M10 9.5h12M10 13.5h7" />
      <path className="logo-check" d="m11 19 3.2 3.2L21.5 15" />
    </svg>
  );
}

export default function Logo({ size = 30 }: { size?: number }) {
  return (
    <span className="logo">
      <LogoMark size={size} />
      <span className="logo-word">
        Fiscal<span className="logo-ai">AI</span>
      </span>
    </span>
  );
}

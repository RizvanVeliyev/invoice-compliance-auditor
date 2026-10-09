"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";
import { LogoMark } from "@/components/Logo";
import { isAuditor, postJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

type Tone = "ok" | "warn" | "bad" | "info";
type Action = { label: string; href: string };
type Msg = { id: number; from: "me" | "bot"; text: string; at: number; tone?: Tone; actions?: Action[]; error?: boolean };
type Reply = { text: string; tone: Tone; actions: Action[]; source: "rules" | "model"; suggestions: string[] };
const STORE = "ledger.chat";
const TONE_ICON: Record<Tone, string> = { ok: "check", warn: "bell", bad: "x", info: "note" };

/** The assistant: a round button in the corner that opens a conversation. Signed-in people only. */
export default function ChatWidget() {
  const { user } = useAuth();
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(false);
  const [wide, setWide] = useState(false);
  const [seen, setSeen] = useState(true);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const userId = user?.id;

  // The conversation survives moving between pages, and belongs to the person who had it.
  useEffect(() => {
    setMessages([]);
    setSuggestions([]);
    if (!userId) {
      setOpen(false);
      return;
    }
    try {
      const saved = JSON.parse(sessionStorage.getItem(`${STORE}.${userId}`) || "null");
      if (Array.isArray(saved)) setMessages(saved);
      setSeen(localStorage.getItem(`${STORE}.seen`) === "1"); // a small dot invites a first look
    } catch {
      /* start empty */
    }
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    try {
      sessionStorage.setItem(`${STORE}.${userId}`, JSON.stringify(messages.slice(-40)));
    } catch {
      /* not saved */
    }
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [messages, userId, busy]);

  useEffect(() => {
    if (!open) return;
    setSeen(true);
    try {
      localStorage.setItem(`${STORE}.seen`, "1");
    } catch {
      /* ignore */
    }
    const timer = setTimeout(() => input.current?.focus(), 60);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;
  const auditor = isAuditor(user);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setDraft("");
    setBusy(true);
    setMessages((m) => [...m, { id: Date.now(), from: "me", text: message, at: Date.now() }]);
    try {
      const r = await postJson<Reply>("/api/chat", { message, lang });
      setMessages((m) => [...m, { id: Date.now() + 1, from: "bot", text: r.text, at: Date.now(), tone: r.tone, actions: r.actions }]);
      setSuggestions(r.suggestions || []);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { id: Date.now() + 1, from: "bot", text: e instanceof Error ? e.message : t("chat.error"), at: Date.now(), error: true },
      ]);
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  }

  const time = (at: number) => {
    const d = new Date(at);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  };
  const cards = [
    { icon: "file", title: t("chat.c1"), text: t("chat.c1d"), ask: t(auditor ? "chat.c1a" : "chat.c1q") },
    { icon: "bolt", title: t("chat.c2"), text: t("chat.c2d"), ask: t("chat.c2q") },
    { icon: auditor ? "inbox" : "chart", title: t(auditor ? "chat.c3a_t" : "chat.c3"), text: t(auditor ? "chat.c3a_d" : "chat.c3d"), ask: t(auditor ? "chat.c3a" : "chat.c3q") },
  ];
  const starters = [t("chat.s1"), t("chat.s2"), t("chat.s3"), t("chat.s4")];
  const chips = suggestions.length ? suggestions : starters;

  return (
    <>
      {open && (
        <section className={`chat${wide ? " is-wide" : ""}`} role="dialog" aria-label={t("chat.title")}>
          <header className="chat-head">
            <span className="chat-mark">
              <LogoMark size={26} />
              <span className="chat-online" aria-hidden />
            </span>
            <span className="chat-title">
              <strong>{t("chat.title")}</strong>
              <span>{t("chat.sub")}</span>
            </span>
            {messages.length > 0 && (
              <button
                className="chat-tool"
                title={t("chat.clear")}
                aria-label={t("chat.clear")}
                onClick={() => {
                  setMessages([]);
                  setSuggestions([]);
                }}
              >
                <Icon name="undo" size={16} />
              </button>
            )}
            <button className="chat-tool chat-wide" title={t(wide ? "chat.smaller" : "chat.bigger")} aria-label={t(wide ? "chat.smaller" : "chat.bigger")} onClick={() => setWide((v) => !v)}>
              <Icon name={wide ? "shrink" : "grow"} size={16} />
            </button>
            <button className="chat-tool" title={t("common.dismiss")} aria-label={t("common.dismiss")} onClick={() => setOpen(false)}>
              <Icon name="x" size={18} />
            </button>
          </header>

          <div className="chat-list" ref={list} aria-live="polite">
            {messages.length === 0 && (
              <div className="chat-welcome">
                <p className="chat-hi">{t("chat.hi", { name: user.name.split(" ")[0] })}</p>
                <p className="chat-lead">{t("chat.lead")}</p>
                <div className="chat-cards">
                  {cards.map((c) => (
                    <button key={c.title} className="chat-card" onClick={() => send(c.ask)} disabled={busy}>
                      <span className="chat-card-icon">
                        <Icon name={c.icon} size={18} />
                      </span>
                      <span className="chat-card-text">
                        <strong>{c.title}</strong>
                        <span>{c.text}</span>
                        <em>“{c.ask}”</em>
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) =>
              m.from === "me" ? (
                <div key={m.id} className="row row-me">
                  <div className="bubble bubble-me">{m.text}</div>
                  <span className="stamp-time">{time(m.at)}</span>
                </div>
              ) : (
                <div key={m.id} className="row row-bot">
                  <span className="bot-face" aria-hidden>
                    <LogoMark size={16} />
                  </span>
                  <div className="row-body">
                    <div className={`bubble bubble-bot tone-${m.error ? "bad" : m.tone || "info"}`}>
                      {m.tone && m.tone !== "info" && !m.error && (
                        <span className={`verdict verdict-${m.tone}`}>
                          <Icon name={TONE_ICON[m.tone]} size={13} />
                          {t(`chat.tone_${m.tone}`)}
                        </span>
                      )}
                      {m.text}
                    </div>
                    {m.actions && m.actions.length > 0 && (
                      <div className="chat-actions">
                        {m.actions.map((a) => (
                          <Link key={a.href} href={a.href} className="chat-action" onClick={() => window.innerWidth < 700 && setOpen(false)}>
                            {a.label}
                            <Icon name="arrow" size={14} />
                          </Link>
                        ))}
                      </div>
                    )}
                    <span className="stamp-time">{time(m.at)}</span>
                  </div>
                </div>
              ),
            )}
            {busy && (
              <div className="row row-bot">
                <span className="bot-face" aria-hidden>
                  <LogoMark size={16} />
                </span>
                <div className="bubble bubble-bot bubble-typing" aria-label={t("chat.thinking")}>
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
          </div>

          {messages.length > 0 && (
            <div className="chat-chips">
              {chips.map((c) => (
                <button key={c} className="chip" disabled={busy} onClick={() => send(c)}>
                  {c}
                </button>
              ))}
            </div>
          )}

          <form
            className="chat-form"
            onSubmit={(e) => {
              e.preventDefault();
              send(draft);
            }}
          >
            <input
              ref={input}
              value={draft}
              maxLength={600}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={t("chat.placeholder")}
              aria-label={t("chat.placeholder")}
            />
            <button className="chat-send" disabled={busy || !draft.trim()} aria-label={t("chat.send")} title={t("chat.send")}>
              <Icon name="send" />
            </button>
          </form>
          <p className="chat-foot">{t("chat.foot")}</p>
        </section>
      )}

      <button
        className={`chat-fab${open ? " is-open" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={t(open ? "common.dismiss" : "chat.open")}
        title={t(open ? "common.dismiss" : "chat.open")}
      >
        <Icon name={open ? "x" : "chat"} size={24} />
        {!open && !seen && <span className="chat-dot" aria-hidden />}
      </button>
    </>
  );
}

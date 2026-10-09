"use client";

import { useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";
import { LogoMark } from "@/components/Logo";
import { postJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

type Msg = { id: number; from: "me" | "bot"; text: string; error?: boolean };
type Reply = { text: string; source: "rules" | "model"; suggestions: string[] };
const STORE = "ledger.chat";

/** The assistant: a round button in the corner that opens a small conversation. Signed-in people only. */
export default function ChatWidget() {
  const { user } = useAuth();
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(false);
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
    if (open) setTimeout(() => input.current?.focus(), 60);
  }, [open]);

  if (!user) return null;

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setDraft("");
    setBusy(true);
    setMessages((m) => [...m, { id: Date.now(), from: "me", text: message }]);
    try {
      const r = await postJson<Reply>("/api/chat", { message, lang });
      setMessages((m) => [...m, { id: Date.now() + 1, from: "bot", text: r.text }]);
      setSuggestions(r.suggestions || []);
    } catch (e) {
      setMessages((m) => [...m, { id: Date.now() + 1, from: "bot", text: e instanceof Error ? e.message : t("chat.error"), error: true }]);
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  }

  const starters = [t("chat.s1"), t("chat.s2"), t("chat.s3"), t("chat.s4")];
  const chips = suggestions.length ? suggestions : starters;

  return (
    <>
      {open && (
        <section className="chat" role="dialog" aria-label={t("chat.title")}>
          <header className="chat-head">
            <span className="chat-mark">
              <LogoMark size={26} />
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
            <button className="chat-tool" title={t("common.dismiss")} aria-label={t("common.dismiss")} onClick={() => setOpen(false)}>
              <Icon name="x" size={18} />
            </button>
          </header>

          <div className="chat-list" ref={list} aria-live="polite">
            <div className="bubble bubble-bot">{t("chat.hello", { name: user.name.split(" ")[0] })}</div>
            {messages.map((m) => (
              <div key={m.id} className={`bubble bubble-${m.from}${m.error ? " bubble-error" : ""}`}>
                {m.text}
              </div>
            ))}
            {busy && (
              <div className="bubble bubble-bot bubble-typing" aria-label={t("chat.thinking")}>
                <span />
                <span />
                <span />
              </div>
            )}
          </div>

          <div className="chat-chips">
            {chips.map((c) => (
              <button key={c} className="chip" disabled={busy} onClick={() => send(c)}>
                {c}
              </button>
            ))}
          </div>

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
              <Icon name="arrow" />
            </button>
          </form>
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
      </button>
    </>
  );
}

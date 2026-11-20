import { useCallback, useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api, type ChatReply } from "./api";
import { scrollBehavior } from "./motion";
import { useApp } from "./store";

interface Msg { role: "user" | "assistant"; content: string; mode?: ChatReply["mode"]; error?: boolean }

// Minimal typing for the Web Speech API, which is not in every TypeScript DOM lib.
interface SpeechResultEvent { results: ArrayLike<ArrayLike<{ transcript: string }>> }
interface Recognition {
  lang: string; interimResults: boolean; start(): void; stop(): void;
  onresult: ((e: SpeechResultEvent) => void) | null; onend: (() => void) | null; onerror: (() => void) | null;
}
type RecognitionCtor = new () => Recognition;
type SpeechWindow = Window & { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };

/** The browser's speech recogniser, if it has one (Chrome/Edge/Safari; not Firefox). */
export function speechRecognition(w: SpeechWindow = window): RecognitionCtor | undefined {
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

const SUGGEST = {
  en: ["Is it safe to jog now?", "Should my kids play outside?", "No purifier — what can I do?", "Best way to commute today?"],
  hi: ["Aaj bahar walk karna safe hai?", "क्या बच्चे बाहर खेल सकते हैं?", "प्यूरीफायर नहीं है, क्या करूँ?", "आज ऑफिस कैसे जाऊँ?"],
};

// Tiny, safe markdown: **bold** and "* " / "- " bullets → React elements (no innerHTML).
function inline(s: string): ReactNode[] {
  return s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part);
}
/** Render the assistant's reply: paragraphs, bullet lists and **bold**, never raw HTML. */
export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(<ul key={blocks.length} style={{ margin: "4px 0", paddingLeft: 18 }}>{list.map((l, i) => <li key={i}>{inline(l)}</li>)}</ul>);
    }
    list = [];
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const m = line.match(/^[*-]\s+(.*)/);
    if (m) { list.push(m[1]); continue; }
    flush();
    if (line) blocks.push(<p key={blocks.length} style={{ margin: "4px 0" }}>{inline(line.replace(/^#+\s*/, ""))}</p>);
  }
  flush();
  return <>{blocks}</>;
}

/** Floating AI assistant: a non-modal dialog with text and voice input, grounded on the selected city's air. */
export default function Chat() {
  const { t, tx, lang, place, household } = useApp();
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const fabRef = useRef<HTMLButtonElement>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const recRef = useRef<Recognition | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const SR = speechRecognition();

  const close = useCallback(() => {
    setOpen(false);
    recRef.current?.stop();
    requestAnimationFrame(() => fabRef.current?.focus()); // return focus to the button that opened the chat
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: scrollBehavior() }); }, [msgs, busy]);
  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);
  useEffect(() => {
    // Escape closes the chat only when focus is inside it, so it doesn't fight other widgets.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && panelRef.current?.contains(document.activeElement)) close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const speak = (s: string) => {
    if (!("speechSynthesis" in window)) return;
    const u = new SpeechSynthesisUtterance(s.replace(/[*#_`]/g, ""));
    u.lang = lang === "hi" ? "hi-IN" : "en-IN";
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  };

  // Refs so the speech callback (created when the mic starts) always sees current state.
  const msgsRef = useRef(msgs);
  const busyRef = useRef(busy);
  useEffect(() => { msgsRef.current = msgs; busyRef.current = busy; }, [msgs, busy]);
  const send = async (content: string, viaVoice = false) => {
    const q = content.trim();
    if (!q || busyRef.current) return;
    busyRef.current = true;
    // Error bubbles ("You seem to be offline") are not real assistant turns: keep them out of the AI's history.
    const history = msgsRef.current.filter((m) => !m.error).slice(-10)
      .map(({ role, content }) => ({ role, content: content.slice(0, 2000) }));
    setMsgs((m) => [...m, { role: "user", content: q }]);
    setText("");
    setBusy(true);
    try {
      const r = await api.chat({
        message: q.slice(0, 1000), history, lat: place?.lat, lon: place?.lon, place: place?.name, household, lang,
      });
      setMsgs((m) => [...m, { role: "assistant", content: r.reply, mode: r.mode }]);
      if (viaVoice) speak(r.reply);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", content: `⚠️ ${(e as Error).message}`, error: true }]);
    } finally { busyRef.current = false; setBusy(false); }
  };

  const sendRef = useRef(send);
  useEffect(() => { sendRef.current = send; });
  const toggleMic = () => {
    if (listening) { recRef.current?.stop(); return; }
    if (!SR) return;
    const rec = new SR();
    rec.lang = lang === "hi" ? "hi-IN" : "en-IN";
    rec.interimResults = false;
    rec.onresult = (e) => { sendRef.current(e.results[0][0].transcript, true); };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    try {
      rec.start();
      setListening(true);
    } catch {
      setListening(false); // mic blocked or already in use
    }
  };

  const onSubmit = (e: FormEvent) => { e.preventDefault(); send(text); };

  return (
    <>
      {open && (
        // Non-modal dialog: the page stays usable behind it; Escape inside it closes and returns focus to the button.
        <div id="chat-panel" ref={panelRef} className="chat" role="dialog" aria-labelledby={titleId}>
          <header>
            <img src="/logo-96.png" alt="" width={32} height={32} />
            <div>
              <b id={titleId}>{t("chat_title")}</b>
              <div className="small" style={{ opacity: .85 }}>{place ? `📍 ${place.name}` : tx("AI air assistant", "AI वायु सहायक")}</div>
            </div>
            <button type="button" onClick={close} aria-label={tx("Close chat", "चैट बंद करें")}>✕</button>
          </header>
          <div className="msgs" role="log" aria-live="polite" aria-label={t("chat_title")}>
            {msgs.length === 0 && (
              <div className="msg bot">
                <span aria-hidden="true">👋</span>{" "}
                {lang === "hi" ? "नमस्ते! मैं आपके शहर की हवा के हिसाब से सलाह देता हूँ।" : "Hi! I give advice based on your city's air right now."}
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`msg ${m.role === "user" ? "user" : "bot"}`}
                style={{ whiteSpace: m.role === "user" ? "pre-wrap" : "normal" }}>
                <span className="sr-only">{m.role === "user" ? tx("You:", "आप:") : tx("Assistant:", "सहायक:")} </span>
                {m.role === "user" ? m.content : <Markdown text={m.content} />}
                {m.mode === "rules" && (
                  <div className="small muted" style={{ marginTop: 4 }}><span aria-hidden="true">⚙️</span> {t("rules_mode")}</div>
                )}
              </div>
            ))}
            {busy && (
              <div className="msg bot typing" role="status" aria-label={tx("Typing", "लिख रहा है")}>
                <span aria-hidden="true" /><span aria-hidden="true" /><span aria-hidden="true" />
              </div>
            )}
            <div ref={endRef} />
          </div>
          {msgs.length === 0 && (
            <div className="suggest">
              {SUGGEST[lang].map((s) => <button key={s} type="button" className="chip" onClick={() => send(s)}>{s}</button>)}
            </div>
          )}
          <form onSubmit={onSubmit}>
            {SR && (
              <button type="button" className={`icon-btn ${listening ? "live" : ""}`} onClick={toggleMic} disabled={busy && !listening}
                aria-label={t("speak")} aria-pressed={listening}><span aria-hidden="true">🎤</span></button>
            )}
            <label className="sr-only" htmlFor="chat-in">{t("chat_placeholder")}</label>
            <input id="chat-in" ref={inputRef} type="text" value={text} maxLength={1000} placeholder={t("chat_placeholder")}
              onChange={(e) => setText(e.target.value)} />
            <button className="btn small" type="submit" disabled={busy || !text.trim()} aria-label={t("send")}>
              <span aria-hidden="true">➤</span>
            </button>
          </form>
        </div>
      )}
      <button ref={fabRef} type="button" className="fab" onClick={() => (open ? close() : setOpen(true))}
        aria-label={open ? tx("Close chat", "चैट बंद करें") : t("chat_title")} aria-expanded={open} aria-controls="chat-panel">
        <span aria-hidden="true">{open ? "✕" : "💬"}</span>
      </button>
    </>
  );
}

import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "./api";
import { useApp } from "./store";

interface Msg { role: "user" | "assistant"; content: string; mode?: string }

const SUGGEST = {
  en: ["Is it safe to jog now?", "Should my kids play outside?", "No purifier — what can I do?", "Best way to commute today?"],
  hi: ["Aaj bahar walk karna safe hai?", "क्या बच्चे बाहर खेल सकते हैं?", "प्यूरीफायर नहीं है, क्या करूँ?", "आज ऑफिस कैसे जाऊँ?"],
};

// Tiny, safe markdown: **bold** and "* " / "- " bullets → React elements (no innerHTML).
function inline(s: string) {
  return s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part);
}
export function Markdown({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) blocks.push(<ul key={blocks.length} style={{ margin: "4px 0", paddingLeft: 18 }}>{list.map((l, i) => <li key={i}>{inline(l)}</li>)}</ul>);
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

// Minimal typing for the Web Speech API (not in TS DOM lib everywhere).
type Recognition = { lang: string; interimResults: boolean; start(): void; stop(): void;
  onresult: (e: any) => void; onend: () => void; onerror: () => void };

export default function Chat() {
  const { t, lang, place, household } = useApp();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const recRef = useRef<Recognition | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);
  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const speak = (s: string) => {
    if (!("speechSynthesis" in window)) return;
    const u = new SpeechSynthesisUtterance(s.replace(/[*#_`]/g, ""));
    u.lang = lang === "hi" ? "hi-IN" : "en-IN";
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  };

  const send = async (content: string, viaVoice = false) => {
    const q = content.trim();
    if (!q || busy) return;
    const history = msgs.slice(-10).map(({ role, content }) => ({ role, content: content.slice(0, 2000) }));
    setMsgs((m) => [...m, { role: "user", content: q }]);
    setText("");
    setBusy(true);
    try {
      const r = await api.chat({ message: q.slice(0, 1000), history, lat: place?.lat, lon: place?.lon, place: place?.name, household, lang });
      setMsgs((m) => [...m, { role: "assistant", content: r.reply, mode: r.mode }]);
      if (viaVoice) speak(r.reply);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", content: `⚠️ ${(e as Error).message}` }]);
    } finally { setBusy(false); }
  };

  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  const toggleMic = () => {
    if (listening) { recRef.current?.stop(); return; }
    const rec: Recognition = new SR();
    rec.lang = lang === "hi" ? "hi-IN" : "en-IN";
    rec.interimResults = false;
    rec.onresult = (e) => { const said = e.results[0][0].transcript; send(said, true); };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    rec.start();
  };

  const onSubmit = (e: FormEvent) => { e.preventDefault(); send(text); };

  return (
    <>
      {open && (
        <div className="chat" role="dialog" aria-label={t("chat_title")}>
          <header>
            <img src="/logo.svg" alt="" />
            <div><b>{t("chat_title")}</b><div className="small" style={{ opacity: .85 }}>{place ? `📍 ${place.name}` : "AI air assistant"}</div></div>
            <button onClick={() => setOpen(false)} aria-label="Close chat">✕</button>
          </header>
          <div className="msgs" aria-live="polite">
            {msgs.length === 0 && (
              <div className="msg bot">👋 {lang === "hi" ? "नमस्ते! मैं आपके शहर की हवा के हिसाब से सलाह देता हूँ।" : "Hi! I give advice based on your city's air right now."}</div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`msg ${m.role === "user" ? "user" : "bot"}`} style={{ whiteSpace: m.role === "user" ? "pre-wrap" : "normal" }}>
                {m.role === "user" ? m.content : <Markdown text={m.content} />}
                {m.mode === "rules" && <div className="small muted" style={{ marginTop: 4 }}>⚙️ {t("rules_mode")}</div>}
              </div>
            ))}
            {busy && <div className="msg bot typing" aria-label="Typing"><span /><span /><span /></div>}
            <div ref={endRef} />
          </div>
          {msgs.length === 0 && (
            <div className="suggest">{SUGGEST[lang].map((s) => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}</div>
          )}
          <form onSubmit={onSubmit}>
            {SR && <button type="button" className={`icon-btn ${listening ? "live" : ""}`} onClick={toggleMic}
              aria-label={t("speak")} aria-pressed={listening}>🎤</button>}
            <label className="sr-only" htmlFor="chat-in">{t("chat_placeholder")}</label>
            <input id="chat-in" ref={inputRef} type="text" value={text} maxLength={1000} placeholder={t("chat_placeholder")} onChange={(e) => setText(e.target.value)} />
            <button className="btn small" type="submit" disabled={busy || !text.trim()} aria-label={t("send")}>➤</button>
          </form>
        </div>
      )}
      <button className="fab" onClick={() => setOpen((o) => !o)} aria-label={t("chat_title")} aria-expanded={open}>{open ? "✕" : "💬"}</button>
    </>
  );
}

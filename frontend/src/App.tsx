import { lazy, Suspense, useEffect, useState } from "react";
import Chat from "./Chat";
import ErrorBoundary from "./ErrorBoundary";
import { Sky } from "./components";
import type { Key } from "./i18n";
import { scrollBehavior } from "./motion";
import { useApp } from "./store";
import Today from "./pages/Today";

const Family = lazy(() => import("./pages/Family"));
const HomeAir = lazy(() => import("./pages/HomeAir"));
const Impact = lazy(() => import("./pages/Impact"));
const Community = lazy(() => import("./pages/Community"));

const TABS: { id: string; icon: string; key: Key }[] = [
  { id: "today", icon: "🌤️", key: "tab_today" },
  { id: "family", icon: "🛡️", key: "tab_family" },
  { id: "home", icon: "🏠", key: "tab_home" },
  { id: "impact", icon: "🌱", key: "tab_impact" },
  { id: "community", icon: "📣", key: "tab_community" },
];

/** The tab named in the URL hash, or "today". */
function readHashTab(): string {
  const h = window.location.hash.replace("#", "");
  return TABS.some((t) => t.id === h) ? h : "today";
}

/** Current tab, kept in the URL hash so the back button and shared links work. */
function useHashTab(): [string, (id: string) => void] {
  const [tab, setTab] = useState(readHashTab);
  useEffect(() => {
    const onHashChange = () => setTab(readHashTab());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  const go = (id: string) => {
    window.location.hash = id;
    window.scrollTo({ top: 0, behavior: scrollBehavior() });
  };
  return [tab, go];
}

const TAB_KEYS: Record<string, (i: number) => number> = {
  ArrowRight: (i) => i + 1, ArrowLeft: (i) => i - 1, Home: () => 0, End: () => TABS.length - 1,
};

export default function App() {
  const { t, tx, lang, setLang } = useApp();
  const [tab, go] = useHashTab();
  // Roving focus between tabs (WAI-ARIA tabs pattern).
  const onTabKey = (e: React.KeyboardEvent, i: number) => {
    const move = TAB_KEYS[e.key];
    if (!move) return;
    e.preventDefault();
    const id = TABS[(move(i) + TABS.length) % TABS.length].id;
    go(id);
    requestAnimationFrame(() => document.getElementById(`tab-${id}`)?.focus());
  };

  return (
    <>
      <Sky />
      <button type="button" className="skip" onClick={() => document.getElementById("panel")?.focus()}>
        {tx("Skip to main content", "मुख्य सामग्री पर जाएँ")}
      </button>
      <div className="shell">
        <header className="top">
          <a className="brand" href="#today" aria-label={tx("BreatheWise AI home", "BreatheWise AI होम")}>
            <img src="/logo-96.png" alt="" width={46} height={46} />
            <div>
              <h1 className="wordmark">
                <span className="w-light">Breathe</span><span className="w-bold">Wise</span> <span className="w-ai">AI</span>
              </h1>
              <small>{t("tagline")}</small>
            </div>
          </a>
          <div className="lang" role="group" aria-label={tx("Language", "भाषा")}>
            <button type="button" lang="en" aria-label="English" aria-pressed={lang === "en"} onClick={() => setLang("en")}>EN</button>
            <button type="button" lang="hi" aria-label="हिन्दी" aria-pressed={lang === "hi"} onClick={() => setLang("hi")}>हिं</button>
          </div>
        </header>
        <div className="tabs" role="tablist" aria-label={tx("Sections", "भाग")}>
          {TABS.map((x, i) => (
            <button key={x.id} type="button" id={`tab-${x.id}`} role="tab" aria-selected={tab === x.id} aria-controls="panel"
              tabIndex={tab === x.id ? 0 : -1} onClick={() => go(x.id)} onKeyDown={(e) => onTabKey(e, i)}>
              <span aria-hidden="true">{x.icon}</span>{t(x.key)}
            </button>
          ))}
        </div>
        <main id="panel" role="tabpanel" tabIndex={-1} aria-labelledby={`tab-${tab}`} key={tab}>
          <ErrorBoundary resetKey={tab}>
            <Suspense fallback={<div className="card skeleton" role="status" aria-label={t("loading")} style={{ height: 240, marginTop: 18 }} />}>
              {tab === "today" && <Today />}
              {tab === "family" && <Family />}
              {tab === "home" && <HomeAir />}
              {tab === "impact" && <Impact />}
              {tab === "community" && <Community />}
            </Suspense>
          </ErrorBoundary>
        </main>
        <footer className="foot">
          {t("disclaimer")}<br />
          © {new Date().getFullYear()} BreatheWise AI · {tx("Developed by", "विकासक:")}{" "}
          <a href="https://github.com/shivangsaxena1011" target="_blank" rel="noopener noreferrer"
            style={{ color: "inherit", textDecoration: "underline" }}>
            Shivang Saxena<span className="sr-only"> {tx("(opens in a new tab)", "(नए टैब में खुलेगा)")}</span>
          </a>
        </footer>
      </div>
      <Chat />
    </>
  );
}

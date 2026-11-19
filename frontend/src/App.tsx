import { lazy, Suspense, useEffect, useState } from "react";
import Chat from "./Chat";
import { Sky } from "./components";
import type { Key } from "./i18n";
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

function useHashTab(): [string, (id: string) => void] {
  const read = () => {
    const h = window.location.hash.replace("#", "");
    return TABS.some((t) => t.id === h) ? h : "today";
  };
  const [tab, setTab] = useState(read);
  useEffect(() => {
    const on = () => setTab(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return [tab, (id) => { window.location.hash = id; window.scrollTo({ top: 0, behavior: "smooth" }); }];
}

export default function App() {
  const { t, lang, setLang } = useApp();
  const [tab, go] = useHashTab();

  return (
    <>
      <Sky />
      <div className="shell">
        <header className="top">
          <a className="brand" href="#today" aria-label="BreatheWise AI home">
            <img src="/logo.svg" alt="" width={44} height={44} />
            <div><h1>Breathe<span>Wise</span> AI</h1><small>{t("tagline")}</small></div>
          </a>
          <div className="lang" role="group" aria-label="Language">
            <button aria-pressed={lang === "en"} onClick={() => setLang("en")}>EN</button>
            <button aria-pressed={lang === "hi"} onClick={() => setLang("hi")}>हिं</button>
          </div>
        </header>
        <nav className="tabs" role="tablist" aria-label="Sections">
          {TABS.map((x) => (
            <button key={x.id} role="tab" aria-selected={tab === x.id} onClick={() => go(x.id)}>
              <span aria-hidden="true">{x.icon}</span>{t(x.key)}
            </button>
          ))}
        </nav>
        <main role="tabpanel" key={tab}>
          <Suspense fallback={<div className="card skeleton" style={{ height: 240, marginTop: 18 }} />}>
            {tab === "today" && <Today />}
            {tab === "family" && <Family />}
            {tab === "home" && <HomeAir />}
            {tab === "impact" && <Impact />}
            {tab === "community" && <Community />}
          </Suspense>
        </main>
        <footer className="foot">{t("disclaimer")}<br />BreatheWise AI · PromptWars Challenge 6</footer>
      </div>
      <Chat />
    </>
  );
}

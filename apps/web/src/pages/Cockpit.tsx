// Cockpit shell — read-only port of JARVIS/app/main.jsx App, wired live.
import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Header } from "../components/Header";
import { Composer, ChatStream, buildItems } from "../components/Chat";
import { Rail } from "../components/Rail";
import { GraphPage } from "../components/GraphPage";
import { DashboardPage } from "../components/DashboardPage";
import { BullseyePage } from "../components/BullseyePage";
import { BrainsPage } from "../components/Pages";
import { useBrains, type DisplayBrain } from "../hooks/useBrains";
import { useStreamChat } from "../hooks/useStreamChat";

type Route = "chat" | "dashboard" | "bullseye" | "graph" | "brains";
const ROUTES: Route[] = ["chat", "dashboard", "bullseye", "graph", "brains"];

function routeFromPath(pathname: string): Route {
  const tail = pathname.replace(/^\/app\/?/, "").split("/")[0];
  return (ROUTES as string[]).includes(tail) ? (tail as Route) : "chat";
}

export function Cockpit() {
  const location = useLocation();
  const navigate = useNavigate();
  const route: Route = routeFromPath(location.pathname);

  // Normalize bare /app and migrate legacy #hash routes once on mount.
  useEffect(() => {
    const hash = location.hash.replace(/^#/, "");
    if (hash && (ROUTES as string[]).includes(hash)) {
      navigate(`/app/${hash}`, { replace: true });
      return;
    }
    if (location.pathname === "/app" || location.pathname === "/app/") {
      navigate("/app/chat", { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Brain selection — live
  const { brains } = useBrains();
  const [brainId, setBrainId] = useState<string | null>(null);
  useEffect(() => {
    if (brains.length === 0) {
      setBrainId(null);
      return;
    }
    if (!brainId || !brains.find((b) => b.id === brainId)) {
      setBrainId(brains[0].id);
    }
  }, [brains, brainId]);
  const brain: DisplayBrain | null =
    brains.find((b) => b.id === brainId) ?? brains[0] ?? null;

  // Live streaming chat
  const { messages, isStreaming, toolActivity, threadId, sendMessage } =
    useStreamChat(brain?.id);

  const handleWikilinkClick = useCallback(
    (target: string) => {
      navigate("/app/brains", { state: { brainId: brain?.id, pagePath: target } });
    },
    [navigate, brain],
  );

  // URL routing — driven by react-router
  function setRoute(r: string) {
    navigate(`/app/${r}`);
  }

  const items = buildItems(messages, toolActivity, isStreaming);
  const shortThread = threadId ? threadId.slice(0, 4) + "·" + threadId.slice(4, 8) : "—";

  return (
    <div className="app">
      <Header
        route={route}
        setRoute={setRoute}
        brain={brain}
        brains={brains}
        setBrain={(b) => setBrainId(b.id)}
      />

      <main className="app-main">
        {route === "chat" && (
          <div className="chat-page page">
            <div className="chat-col">
              <div className="thread-bar">
                <div className="left">
                  <span className="eyebrow">THREAD</span>
                  <h2>{brain ? brain.title : "—"}</h2>
                  <span className="id">ID {shortThread}</span>
                </div>
                <div className="right">
                  <span className="chip chip-accent" style={{ marginRight: 8 }}>
                    <span className="dot dot-pulse"></span>
                    {isStreaming ? "STREAMING" : "IDLE"}
                  </span>
                  <button className="icon-btn" title="Search">
                    <svg
                      viewBox="0 0 16 16"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.4"
                    >
                      <circle cx="7" cy="7" r="4.5" />
                      <line x1="10.5" y1="10.5" x2="14" y2="14" />
                    </svg>
                  </button>
                  <button className="icon-btn" title="Clear" onClick={() => window.location.reload()}>
                    <svg
                      viewBox="0 0 16 16"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.4"
                    >
                      <path d="M3 4h10M6 4V2.5h4V4M5 4l1 9h4l1-9" />
                    </svg>
                  </button>
                </div>
              </div>

              <ChatStream
                items={items}
                streaming={isStreaming}
                onWikilinkClick={handleWikilinkClick}
              />

              <Composer onSend={(t, opts) => sendMessage(t, opts)} streaming={isStreaming} />
            </div>

            <Rail brain={brain} toolActivity={toolActivity} />
          </div>
        )}

        {route === "dashboard" && (
          <div className="page">
            <DashboardPage />
          </div>
        )}
        {route === "bullseye" && (
          <div className="page">
            <BullseyePage />
          </div>
        )}
        {route === "graph" && (
          <div className="page">
            <GraphPage brain={brain} />
          </div>
        )}
        {route === "brains" && <BrainsPage brains={brains} />}
      </main>
    </div>
  );
}

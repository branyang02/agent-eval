import {
  Bot,
  CheckCircle2,
  CircleAlert,
  CircleDot,
  RefreshCw,
} from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";

type Role = "simulated_user" | "agent";

type TranscriptEvent = {
  id: number;
  role: Role;
  turn: number;
  message: string;
  timestamp: number;
};

type Transcript = {
  events: TranscriptEvent[];
};

type ConnectionState = "connecting" | "live" | "error";

const EXIT_MESSAGE = "You may exit now.";

function roleLabel(role: Role): string {
  return role === "simulated_user" ? "User" : "Agent";
}

function renderMessage(message: string) {
  const parts = message.split(/```/g);

  return parts.map((part, index) => {
    const isCode = index % 2 === 1;
    if (isCode) {
      const lines = part.replace(/^\n/, "").replace(/\n$/, "").split("\n");
      const firstLine = lines[0] ?? "";
      const hasLanguage = firstLine.trim() !== "" && !firstLine.includes(" ");
      const code = hasLanguage ? lines.slice(1).join("\n") : lines.join("\n");

      return (
        <pre className="code-block" key={`code-${index}`}>
          <code>{code}</code>
        </pre>
      );
    }

    return part
      .split(/\n{2,}/g)
      .filter((paragraph) => paragraph.trim().length > 0)
      .map((paragraph, paragraphIndex) => (
        <p key={`text-${index}-${paragraphIndex}`}>{paragraph}</p>
      ));
  });
}

function App() {
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("connecting");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [autoRefresh, setAutoRefresh] = useState(true);

  const refreshTranscript = useCallback(async () => {
    try {
      const response = await fetch("/transcript", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const nextTranscript = (await response.json()) as Transcript;
      setTranscript(nextTranscript);
      setConnectionState("live");
      setErrorMessage("");
    } catch (error) {
      setConnectionState("error");
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  }, []);

  useEffect(() => {
    void refreshTranscript();
  }, [refreshTranscript]);

  useEffect(() => {
    if (!autoRefresh) {
      return;
    }
    const interval = window.setInterval(() => {
      void refreshTranscript();
    }, 700);
    return () => window.clearInterval(interval);
  }, [autoRefresh, refreshTranscript]);

  const simulatedUserMessages =
    transcript?.events.filter((event) => event.role === "simulated_user").length ?? 0;
  const agentReplies =
    transcript?.events.filter((event) => event.role === "agent").length ?? 0;
  const messageCount = transcript?.events.length ?? 0;
  const exitSeen = useMemo(
    () =>
      Boolean(
        transcript?.events.some(
          (event) =>
            event.role === "simulated_user" &&
            event.message === EXIT_MESSAGE,
        ),
      ),
    [transcript],
  );

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Conversation Viewer</h1>
          <div className="conversation-meta">
            <span>{simulatedUserMessages} user messages</span>
            <span>{agentReplies} agent replies</span>
            <span>{messageCount} events</span>
          </div>
        </div>
        <div className="toolbar">
          <span className={`status-pill status-${connectionState}`}>
            {connectionState === "live" ? <CircleDot /> : null}
            {connectionState === "connecting" ? <RefreshCw /> : null}
            {connectionState === "error" ? <CircleAlert /> : null}
            {connectionState}
          </span>
          <button
            className="icon-button"
            type="button"
            aria-label="Refresh transcript"
            title="Refresh transcript"
            onClick={() => void refreshTranscript()}
          >
            <RefreshCw />
          </button>
          <button
            className={`toggle-button ${autoRefresh ? "is-on" : ""}`}
            type="button"
            onClick={() => setAutoRefresh((value) => !value)}
          >
            Auto
          </button>
        </div>
      </header>

      {errorMessage ? (
        <div className="error-banner">
          <CircleAlert />
          <span>{errorMessage}</span>
        </div>
      ) : null}

      <section className="chat-pane" aria-label="Conversation transcript">
        {transcript?.events.length ? (
          transcript.events.map((event, index) => {
            const isUser = event.role === "simulated_user";
            return (
              <article
                className={`message-row ${isUser ? "message-user" : "message-agent"}`}
                key={`${event.role}-${event.id}-${index}`}
              >
                {!isUser ? (
                  <div className="avatar" aria-hidden="true">
                    <Bot />
                  </div>
                ) : null}
                <div className="message-body">
                  <div className="message-meta">
                    <strong>{roleLabel(event.role)}</strong>
                    <span>event {event.id}</span>
                    {event.message === EXIT_MESSAGE ? (
                      <span className="exit-chip">
                        <CheckCircle2 />
                        exit
                      </span>
                    ) : null}
                  </div>
                  <div className="message-content">{renderMessage(event.message)}</div>
                </div>
              </article>
            );
          })
        ) : (
          <div className="empty-state">
            <CircleDot />
            <p>Waiting for transcript events</p>
          </div>
        )}
      </section>

      <footer className="composer-bar" aria-label="Conversation state">
        <span>{exitSeen ? "Exit message seen" : "Running"}</span>
        <span>{`${simulatedUserMessages} user messages, ${agentReplies} agent replies`}</span>
      </footer>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

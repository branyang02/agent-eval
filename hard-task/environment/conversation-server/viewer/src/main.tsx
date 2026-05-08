import {
  Bot,
  CheckCircle2,
  CircleAlert,
  CircleDot,
  RefreshCw,
} from "lucide-react";
import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import css from "highlight.js/lib/languages/css";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import markdown from "highlight.js/lib/languages/markdown";
import python from "highlight.js/lib/languages/python";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
import yaml from "highlight.js/lib/languages/yaml";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { createRoot } from "react-dom/client";
import remarkGfm from "remark-gfm";

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
const UPDATE_RETRY_MS = 1000;
const REMARK_PLUGINS = [remarkGfm];
const LANGUAGE_ALIASES: Record<string, string> = {
  html: "xml",
  js: "javascript",
  md: "markdown",
  py: "python",
  shell: "bash",
  sh: "bash",
  ts: "typescript",
  yml: "yaml",
  zsh: "bash",
};

hljs.registerLanguage("bash", bash);
hljs.registerLanguage("css", css);
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("json", json);
hljs.registerLanguage("markdown", markdown);
hljs.registerLanguage("python", python);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("xml", xml);
hljs.registerLanguage("yaml", yaml);

function roleLabel(role: Role): string {
  return role === "simulated_user" ? "User" : "Agent";
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function maxEventId(events: TranscriptEvent[]): number {
  return events.reduce((maxId, event) => Math.max(maxId, event.id), 0);
}

function mergeTranscript(
  currentTranscript: Transcript | null,
  events: TranscriptEvent[],
): Transcript {
  const byId = new Map<number, TranscriptEvent>();
  for (const event of currentTranscript?.events ?? []) {
    byId.set(event.id, event);
  }
  for (const event of events) {
    byId.set(event.id, event);
  }
  return {
    events: Array.from(byId.values()).sort((left, right) => left.id - right.id),
  };
}

function normalizeLanguage(language: string): string {
  const normalized = language.trim().toLowerCase();
  return LANGUAGE_ALIASES[normalized] ?? normalized;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function highlightedCode(code: string, language: string | null): string {
  try {
    if (language && hljs.getLanguage(language)) {
      return hljs.highlight(code, { language, ignoreIllegals: true }).value;
    }
    return hljs.highlightAuto(code).value;
  } catch {
    return escapeHtml(code);
  }
}

type CodeElementProps = {
  children?: React.ReactNode;
  className?: string;
};

function CodeBlock({
  children,
  className,
}: CodeElementProps): React.ReactElement {
  const match = /(?:^|\s)language-([^\s]+)/.exec(className ?? "");
  const language = match ? normalizeLanguage(match[1]) : null;
  const code = String(children ?? "").replace(/\n$/, "");
  const html = highlightedCode(code, language);

  return (
    <div className="code-frame">
      {language ? <div className="code-language">{language}</div> : null}
      <pre className="code-block">
        <code dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    </div>
  );
}

const markdownComponents: Components = {
  code({ children, className, node: _node, ...props }) {
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  },
  pre({ children }) {
    const child = React.Children.toArray(children)[0];
    if (React.isValidElement<CodeElementProps>(child)) {
      return <CodeBlock {...child.props} />;
    }

    return <pre>{children}</pre>;
  },
};

function renderMessage(message: string) {
  return (
    <ReactMarkdown
      components={markdownComponents}
      remarkPlugins={REMARK_PLUGINS}
    >
      {message}
    </ReactMarkdown>
  );
}

function App() {
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("connecting");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const lastEventIdRef = useRef(0);

  const refreshTranscript = useCallback(async () => {
    try {
      const response = await fetch("/transcript", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const nextTranscript = (await response.json()) as Transcript;
      lastEventIdRef.current = maxEventId(nextTranscript.events);
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

    const controller = new AbortController();
    let stopped = false;

    async function pollForUpdates() {
      while (!stopped) {
        try {
          const response = await fetch(
            `/transcript/updates?after_id=${lastEventIdRef.current}`,
            {
              cache: "no-store",
              signal: controller.signal,
            },
          );
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }

          const update = (await response.json()) as Transcript;
          if (stopped) {
            return;
          }

          if (update.events.length > 0) {
            lastEventIdRef.current = Math.max(
              lastEventIdRef.current,
              maxEventId(update.events),
            );
            setTranscript((currentTranscript) =>
              mergeTranscript(currentTranscript, update.events),
            );
          }
          setConnectionState("live");
          setErrorMessage("");
        } catch (error) {
          if (stopped || controller.signal.aborted) {
            return;
          }
          setConnectionState("error");
          setErrorMessage(error instanceof Error ? error.message : String(error));
          await sleep(UPDATE_RETRY_MS);
        }
      }
    }

    void pollForUpdates();
    return () => {
      stopped = true;
      controller.abort();
    };
  }, [autoRefresh]);

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

import { useState } from "react";
import { EvidenceItem, streamChat } from "../api/client";

interface Message {
  role: "user" | "assistant";
  content: string;
  evidence?: EvidenceItem[];
  toolCalls?: number;
}

interface Props {
  projectId: string;
  onEvidenceClick: (item: EvidenceItem) => void;
}

const SUGGESTIONS = [
  "Give me an architecture overview of this project.",
  "What are the main entry points?",
  "How are modules connected?",
  "Show me the API routes.",
];

export default function ChatPanel({ projectId, onEvidenceClick }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [toolStatus, setToolStatus] = useState<string | null>(null);

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return;
    const userMsg: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setToolStatus(null);

    let assistant = "";
    let evidence: EvidenceItem[] = [];
    let toolCalls = 0;

    try {
      await streamChat(projectId, text, sessionId, (event) => {
        if (event.type === "session" && event.session_id) {
          setSessionId(event.session_id as string);
        }
        if (event.type === "tool_start") {
          setToolStatus(`Using ${event.name as string}…`);
        }
        if (event.type === "tool_end") {
          setToolStatus(null);
        }
        if (event.type === "evidence" && Array.isArray(event.items)) {
          evidence = event.items as EvidenceItem[];
        }
        if (event.type === "meta" && typeof event.tool_calls === "number") {
          toolCalls = event.tool_calls;
        }
        if (event.type === "token" && typeof event.content === "string") {
          assistant += event.content;
          setMessages((prev) => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last?.role === "assistant") {
              copy[copy.length - 1] = { ...last, content: assistant, evidence, toolCalls };
              return copy;
            }
            return [...copy, { role: "assistant", content: assistant, evidence, toolCalls }];
          });
        }
        if (event.type === "error") {
          assistant = event.content as string;
        }
      });

      if (!assistant) {
        setMessages((prev) => [...prev, { role: "assistant", content: "No response received.", evidence, toolCalls }]);
      } else {
        setMessages((prev) => {
          const copy = [...prev];
          const idx = copy.findIndex((m, i) => m.role === "assistant" && i === copy.length - 1);
          if (idx >= 0) copy[idx] = { role: "assistant", content: assistant, evidence, toolCalls };
          else copy.push({ role: "assistant", content: assistant, evidence, toolCalls });
          return copy;
        });
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: err instanceof Error ? err.message : "Chat failed." },
      ]);
    } finally {
      setLoading(false);
      setToolStatus(null);
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <h3>Ask the codebase</h3>
            <p>Agent uses graph tools first, then reads small code snippets. Every answer should cite evidence.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => sendMessage(s)} disabled={loading}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-message ${m.role}`}>
            <div className="chat-bubble">{m.content}</div>
            {m.role === "assistant" && m.evidence && m.evidence.length > 0 && (
              <div className="evidence-panel">
                <div className="evidence-title">Evidence ({m.toolCalls ?? 0} tool calls)</div>
                {m.evidence.map((e, j) => (
                  <button key={j} className="evidence-item" onClick={() => onEvidenceClick(e)}>
                    {e.label} — {e.path}{e.line ? `:${e.line}` : ""}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && <div className="chat-status">{toolStatus || "Thinking…"}</div>}
      </div>
      <form
        className="chat-input-row"
        onSubmit={(e) => {
          e.preventDefault();
          sendMessage(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="How does this project work?"
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>Send</button>
      </form>
    </div>
  );
}

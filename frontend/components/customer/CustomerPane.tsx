"use client";

// Walking skeleton of the customer phone: start session, keypad text, transcript, end call, test audio.
// Drag-to-scan, mascot states, captions and basket come in lane C; voice in lane V.
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { playWavUrl } from "@/lib/audio";
import { DEMO_QR_TOKEN, USE_MOCKS } from "@/lib/config";
import { getDeviceId } from "@/lib/device";
import { connectCustomer, type Connection } from "@/lib/ws";
import { MOCK_SESSION_ID } from "@/mocks/demoSession";
import type { AgentState, CustomerInbound, CustomerOutbound, SessionState } from "@/lib/types";

interface Line {
  speaker: "customer" | "hermion";
  text: string;
}

export function CustomerPane() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [state, setState] = useState<SessionState | null>(null);
  const [agent, setAgent] = useState<AgentState>("idle");
  const [lines, setLines] = useState<Line[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const conn = useRef<Connection<CustomerInbound> | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    const c = connectCustomer(sessionId, (e: CustomerOutbound) => {
      if (e.type === "state") setState(e.state);
      else if (e.type === "agent_state") setAgent(e.state);
      else if (e.type === "transcript") setLines((l) => [...l, { speaker: e.speaker, text: e.text }]);
      else if (e.type === "error") setError(e.message);
    });
    conn.current = c;
    return () => c.close();
  }, [sessionId]);

  async function start() {
    setError(null);
    setLines([]);
    try {
      const id = USE_MOCKS
        ? MOCK_SESSION_ID
        : (await api.createSession({ qr_token: DEMO_QR_TOKEN, device_id: getDeviceId() })).session_id;
      setSessionId(id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function end() {
    if (sessionId && !USE_MOCKS) await api.exitSession(sessionId).catch(() => {});
    conn.current?.close();
    setSessionId(null);
    setState(null);
    setAgent("idle");
  }

  function sendText() {
    const text = draft.trim();
    if (!text || !conn.current) return;
    conn.current.send({ type: "text_input", text });
    setDraft("");
  }

  return (
    <section className="flex h-full items-center justify-center bg-indigo-100 p-4" data-testid="customer-pane">
      <div className="flex h-[640px] w-[320px] flex-col rounded-[40px] border-8 border-slate-900 bg-gradient-to-b from-sky-100 to-violet-200 p-4 shadow-xl">
        <div className="mx-auto mb-3 h-6 w-24 rounded-full bg-slate-900" />
        {!sessionId ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
            <p className="text-slate-700">Scan the shop&apos;s QR to start</p>
            <button
              onClick={start}
              className="rounded-full bg-slate-900 px-5 py-2 text-white"
              data-testid="start-session"
            >
              Start session
            </button>
          </div>
        ) : (
          <>
            <p className="text-center text-xs text-slate-600" data-testid="session-status">
              Hermion · {state ?? "connecting"} · <span data-testid="agent-state">{agent}</span>
            </p>
            <ol className="my-3 flex-1 space-y-2 overflow-y-auto text-sm" data-testid="customer-transcript">
              {lines.map((l, i) => (
                <li
                  key={i}
                  className={`rounded-xl px-3 py-2 ${l.speaker === "customer" ? "ml-8 bg-white" : "mr-8 bg-slate-900 text-white"}`}
                >
                  {l.text}
                </li>
              ))}
            </ol>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                sendText();
              }}
            >
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Type to Hermion…"
                className="min-w-0 flex-1 rounded-full bg-white px-3 py-2 text-sm outline-none"
                data-testid="keypad-input"
              />
              <button className="rounded-full bg-slate-900 px-3 text-sm text-white" data-testid="keypad-send">
                Send
              </button>
            </form>
            <button
              onClick={end}
              className="mx-auto mt-3 h-12 w-12 rounded-full bg-red-600 text-white"
              aria-label="End call"
              data-testid="end-call"
            >
              ✕
            </button>
          </>
        )}
        {error && <p className="mt-2 text-center text-xs text-red-700">{error}</p>}
        <button
          onClick={() => playWavUrl(api.ttsTestUrl("te-IN")).catch((e: Error) => setError(e.message))}
          className="mt-2 text-xs text-slate-500 underline"
          data-testid="tts-test"
        >
          Play TTS test clip
        </button>
      </div>
    </section>
  );
}

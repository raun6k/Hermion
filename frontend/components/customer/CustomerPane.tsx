"use client";

// Customer pane: a voice call in a phone frame (docs/frontend.md). Scan QR reveals the draggable scanner,
// then the call: captions, basket chip, mute / end / More. All network access goes through lib/api and
// lib/ws; this pane shares no state with the merchant pane. Voice arrives with the Stage 3 pipeline; until
// then the More sheet's text box is the input.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { TtsPlayer } from "@/lib/audio";
import { getDeviceId } from "@/lib/device";
import { connectCustomer, type Connection } from "@/lib/ws";
import { TERMINAL_STATES } from "@/lib/types";
import type { AgentState, BasketLinePublic, CustomerInbound, CustomerOutbound, SessionState } from "@/lib/types";
import { BasketChip, BasketSheet } from "./BasketSheet";
import { CallControls } from "./CallControls";
import { Caption, type CaptionLine } from "./Caption";
import { Mascot } from "./Mascot";
import { LanguageChoice } from "./LanguageChoice";
import { MoreSheet } from "./MoreSheet";
import { PhoneFrame } from "./PhoneFrame";
import { Scanner } from "./Scanner";

interface Line {
  speaker: "customer" | "hermion";
  text: string;
}

const WAITING: SessionState[] = ["pending_merchant", "briefing"];

export function CustomerPane() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [languages, setLanguages] = useState<string[] | null>(null);
  const [languageReady, setLanguageReady] = useState(false);
  const [languagePin, setLanguagePin] = useState<string | null>(null);
  const [languagePending, setLanguagePending] = useState(false);
  const [languageError, setLanguageError] = useState<string | null>(null);
  const [languageLoadAttempt, setLanguageLoadAttempt] = useState(0);
  const [state, setState] = useState<SessionState | null>(null);
  const [stateMessage, setStateMessage] = useState<string | null>(null);
  const [agent, setAgent] = useState<AgentState>("idle");
  const [transcript, setTranscript] = useState<Line[]>([]);
  const [caption, setCaption] = useState<CaptionLine | null>(null);
  const [basket, setBasket] = useState<{ lines: BasketLinePublic[]; total: string }>({ lines: [], total: "0" });
  const [muted, setMuted] = useState(false);
  const [more, setMore] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const conn = useRef<Connection<CustomerInbound> | null>(null);
  const player = useRef<TtsPlayer | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    api.session(sessionId).then((info) => {
      if (!active) return;
      setLanguages(info.languages);
      if (info.state !== "intro" || info.language) setLanguageReady(true);
      if (info.language) setLanguagePin(info.language);
      setLanguageError(null);
    }).catch(() => { if (active) setLanguageError("Could not load languages. Please try again."); });
    return () => { active = false; };
  }, [sessionId, languageLoadAttempt]);

  useEffect(() => {
    if (!sessionId) return;
    player.current ??= new TtsPlayer();
    const c = connectCustomer(
      sessionId,
      (e: CustomerOutbound) => {
        if (e.type === "state") {
          setState(e.state);
          setStateMessage(e.message);
          if (e.state !== "negotiating" && e.state !== "discovery") {
            setSheet(false);
            setMore(false);
          }
        } else if (e.type === "language_selected") {
          setLanguagePin(e.code);
          setLanguageReady(true);
          setLanguagePending(false);
          setLanguageError(null);
        } else if (e.type === "agent_state") setAgent(e.state);
        else if (e.type === "transcript") setTranscript((t) => [...t, { speaker: e.speaker, text: e.text }]);
        else if (e.type === "caption") setCaption({ speaker: e.speaker, product_name: e.product_name, amount: e.amount });
        else if (e.type === "basket") setBasket({ lines: e.lines, total: e.total });
        else if (e.type === "tts_stop") player.current?.stop();
        else if (e.type === "error") {
          setLanguagePending(false);
          if (e.code === "UNSUPPORTED_LANGUAGE" || e.code === "LANGUAGE_REQUIRED") setLanguageError(e.message);
          else setError(e.message);
        }
      },
      { onBinary: (chunk) => player.current?.enqueue(chunk) },
    );
    conn.current = c;
    return () => {
      c.close();
      player.current?.stop();
    };
  }, [sessionId]);

  const reset = useCallback(() => {
    setSessionId(null);
    setScanning(false);
    setLanguages(null);
    setLanguageReady(false);
    setLanguagePin(null);
    setLanguagePending(false);
    setLanguageError(null);
    setState(null);
    setStateMessage(null);
    setAgent("idle");
    setTranscript([]);
    setCaption(null);
    setBasket({ lines: [], total: "0" });
    setSheet(false);
    setMore(false);
    setMuted(false);
    setConfirmError(null);
  }, []);

  async function scan(qrToken: string) {
    setError(null);
    try {
      const { session_id } = await api.createSession({ qr_token: qrToken, device_id: getDeviceId() });
      reset();
      setSessionId(session_id); // the scanner disappears and stays away for the whole session
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the session");
    }
  }

  async function endCall() {
    const id = sessionId;
    reset();
    if (id) await api.exitSession(id).catch(() => {});
  }

  async function confirmAndSend() {
    if (!sessionId) return;
    setBusy(true);
    setConfirmError(null);
    try {
      await api.confirm(sessionId);
      setSheet(false);
    } catch (e) {
      setConfirmError(e instanceof ApiError ? e.message : "Could not send the basket");
    } finally {
      setBusy(false);
    }
  }

  const terminal = state !== null && TERMINAL_STATES.includes(state);
  const inCall = sessionId !== null && !terminal;
  const waiting = state !== null && WAITING.includes(state);
  const inPerson = state === "in_person";
  const choosingLanguage = inCall && state === "intro" && !languageReady;
  const canType = inCall && state !== "intro" && !waiting && !inPerson;
  const lastLine = transcript.length ? transcript[transcript.length - 1] : null;
  const mascot: AgentState = state === "accepted" ? "happy" : waiting ? "thinking" : agent;
  const card = "mx-6 rounded-2xl bg-white px-4 py-3 text-center text-sm font-medium text-blue-950 shadow";

  return (
    <section className="relative flex h-full items-center justify-center bg-black p-4" data-testid="customer-pane">
      <PhoneFrame
        status={
          sessionId ? (
            <span data-testid="session-status">
              Hermion · {state ?? "connecting"} · <span data-testid="agent-state">{agent}</span>
            </span>
          ) : null
        }
        overlay={!sessionId && scanning ? <Scanner onScan={scan} onCancel={() => setScanning(false)} /> : null}
      >
        {!sessionId ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 px-8 text-center" data-testid="scan-prompt">
            <Mascot state="idle" />
            <p className="text-lg font-semibold">Bargain with Hermion</p>
            {scanning ? (
              <p className="text-sm text-white/70">Drag the scanner onto the shop&apos;s QR code.</p>
            ) : (
              <>
                <p className="text-sm text-white/70">Scan the shop&apos;s QR code to start a call.</p>
                <button onClick={() => setScanning(true)} className="rounded-full bg-pink-300 px-6 py-2.5 text-sm font-semibold text-blue-950 shadow-lg" data-testid="scan-qr">
                  Scan QR
                </button>
              </>
            )}
            {error && <p className="max-w-60 rounded-lg bg-white/10 px-3 py-2 text-xs text-pink-200" role="alert" data-testid="customer-error">{error}</p>}
          </div>
        ) : choosingLanguage ? (
          <LanguageChoice
            languages={languages}
            pending={languagePending}
            error={languageError}
            onChoose={(code) => {
              setLanguagePending(true);
              setLanguageError(null);
              conn.current?.send({ type: "select_language", code });
            }}
            onCancel={endCall}
            onRetry={() => setLanguageLoadAttempt((n) => n + 1)}
          />
        ) : (
          <>
            {basket.lines.length > 0 && inCall && (
              <BasketChip
                count={basket.lines.length}
                total={basket.total}
                onClick={() => {
                  setMore(false);
                  setSheet(true);
                }}
              />
            )}
            <div className="flex flex-1 flex-col justify-center">
              <Mascot state={mascot} />
              <Caption caption={caption} line={lastLine} />
              {waiting && (
                <p className={card} data-testid="waiting">
                  {stateMessage ?? "The shop is reviewing your basket…"}
                </p>
              )}
              {inPerson && (
                <p className={card} data-testid="in-person-note">
                  {stateMessage ?? "The shopkeeper is coming to you"}
                </p>
              )}
              {terminal && (
                <div className="mx-6 space-y-3 rounded-2xl bg-white p-4 text-center text-blue-950 shadow" data-testid="result" data-state={state}>
                  <p className="text-sm font-semibold">
                    {state === "accepted" ? "Deal confirmed" : state === "declined" ? "Not this time" : "Call ended"}
                  </p>
                  {stateMessage && <p className="text-sm text-slate-600">{stateMessage}</p>}
                  {basket.lines.length > 0 && state === "accepted" && (
                    <ul className="text-sm text-slate-700">
                      {basket.lines.map((l) => (
                        <li key={l.product_id}>{l.product_name} · ₹{Number(l.line_total).toLocaleString("en-IN")}</li>
                      ))}
                    </ul>
                  )}
                  <button onClick={reset} className="rounded-full bg-blue-900 px-5 py-2 text-sm text-white" data-testid="done">Done</button>
                </div>
              )}
            </div>
            {inCall && (
              <CallControls
                muted={muted}
                moreOpen={more}
                onMute={() => {
                  conn.current?.send({ type: "mute", muted: !muted });
                  setMuted(!muted);
                }}
                onEnd={endCall}
                onMore={() => setMore((m) => !m)}
              />
            )}
            {more && inCall && (
              <MoreSheet
                sessionId={sessionId}
                conversation={transcript}
                basketCount={basket.lines.length}
                canType={canType}
                pinnedLanguage={languagePin}
                onViewBasket={() => {
                  setMore(false);
                  setSheet(true);
                }}
                onSend={(text) => conn.current?.send({ type: "text_input", text })}
                onLanguage={(code) => {
                  setLanguagePin(code);
                  conn.current?.send({ type: "language", code });
                }}
                onClose={() => setMore(false)}
              />
            )}
            {sheet && inCall && (
              <BasketSheet lines={basket.lines} total={basket.total} busy={busy} error={confirmError} onConfirm={confirmAndSend} onClose={() => setSheet(false)} />
            )}
          </>
        )}
      </PhoneFrame>

      {/* Full transcript for assistive tech and tests. */}
      <ol className="sr-only" data-testid="customer-transcript">
        {transcript.map((l, i) => (
          <li key={i}>{l.speaker}: {l.text}</li>
        ))}
      </ol>
    </section>
  );
}

"use client";

// Customer pane: a phone (docs/frontend.md). Scan a shop's QR -> the shop's home page (Talk to Hermion, this
// device's baskets with their status, the shop page) -> the call: captions, basket pill, mute / end / More.
// Sending the basket returns to the home page; talking to Hermion again takes a waiting basket back. All network access goes through lib/api and
// lib/ws; this pane shares no state with the merchant pane. Voice runs through the customer socket;
// the More sheet retains a text input for integration tests.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { startMicCapture, TtsPlayer, type MicCapture } from "@/lib/audio";
import { getDeviceId } from "@/lib/device";
import { rupees } from "@/lib/format";
import { loadUiLanguage, pickUiLanguage, saveUiLanguage, translate, type TextKey } from "@/lib/i18n";
import { connectCustomer, type Connection } from "@/lib/ws";
import { TERMINAL_STATES } from "@/lib/types";
import type { AgentState, BasketLinePublic, CustomerInbound, CustomerOutbound, MerchantChoice, SessionState, VisitPublic } from "@/lib/types";
import { BasketSheet } from "./BasketSheet";
import { CallControls } from "./CallControls";
import { Caption, TranscriptSheet, type CaptionLine, type SpokenLine } from "./Caption";
import { ShopHome } from "./ShopHome";
import { ShopPage } from "./ShopPage";
import { Mascot } from "./Mascot";
import { LanguageButton, LanguageWindow } from "./LanguageMenu";
import { MoreSheet } from "./MoreSheet";
import { PhoneFrame } from "./PhoneFrame";
import { CameraView } from "./CameraView";
import { ScanStrip } from "./ScanStrip";

type Line = SpokenLine;
const clock = () => new Date().toTimeString().slice(0, 5);

const AGENT_TEXT: Record<AgentState, TextKey> = {
  idle: "agentIdle",
  listening: "agentListening",
  thinking: "agentThinking",
  speaking: "agentSpeaking",
  negotiating: "agentThinking",
  happy: "agentHappy",
};

export function CustomerPane() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [view, setView] = useState<"home" | "call">("home"); // with a session: the shop's home page or the call
  const [live, setLive] = useState(false); // customer socket open (from the first Talk to Hermion)
  const [qr, setQr] = useState<string | null>(null);
  const [visits, setVisits] = useState<VisitPublic[]>([]);
  const wantsRejoin = useRef(false); // call rejoin once the socket has said which state we are in
  const [scannerOpen, setScannerOpen] = useState(false);
  const [shops, setShops] = useState<MerchantChoice[]>([]);
  const [name, setName] = useState("");
  const [scale, setScale] = useState(1);
  const pane = useRef<HTMLDivElement>(null);
  // Screen text language. Spoken language is never chosen: Hermion follows whatever the customer speaks.
  const [shopLanguages, setShopLanguages] = useState<string[]>([]);
  const [uiLang, setUiLang] = useState("en-IN");
  const [langOpen, setLangOpen] = useState(false);
  const [state, setState] = useState<SessionState | null>(null);
  const [agent, setAgent] = useState<AgentState>("idle");
  const [transcript, setTranscript] = useState<Line[]>([]);
  const [caption, setCaption] = useState<CaptionLine | null>(null);
  const [log, setLog] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [bump, setBump] = useState(0);
  const [shopInfo, setShopInfo] = useState<{ name: string; description: string } | null>(null);
  const basketCount = useRef(0);
  const [basket, setBasket] = useState<{ lines: BasketLinePublic[]; total: string }>({ lines: [], total: "0" });
  const [muted, setMuted] = useState(false);
  const [more, setMore] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const conn = useRef<Connection<CustomerInbound> | null>(null);
  const player = useRef<TtsPlayer | null>(null);
  const mic = useRef<MicCapture | null>(null);
  const allowAudio = useRef(false);
  const uiLangRef = useRef(uiLang);
  useEffect(() => { uiLangRef.current = uiLang; }, [uiLang]);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const t = useCallback((key: TextKey) => translate(uiLang, key), [uiLang]);

  // The phone fills the customer pane; opening the scanner lets the scan strip take its own room.
  useEffect(() => {
    const el = pane.current;
    if (!el) return;
    const fit = () => setScale(Math.max(0.3, Math.min(2, el.clientHeight / 660, el.clientWidth / 330)));
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [sessionId]);

  useEffect(() => {
    api.merchants().then(setShops).catch(() => {});
  }, []);

  useEffect(() => {
    let active = true;
    api.shop().then((shop) => {
      if (!active) return;
      setShopLanguages(shop.languages);
      setUiLang(pickUiLanguage(shop.languages, loadUiLanguage()));
    }).catch(() => {});
    return () => { active = false; };
  }, []);

  function chooseUiLanguage(code: string) {
    setUiLang(code);
    saveUiLanguage(code);
    setLangOpen(false);
    conn.current?.send({ type: "ui_language", code });
  }

  const refreshVisits = useCallback(() => {
    if (qr) api.visits(qr, getDeviceId()).then(setVisits).catch(() => {});
  }, [qr]);

  useEffect(() => {
    if (!sessionId || !live) return;
    player.current ??= new TtsPlayer();
    const c = connectCustomer(
      sessionId,
      (e: CustomerOutbound) => {
        if (e.type === "state") {
          setState((before) => {
            // The shop answered via Hermion (briefing -> negotiating): open the call so the customer hears it.
            if (before === "briefing" && e.state === "negotiating") {
              setView("call");
              void enableVoice();
            }
            return e.state;
          });
          if (e.state === "pending_merchant" && wantsRejoin.current) {
            wantsRejoin.current = false;
            void api.rejoin(sessionId).catch((err) => setError(err instanceof ApiError ? err.message : t("startFailed")));
          } else if (e.state !== "negotiating" && e.state !== "discovery" && e.state !== "intro") {
            // Sent, decided or paused: the call closes and the home page shows where the basket stands.
            setSheet(false);
            setMore(false);
            setView("home");
            mic.current?.stop();
            mic.current = null;
            player.current?.stop();
          }
          refreshVisits();
        } else if (e.type === "agent_state") setAgent(e.state);
        else if (e.type === "transcript") {
          // The server uses revised STT partials for barge-in; the customer sees only finalized words.
          if (!e.final) return;
          setTranscript((t) => [...t, { speaker: e.speaker, text: e.text, at: clock() }]);
        } else if (e.type === "caption") setCaption({ speaker: e.speaker, product_name: e.product_name, amount: e.amount });
        else if (e.type === "basket") {
          if (e.lines.length > basketCount.current) {
            setToast(translate(uiLangRef.current, "added"));
            setBump((n) => n + 1);
            setTimeout(() => setToast(null), 2500);
          }
          basketCount.current = e.lines.length;
          setBasket({ lines: e.lines, total: e.total });
        } else if (e.type === "tts_stop") player.current?.stop();
        else if (e.type === "error") {
          if (e.code === "SPEECH_ERROR") setVoiceError(e.message);
          else if (e.code !== "UNSUPPORTED_LANGUAGE") setError(e.message);
        }
      },
      {
        onBinary: (chunk) => player.current?.enqueue(chunk),
        onClose: () => player.current?.stop(),
        onReconnect: () => {
          setTranscript([]);
          c.send({ type: "ui_language", code: uiLangRef.current });
          if (mic.current) c.send({ type: "voice_start" });
        },
      },
    );
    conn.current = c;
    allowAudio.current = true;
    c.send({ type: "ui_language", code: uiLangRef.current });
    void enableVoice();
    return () => {
      allowAudio.current = false;
      mic.current?.stop();
      mic.current = null;
      c.close();
      player.current?.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, live]);

  /** Clear the call (not the shop): used before a new session starts. */
  const resetCall = useCallback(() => {
    basketCount.current = 0;
    setLog(false);
    setToast(null);
    setState(null);
    setAgent("idle");
    setTranscript([]);
    setCaption(null);
    setBasket({ lines: [], total: "0" });
    setSheet(false);
    setMore(false);
    setMuted(false);
    setConfirmError(null);
    setVoiceError(null);
  }, []);

  /** Switch shops: return to the scan screen without exiting this shop's live session. */
  const leaveShop = useCallback(() => {
    allowAudio.current = false;
    mic.current?.stop();
    mic.current = null;
    player.current?.stop();
    wantsRejoin.current = false;
    resetCall();
    setLive(false);
    setSessionId(null);
    setShopInfo(null);
    setScannerOpen(false);
    setQr(null);
    setVisits([]);
    setView("home");
  }, [resetCall]);

  async function enableVoice() {
    player.current ??= new TtsPlayer();
    player.current.unlock();
    try {
      const connection = conn.current;
      if (!mic.current) {
        const capture = await startMicCapture((chunk) => { if (allowAudio.current && conn.current === connection) connection?.sendBinary?.(chunk); });
        if (!allowAudio.current || conn.current !== connection) { capture.stop(); return; }
        if (mic.current) capture.stop();
        else mic.current = capture;
      }
      mic.current.setMuted(muted);
      conn.current?.send({ type: "voice_start" });
      setVoiceError(null);
    } catch {
      setVoiceError(translate(uiLangRef.current, "micUnavailable"));
    }
  }

  async function scan(qrToken: string) {
    setError(null);
    try {
      const { session_id } = await api.createSession({ qr_token: qrToken, device_id: getDeviceId(), customer_name: name.trim() || null });
      resetCall();
      setLive(false);
      setSessionId(session_id); // the scanner disappears while the customer is in the shop
      setScannerOpen(false);
      setQr(qrToken);
      setView("home");
      api.session(session_id).then((s) => setState(s.state)).catch(() => {});
      api.visits(qrToken, getDeviceId()).then(setVisits).catch(() => {});
      const chosen = shops.find((x) => x.qr_token === qrToken);
      setShopInfo({ name: chosen?.shop_name ?? "", description: chosen?.shop_description ?? "" });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("startFailed"));
    }
  }

  async function removeLine(productId: string) {
    if (!sessionId) return;
    try {
      const next = await api.removeFromBasket(sessionId, productId);
      basketCount.current = next.lines.length;
      setBasket({ lines: next.lines, total: next.total });
    } catch (e) {
      setConfirmError(e instanceof ApiError ? e.message : t("removeFailed"));
    }
  }

  /** Talk to Hermion: open (or reopen) the call. A finished visit starts a new session; a basket waiting for the
   *  shop is taken back once the socket confirms the state (rejoin). */
  async function talk() {
    if (!qr) return;
    setError(null);
    let id = sessionId;
    if (!id || (state !== null && TERMINAL_STATES.includes(state))) {
      try {
        id = (await api.createSession({ qr_token: qr, device_id: getDeviceId(), customer_name: name.trim() || null })).session_id;
      } catch (e) {
        return setError(e instanceof ApiError ? e.message : t("startFailed"));
      }
      resetCall();
      setLive(false);
      setSessionId(id);
      setState("intro");
    }
    setView("call");
    if (state === "pending_merchant") {
      if (live) void api.rejoin(id).catch(() => {});
      else wantsRejoin.current = true;
    }
    if (live) void enableVoice();
    else setLive(true);
  }

  async function endCall() {
    const id = sessionId;
    setLive(false);
    setView("home");
    mic.current?.stop();
    mic.current = null;
    if (id) await api.exitSession(id).catch(() => {});
    setState("exited");
    refreshVisits();
  }

  async function confirmAndSend() {
    if (!sessionId) return;
    setBusy(true);
    setConfirmError(null);
    try {
      await api.confirm(sessionId);
      setSheet(false);
    } catch (e) {
      setConfirmError(e instanceof ApiError ? e.message : t("sendFailed"));
    } finally {
      setBusy(false);
    }
  }

  const terminal = state !== null && TERMINAL_STATES.includes(state);
  useEffect(() => {
    if (terminal) {
      mic.current?.stop();
      mic.current = null;
      player.current?.stop();
      conn.current?.send({ type: "mute", muted: true });
    }
  }, [terminal]);
  const inCall = sessionId !== null && view === "call" && !terminal;
  const canType = inCall && (state === "intro" || state === "discovery" || state === "negotiating");
  const early = transcript.length <= 1 && !caption;
  const mascot: AgentState = agent;
  const showShop = Boolean(shopInfo && early && inCall);

  return (
    <section className="relative flex h-full min-h-0 flex-col items-center gap-2 overflow-hidden bg-black p-2" data-testid="customer-pane">
      {!sessionId && scannerOpen && (
        <ScanStrip
          shops={shops}
          onScan={scan}
          onCancel={() => setScannerOpen(false)}
          lang={uiLang}
        />
      )}
      <div ref={pane} className="flex min-h-0 w-full flex-1 items-center justify-center">
      <div style={{ width: 330 * scale, height: 660 * scale }} className="shrink-0">
      <div style={{ transform: `scale(${scale})`, transformOrigin: "top left" }}>
      <PhoneFrame
        status={
          inCall ? (
            <div className="flex flex-col items-center gap-2" data-testid="session-status" data-state={state ?? "connecting"} data-agent={agent}>
              <div className="leading-tight">
                <p className="text-[17px] font-extrabold text-white">{shopInfo?.name || t("title")}</p>
                <p className="text-xs text-white/75">
                  {t("withHermion")} <span className="text-pink-400" aria-hidden>✦</span>
                </p>
              </div>
              {inCall && (
                <button
                  type="button"
                  onClick={() => { setMore(false); setSheet(true); }}
                  className="flex min-h-10 items-center gap-2 rounded-full bg-white px-4 text-sm font-bold text-[#071844] shadow-md transition active:scale-95"
                  aria-label={`${t("openBasket")} (${basket.lines.length})`}
                  data-testid="basket-chip"
                >
                  <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M5 8h14l-1 12H6L5 8Z" /><path d="M9 8V6a3 3 0 0 1 6 0v2" /></svg>
                  <span key={bump} className={`tabular-nums ${bump ? "hm-pop" : ""}`}>
                    {basket.lines.length} <span className="text-slate-300">·</span> {rupees(basket.total)}
                  </span>
                </button>
              )}
            </div>
          ) : null
        }
        modal={langOpen ? <LanguageWindow languages={shopLanguages} selected={uiLang} onChoose={chooseUiLanguage} onClose={() => setLangOpen(false)} /> : null}
      >
        {!sessionId ? (
          scannerOpen ? (
            <div className="relative min-h-0 flex-1">
              <CameraView lang={uiLang} />
              {error && <p className="absolute bottom-8 left-5 right-5 z-10 rounded-xl bg-white px-3 py-2 text-center text-xs font-medium text-blue-950 shadow" role="alert" data-testid="customer-error">{error}</p>}
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 px-8 text-center" data-testid="scan-prompt">
              <Mascot state="idle" />
              <p className="text-lg font-semibold">{t("title")}</p>
              <p className="text-sm text-white/70">{t("scanPrompt")}</p>
              <button
                type="button"
                onClick={() => setScannerOpen(true)}
                className="min-h-12 rounded-full bg-pink-700 px-8 text-sm font-extrabold text-white shadow-[0_8px_24px_rgba(236,72,153,0.32)] transition hover:bg-pink-600 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white active:scale-[0.98]"
                data-testid="scan-qr"
              >
                {t("scanButton")}
              </button>
              <label className="flex w-full max-w-56 flex-col gap-1 text-left text-xs text-white/70">
                {t("yourName")}
                <input value={name} onChange={(e) => setName(e.target.value.slice(0, 80))} className="rounded-full bg-white/10 px-4 py-2 text-sm text-white placeholder-white/40" placeholder={t("guest")} data-testid="customer-name" />
              </label>
              {error && <p className="max-w-60 rounded-lg bg-white/10 px-3 py-2 text-xs text-pink-200" role="alert" data-testid="customer-error">{error}</p>}
              {shopLanguages.length > 1 && <div className="mt-2"><LanguageButton lang={uiLang} onClick={() => setLangOpen(true)} /></div>}
            </div>
          )
        ) : !inCall ? (
          <ShopHome
            lang={uiLang}
            shopName={shopInfo?.name ?? ""}
            description={shopInfo?.description ?? ""}
            visits={visits}
            current={state}
            busy={false}
            onTalk={() => void talk()}
            onLeave={leaveShop}
            languageButton={shopLanguages.length > 1 ? <LanguageButton lang={uiLang} onClick={() => setLangOpen(true)} /> : null}
          />
        ) : (
          <>
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden" data-testid="call-body">
              <div className="shrink-0 pt-2">
              <Mascot state={mascot} compact label={t(AGENT_TEXT[mascot])} />
              <p className="mb-2 text-center text-xs font-medium text-white/80" aria-hidden>{t(AGENT_TEXT[mascot])}</p>
              </div>
              {showShop && shopInfo && <div className="min-h-0 flex-1 overflow-hidden"><ShopPage lang={uiLang} name={shopInfo.name} description={shopInfo.description} /></div>}
              {!showShop && <Caption lang={uiLang} caption={caption} lines={transcript} onOpen={() => setLog(true)} />}
              {toast && <p className="hm-rise mx-auto mt-2 rounded-full bg-emerald-400 px-4 py-1.5 text-xs font-semibold text-blue-950 shadow" role="status" data-testid="basket-toast">{toast}</p>}
              {voiceError && <div className="mx-6 rounded-xl bg-white p-3 text-center text-sm text-blue-950" role="alert">{voiceError} <button className="font-semibold underline" onClick={() => void enableVoice()}>{t("retryMic")}</button></div>}
              {error && <p className="mx-6 rounded-xl bg-white p-3 text-center text-sm text-blue-950" role="alert">{error}</p>}
            </div>
            {inCall && (
              <CallControls
                lang={uiLang}
                muted={muted}
                moreOpen={more}
                onMute={() => {
                  conn.current?.send({ type: "mute", muted: !muted });
                  mic.current?.setMuted(!muted);
                  setMuted(!muted);
                }}
                onEnd={endCall}
                onMore={() => setMore((m) => !m)}
                extra={
                  <>
                    {shopLanguages.length > 1 && <LanguageButton lang={uiLang} onClick={() => setLangOpen(true)} />}
                  </>
                }
              />
            )}
            {more && inCall && (
              <MoreSheet
                lang={uiLang}
                basketCount={basket.lines.length}
                canType={canType}
                onViewBasket={() => {
                  setMore(false);
                  setSheet(true);
                }}
                onSwitchShop={leaveShop}
                onSend={(text) => conn.current?.send({ type: "text_input", text })}
                onClose={() => setMore(false)}
              />
            )}
            {sheet && inCall && (
              <BasketSheet lang={uiLang} lines={basket.lines} total={basket.total} busy={busy} error={confirmError} onConfirm={confirmAndSend} onRemove={removeLine} onClose={() => setSheet(false)} />
            )}
            {log && <TranscriptSheet lang={uiLang} lines={transcript} onClose={() => setLog(false)} />}
          </>
        )}
      </PhoneFrame>
      </div>
      </div>
      </div>

      {/* Full transcript for assistive tech and tests. */}
      <ol className="sr-only" data-testid="customer-transcript">
        {transcript.map((l, i) => (
          <li key={i}>{l.speaker}: {l.text}</li>
        ))}
      </ol>
    </section>
  );
}

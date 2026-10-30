"use client";

// Dev page for the voice lane: mic -> backend /dev/stt -> Sarvam -> final text with detected language,
// and streamed TTS playback that can be stopped. Not part of the product UI.
import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { startMicCapture, TtsPlayer, type MicCapture } from "@/lib/audio";
import { DEMO_CUSTOMER_LANGUAGE, WS_URL } from "@/lib/config";

interface SttEvent {
  type: string;
  text?: string;
  language?: string | null;
  message?: string;
}

export default function VoiceDevPage() {
  const [log, setLog] = useState<string[]>([]);
  const [listening, setListening] = useState(false);
  const [lang, setLang] = useState(DEMO_CUSTOMER_LANGUAGE);
  const [text, setText] = useState("");
  const mic = useRef<MicCapture | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const player = useRef<TtsPlayer | null>(null);

  const add = (line: string) => setLog((l) => [...l.slice(-40), line]);

  async function start() {
    const socket = new WebSocket(`${WS_URL}/dev/stt?lang=auto`);
    socket.binaryType = "arraybuffer";
    socket.onmessage = (m) => {
      const e = JSON.parse(m.data as string) as SttEvent;
      add(e.type === "final" ? `final [${e.language}]: ${e.text}` : `${e.type}${e.text ? `: ${e.text}` : ""}${e.message ? `: ${e.message}` : ""}`);
    };
    socket.onclose = () => add("socket closed");
    ws.current = socket;
    await new Promise<void>((resolve, reject) => {
      socket.onopen = () => resolve();
      socket.onerror = () => reject(new Error("could not reach the backend"));
    });
    mic.current = await startMicCapture((chunk) => socket.readyState === WebSocket.OPEN && socket.send(chunk));
    setListening(true);
  }

  function stop() {
    mic.current?.stop();
    ws.current?.close();
    mic.current = ws.current = null;
    setListening(false);
  }

  async function speak() {
    player.current ??= new TtsPlayer();
    const started = performance.now();
    player.current.onEnded = () => add(`tts ended after ${Math.round(performance.now() - started)} ms`);
    try {
      await player.current.playStream(api.ttsStreamUrl(lang, text));
      add("tts stream received");
    } catch (e) {
      add(`tts: ${(e as Error).message}`);
    }
  }

  return (
    <main className="mx-auto max-w-xl space-y-4 p-6" data-testid="voice-dev">
      <h1 className="text-xl font-semibold">Voice dev page</h1>
      <section className="space-y-2 rounded border p-4">
        <h2 className="font-medium">Mic → Sarvam STT (language auto)</h2>
        <button
          className="rounded bg-slate-900 px-3 py-1 text-white"
          onClick={() => (listening ? stop() : start().catch((e: Error) => add(`mic: ${e.message}`)))}
          data-testid="mic-toggle"
        >
          {listening ? "Stop microphone" : "Start microphone"}
        </button>
      </section>
      <section className="space-y-2 rounded border p-4">
        <h2 className="font-medium">Streamed TTS</h2>
        <input value={lang} onChange={(e) => setLang(e.target.value)} className="w-24 rounded border px-2 py-1" aria-label="language code" />
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Text (empty = sample greeting)" className="ml-2 w-80 rounded border px-2 py-1" />
        <div className="space-x-2">
          <button className="rounded bg-slate-900 px-3 py-1 text-white" onClick={speak} data-testid="tts-play">
            Speak
          </button>
          <button className="rounded border px-3 py-1" onClick={() => player.current?.stop()} data-testid="tts-stop">
            Stop
          </button>
        </div>
      </section>
      <ol className="space-y-1 rounded bg-slate-100 p-3 font-mono text-xs" data-testid="voice-log">
        {log.map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ol>
    </main>
  );
}

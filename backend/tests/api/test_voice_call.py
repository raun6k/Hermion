import uuid

from fastapi.testclient import TestClient


def test_voice_greeting_and_fake_speech_turn(client: TestClient) -> None:
    sid = client.post(
        "/sessions", json={"qr_token": "hermion-m001-demo", "device_id": str(uuid.uuid4())}
    ).json()["session_id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        assert ws.receive_json()["type"] == "state"
        assert ws.receive_json()["type"] == "agent_state"
        ws.send_json({"type": "voice_start"})
        ws.send_json({"type": "ui_language", "code": "te-IN"})
        events = []
        audio = False
        while True:
            message = ws.receive()
            if message.get("bytes") is not None:
                audio = True
            elif message.get("text"):
                import json

                event = json.loads(message["text"])
                events.append(event["type"])
                if event["type"] == "tts_end":
                    break
        assert audio and "transcript" in events
        ws.send_bytes(b"\x01\x00" * 16000)
        events = []
        while True:
            message = ws.receive()
            if message.get("text"):
                import json

                event = json.loads(message["text"])
                events.append(event["type"])
                if event["type"] == "transcript" and event["speaker"] == "customer" and event["final"]:
                    assert event["text"] == "fake transcript"
                    break
        assert "tts_stop" in events
        while True:
            message = ws.receive()
            if message.get("text"):
                event = json.loads(message["text"])
                if event.get("type") == "tts_end":
                    break
        trace = client.get(f"/merchant/sessions/{sid}").json()
        timing = trace["turn_timings"][0]["measurements"]
        assert timing["input"] == "voice"
        assert timing["model_calls"] >= 0
        assert timing["stt_final_ms"] is not None
        import time

        for _ in range(30):
            trace = client.get(f"/merchant/sessions/{sid}").json()
            timing = trace["turn_timings"][0]["measurements"]
            if timing["speech_end_to_first_audio_ms"] is not None:
                break
            time.sleep(0.02)
        assert timing["speech_end_to_first_audio_ms"] is not None


def _scripted_stt(monkeypatch, opened, received, language="te-IN"):
    from app.api import ws_customer
    from app.speech.stt import Transcript

    class Stream:
        def __init__(self, callbacks):
            self.callbacks = callbacks

        async def push_pcm(self, pcm):
            received.append(pcm)
            await self.callbacks.on_speech_start()
            await self.callbacks.on_speech_end()
            await self.callbacks.on_final(Transcript(text=pcm.decode(), language=language))

        async def close(self):
            return None

    class Speech:
        async def open_stream(self, callbacks, language_code):
            opened.append(language_code)
            return Stream(callbacks)

    monkeypatch.setattr(ws_customer, "build_stt", lambda settings: Speech())


def _customer_texts(ws, count, speaker="customer"):
    import json

    texts = []
    while len(texts) < count:
        msg = ws.receive()
        if msg.get("text"):
            event = json.loads(msg["text"])
            if (
                event.get("type") == "transcript"
                and event.get("speaker") == speaker
                and event.get("final", True)
            ):
                texts.append(event["text"])
    return texts


def test_voice_mute_auto_language_and_reconnect(client: TestClient, monkeypatch, reseed) -> None:
    opened, received = [], []
    _scripted_stt(monkeypatch, opened, received)
    sid = client.post(
        "/sessions", json={"qr_token": "hermion-m001-demo", "device_id": str(uuid.uuid4())}
    ).json()["session_id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "ui_language", "code": "te-IN"})
        for _ in range(4):
            ws.receive_json()
        ws.send_json({"type": "voice_start"})
        ws.send_json({"type": "mute", "muted": True})
        ws.send_bytes(b"ignored")
        ws.send_json({"type": "mute", "muted": False})
        ws.send_bytes(b"first")
        assert _customer_texts(ws, 1) == ["first"]
        _customer_texts(ws, 1, "hermion")  # the reply is stored before the socket closes
        assert received == [b"first"]
        assert opened == ["auto"]  # speech language is never pinned
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        assert ws.receive_json()["type"] == "state"
        assert ws.receive_json()["type"] == "agent_state"
        replay = [ws.receive_json() for _ in range(3)]
        assert replay[0]["speaker"] == "hermion"
        assert replay[1]["text"] == "first"


def test_pauses_inside_one_thought_are_a_single_turn(client: TestClient, monkeypatch, reseed) -> None:
    """Finals split by short pauses (and a stray "I") are joined; Hermion answers once, after the quiet."""
    opened, received = [], []
    _scripted_stt(monkeypatch, opened, received)
    client.app.state.settings.voice_endpoint_ms = 400
    sid = client.post(
        "/sessions", json={"qr_token": "hermion-m001-demo", "device_id": str(uuid.uuid4())}
    ).json()["session_id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "voice_start"})
        ws.send_json({"type": "ui_language", "code": "en-IN"})
        for chunk in (b"I want to buy", b"a pair of", b"blue jeans"):
            ws.send_bytes(chunk)
        assert _customer_texts(ws, 1) == ["I want to buy a pair of blue jeans"]
        ws.send_bytes(b"I")  # one stray letter is not a turn
        ws.send_json({"type": "text_input", "text": "hello again"})
        assert _customer_texts(ws, 1) == ["hello again"]


def test_screen_language_sets_session_language(client: TestClient, reseed) -> None:
    sid = client.post(
        "/sessions", json={"qr_token": "hermion-m001-demo", "device_id": str(uuid.uuid4())}
    ).json()["session_id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "ui_language", "code": "ta-IN"})
        for _ in range(4):
            ws.receive_json()
    assert client.get(f"/sessions/{sid}").json()["language"] == "ta-IN"


def test_switching_screen_language_mid_call_switches_hermion(client: TestClient, reseed) -> None:
    from app import languages

    sid = client.post(
        "/sessions", json={"qr_token": "hermion-m001-demo", "device_id": str(uuid.uuid4())}
    ).json()["session_id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "ui_language", "code": "en-IN"})
        for _ in range(4):  # thinking, discovery, greeting, idle
            ws.receive_json()
        ws.send_json({"type": "ui_language", "code": "hi-IN"})
        line = ws.receive_json()
        assert (line["type"], line["speaker"]) == ("transcript", "hermion")
        assert line["text"] == languages.require("hi-IN").switched
        ws.send_json({"type": "ui_language", "code": "hi-IN"})  # same language again: nothing said
    assert client.get(f"/sessions/{sid}").json()["language"] == "hi-IN"

from app.speech.turn_taking import BargeInGate, endpoint_delay_ms

W = dict(base_ms=1600, short_ms=1200, long_ms=2200)


def test_waits_longer_mid_clause_and_shorter_after_a_sentence() -> None:
    assert endpoint_delay_ms("I want the blue shirt and", **W) == 2200
    assert endpoint_delay_ms("I want the blue shirt and.", **W) == 2200  # STT punctuation
    assert endpoint_delay_ms("I can pay 700.", **W) == 2200
    assert endpoint_delay_ms("mera budget hai 800", **W) == 2200
    assert endpoint_delay_ms("How much is this shirt?", **W) == 1200
    assert endpoint_delay_ms("blue shirt medium", **W) == 1600
    assert endpoint_delay_ms("anything", base_ms=0, short_ms=1, long_ms=2) == 0


def test_noise_and_single_tokens_never_barge_in() -> None:
    gate = BargeInGate()
    gate.start(0.0)
    assert not gate.partial("", 0.1)
    assert not gate.partial("uh", 0.2)
    assert gate.partial("wait I want", 0.3)
    assert not gate.partial("wait I want more", 0.4)  # once per speech start


def test_partial_a_second_after_vad_still_interrupts_but_a_late_one_does_not() -> None:
    gate = BargeInGate()
    gate.start(0.0)
    assert gate.partial("hold on please", 1.1)
    gate.start(5.0)
    assert not gate.partial("hold on please", 6.6)

"""Talking with the virtual people aloud: the voice button and the ear of a call make a person's sound into words, which are written in the room as
theirs; one virtual person answers, and the answer is read sentence by sentence."""

import base64
import json

import pytest
from sn_shared import servicesig

from api.chat import speech, virtual_reply, voice_stream
from tests.chat.social.test_virtual_people import pool
from tests.chat.test_room_api import call

EAR_SECRET = "e" * 32
SOUND = base64.b64encode(b"\x01\x00" * 16000).decode()  # one second at 16 kHz


@pytest.fixture
def frames(monkeypatch):
    """What is sent to the socket of the room; the agent and the voice are plain functions."""
    sent = []
    monkeypatch.setattr(voice_stream, "emit", lambda request, slug, payload: sent.append(payload))
    monkeypatch.setattr(speech, "enabled", lambda: True)
    monkeypatch.setattr(speech, "transcribe", lambda pcm, rate: "Xin chào mọi người")
    monkeypatch.setattr(speech, "synthesize", lambda text, voice: (text.encode() * 4, 24000))
    monkeypatch.setattr(virtual_reply, "ask_agent_counted", lambda *a, **k: ("Chào bạn. Mình nghe rõ rồi! Bạn khỏe không?", (120, 15, 800)))
    monkeypatch.setenv("CALLEAR_SECRET", EAR_SECRET)
    voice_stream._QUIET_UNTIL.clear()
    voice_stream._LAST_SPEAKER.clear()
    return sent


def room_with_virtual(client):
    pool(client)
    call(client, "POST", "/rooms", 1, "alice", json={"slug": "vcall", "title": "Vcall", "visibility": "public"})
    call(client, "POST", "/rooms/vcall/virtual", 1, "alice", json={"count": 2})


def say(client, uid=1, name="alice"):
    return call(client, "POST", "/rooms/vcall/voice-message", uid, name, json={"pcm": SOUND, "rate": 16000})


def heard(client, identity=1, humans=1, secret=EAR_SECRET, slug="vcall"):
    body = json.dumps({"slug": slug, "identity": identity, "pcm": SOUND, "rate": 16000, "humans": humans}).encode()
    headers = {"Content-Type": "application/json", **servicesig.sign(secret, body, "POST /internal/call-heard")}
    return client.post("/internal/call-heard", content=body, headers=headers)


def test_a_voice_message_is_written_as_the_persons_own_and_answered_aloud_sentence_by_sentence(raw_client, frames):
    room_with_virtual(raw_client)
    answer = say(raw_client)
    assert answer.status_code == 200 and answer.json()["text"] == "Xin chào mọi người" and answer.json()["answered"]
    voices = [f for f in frames if f["type"] == "voice"]
    assert [f["text"] for f in voices] == ["Chào bạn.", "Mình nghe rõ rồi!", "Bạn khỏe không?"]  # one sound per sentence, in order
    assert [f["seq"] for f in voices] == [0, 1, 2] and [f["last"] for f in voices] == [False, False, True]
    assert len({f["id"] for f in voices}) == 1 and all(f["pcm"] and f["rate"] == 24000 for f in voices)
    messages = call(raw_client, "GET", "/rooms/vcall/messages", 1, "alice").json()
    assert any(m["content"] == "Xin chào mọi người" and m["username"] == "alice" for m in messages)  # theirs, not the voice button's
    assert any(m["content"].startswith("Chào bạn") for m in messages)
    assert any(m["username"] == "system" and m["content"].startswith("ai_usage:120:15:800:") for m in messages)  # what the answer cost
    assert frames[0]["type"] == "message"  # the words of the person first


def test_a_voice_message_where_nothing_is_understood_is_refused(raw_client, frames, monkeypatch):
    room_with_virtual(raw_client)
    monkeypatch.setattr(speech, "transcribe", lambda pcm, rate: "")
    assert say(raw_client).status_code == 422
    assert frames == []


def test_a_voice_message_in_a_room_without_virtual_people_is_just_a_message(raw_client, frames):
    call(raw_client, "POST", "/rooms", 1, "alice", json={"slug": "plain", "title": "Plain", "visibility": "public"})
    answer = call(raw_client, "POST", "/rooms/plain/voice-message", 1, "alice", json={"pcm": SOUND, "rate": 16000})
    assert answer.status_code == 200 and answer.json() == {"text": "Xin chào mọi người", "answered": ""}
    assert [f["type"] for f in frames] == ["message"]


def test_somebody_outside_the_room_cannot_send_a_voice_message_and_a_long_one_is_refused(raw_client, frames):
    room_with_virtual(raw_client)
    assert say(raw_client, 5, "eve").status_code in (403, 404)
    too_long = base64.b64encode(b"\x01\x00" * 16000 * 40).decode()
    assert call(raw_client, "POST", "/rooms/vcall/voice-message", 1, "alice", json={"pcm": too_long, "rate": 16000}).status_code in (413, 422)


def test_the_ear_of_a_call_writes_what_a_person_said_and_a_virtual_person_answers_the_person_alone_with_them(raw_client, frames):
    room_with_virtual(raw_client)
    assert heard(raw_client, identity=1, humans=1).status_code == 204
    assert any(f["type"] == "message" for f in frames) and any(f["type"] == "voice" for f in frames)


def test_among_several_people_the_ear_writes_it_but_a_virtual_person_answers_only_when_called(raw_client, frames, monkeypatch):
    room_with_virtual(raw_client)
    assert heard(raw_client, humans=3).status_code == 204
    assert [f["type"] for f in frames] == ["message"]  # written, nobody answers
    frames.clear()
    name = next(m["username"] for m in call(raw_client, "GET", "/rooms/vcall/members", 1, "alice").json() if m.get("virtual"))
    monkeypatch.setattr(speech, "transcribe", lambda pcm, rate: f"{name} ơi, bạn khỏe không?")
    heard(raw_client, humans=3)
    assert any(f["type"] == "voice" for f in frames)


def test_what_the_ear_hears_while_a_virtual_person_is_talking_is_not_taken_for_a_person(raw_client, frames):
    room_with_virtual(raw_client)
    heard(raw_client, humans=1)
    frames.clear()
    assert voice_stream.is_quiet("vcall")  # the voice is still in the air
    assert heard(raw_client, humans=1).status_code == 204
    assert frames == []


def test_a_call_with_a_wrong_signature_is_refused(raw_client, frames):
    assert heard(raw_client, secret="c" * 32).status_code == 401


def test_a_request_to_share_the_screen_makes_a_slide_and_stopping_takes_it_away(raw_client, frames, monkeypatch):
    room_with_virtual(raw_client)
    monkeypatch.setattr(virtual_reply, "ask_agent_counted", lambda *a, **k: ("• Thăng Long\n• Nhà Lý\n• Thủ đô", (120, 15, 800)))
    monkeypatch.setattr(speech, "transcribe", lambda pcm, rate: "hãy chia sẻ màn hình về lịch sử Hà Nội")
    say(raw_client)
    slide = next(f for f in frames if f["type"] == "slide")
    assert slide["lines"] == ["Thăng Long", "Nhà Lý", "Thủ đô"] and slide["title"].startswith("hãy chia sẻ")
    monkeypatch.setattr(speech, "transcribe", lambda pcm, rate: "dừng chia sẻ đi")
    say(raw_client)
    assert [f for f in frames if f["type"] == "slide"][-1]["lines"] == []


def test_the_one_called_by_name_answers_else_the_first():
    people = [(1, "Giang_Le", "Giang Le", ""), (2, "Anh_Bui", "Anh Bui", "")]
    assert voice_stream.who_answers(people, "Anh Bui ơi, bạn khỏe không")[0] == 2
    assert voice_stream.who_answers(people, "chào cả nhà")[0] == 1
    assert [voice_stream.who_answers(people, "chào cả nhà", "r")[0] for _ in range(4)] == [1, 2, 1, 2]  # they take turns
    assert voice_stream.who_answers(people, "Giang Le ơi", "r")[0] == 1 and voice_stream.who_answers(people, "ai đó", "r")[0] == 2  # (named, then the next)
    assert voice_stream.sentences("Một. Hai! Ba?\nBốn") == ["Một.", "Hai!", "Ba?", "Bốn"]

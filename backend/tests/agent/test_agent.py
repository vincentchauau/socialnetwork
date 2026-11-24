"""The agent inside the chat: the words of a virtual person, the limits, the script read from `users`."""

import pytest

from api.chat.agent import providers, service
from api.chat.agent.models import Persona, persona_of
from api.chat.agent.providers import Line
from sn_shared.testing import add_person

SCRIPT = {
    "display_name": "Lan Nguyen", "persona_role": "gia sư tiếng Anh kiên nhẫn", "speaking_style": "nhẹ nhàng",
    "region": "Đà Lạt", "interests": ["yoga", "cà phê"], "headline": "Gia sư",
}  # fmt: skip
HISTORY = [Line("alice", "Chào bạn")]


def know(factory, user_id=500, kind="virtual", body=None, username="Lan_Nguyen"):
    """A person in `users`: a virtual one has a script (role, way of speaking) beside the public profile."""
    script = SCRIPT if body is None else body
    add_person(
        factory, user_id, username, kind=kind, name=script.get("display_name"), persona_role=script.get("persona_role"),
        speaking_style=script.get("speaking_style"), region=script.get("region"), interests=script.get("interests"), headline=script.get("headline"),
    )


def ask(factory, virtual_id=500, caller_id=1, history=HISTORY):
    with factory() as db:
        return service.reply(db, virtual_id, caller_id, "alice", history)


def test_a_virtual_person_answers_in_the_voice_of_their_script(factory):
    know(factory)
    answer = ask(factory)
    assert answer is not None
    assert "Lan Nguyen" in answer.text and "người ảo" in answer.text and "alice" in answer.text
    assert len(answer.text) <= providers.MAX_REPLY_CHARS


def test_an_unknown_person_a_human_and_an_empty_history_get_no_answer(factory):
    know(factory)
    know(factory, user_id=7, kind="human", username="Human_Person")
    assert ask(factory, virtual_id=999) is None
    assert ask(factory, virtual_id=7) is None
    assert ask(factory, history=[]) is None


def test_the_replies_for_one_caller_are_limited_per_hour(factory, monkeypatch):
    know(factory)
    monkeypatch.setattr(service, "_limiter", service.Limiter(2))
    assert [ask(factory) is not None for _ in range(3)] == [True, True, False]
    assert ask(factory, caller_id=2) is not None  # another caller has their own hour


def test_the_limiter_forgets_after_the_window():
    limiter = service.Limiter(1, window=10)
    assert limiter.allow(1, now=0) is True
    assert limiter.allow(1, now=5) is False
    assert limiter.allow(1, now=11) is True


def test_the_script_is_read_from_users_as_it_is_now(factory):
    know(factory)
    first = ask(factory).text
    know(factory, body={**SCRIPT, "display_name": "Lan Moi"})  # the same row is updated
    assert "Lan Moi" in ask(factory).text and "Lan Moi" not in first


def test_a_script_is_made_from_a_row_of_users(factory):
    know(factory)
    with factory() as db:
        from sn_shared.directory import Person

        script = persona_of(db.get(Person, 500))
    assert script == Persona(
        user_id=500, username="Lan_Nguyen", display_name="Lan Nguyen", role="gia sư tiếng Anh kiên nhẫn", style="nhẹ nhàng",
        headline="Gia sư", region="Đà Lạt", interests=["yoga", "cà phê"],
    )


def test_a_failing_model_gives_no_answer_and_does_not_crash(factory, monkeypatch):
    know(factory)

    class Broken:
        def reply_with_usage(self, *args):
            raise providers.AgentError("down")

    monkeypatch.setattr(service, "_provider", Broken())
    assert ask(factory) is None


def test_an_unknown_tool_gives_no_card():
    assert service.run_tool("no.such.tool", {}, 1, "", False) is None

"""The host sets how the game is played before it starts: the time of a night turn, the event cards, the chat of the dead."""

from tests.werewolf.test_api import get, make_room, post, start


def test_the_host_changes_the_options_and_the_state_says_so(client):
    code = make_room(client, humans=1)
    answer = post(client, f"/rooms/{code}/options", json={"timerSeconds": 60, "events": False, "deadTalk": False})
    assert answer.status_code == 200, answer.text
    state = answer.json()["state"]
    assert (state["timer"], state["events"], state["deadTalk"]) == (60, False, False)
    only_one = post(client, f"/rooms/{code}/options", json={"timerSeconds": 0}).json()["state"]
    assert (only_one["timer"], only_one["events"], only_one["deadTalk"]) == (0, False, False)  # what is not sent stays


def test_a_bad_time_is_refused_and_only_the_host_changes_anything_before_the_start(client):
    code = make_room(client, humans=2)
    assert post(client, f"/rooms/{code}/options", json={"timerSeconds": 100000}).status_code == 422
    assert post(client, f"/rooms/{code}/options", 2, "user2", json={"events": False}).status_code == 403
    assert get(client, f"/rooms/{code}", 1, "alice").json()["state"]["events"] is True
    start(client, code)
    assert post(client, f"/rooms/{code}/options", json={"events": False}).status_code in (400, 409)

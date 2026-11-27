from tests.rally.conftest import ALICE, BOB


def upload(client, headers=ALICE, name: str = "Final", filename: str = "game.mp4", body: bytes = b"video-bytes"):
    return client.post("/matches", data={"name": name}, files={"video": (filename, body, "video/mp4")}, headers=headers)


def rally_body(start: int, end: int, hits: int, winner: str) -> dict:
    return {"start_ms": start, "end_ms": end, "hits": hits, "winner": winner}


def test_upload_creates_match_and_streams_video(client) -> None:
    created = upload(client)

    assert created.status_code == 201
    video = client.get(f"/matches/{created.json()['id']}/video", headers=ALICE)
    assert video.content == b"video-bytes"


def test_upload_rejects_unsupported_extension(client) -> None:
    assert upload(client, filename="notes.txt").status_code == 415


def test_rallies_are_numbered_and_summarised(client) -> None:
    match_id = upload(client).json()["id"]
    url = f"/matches/{match_id}/rallies"

    first = client.post(url, json=rally_body(0, 800, 2, "A"), headers=ALICE)
    second = client.post(url, json=rally_body(1000, 4000, 6, "B"), headers=ALICE)

    assert first.status_code == 201 and second.status_code == 201
    match = client.get(f"/matches/{match_id}", headers=ALICE).json()
    assert [rally["number"] for rally in match["rallies"]] == [1, 2]
    assert match["stats"]["score"] == {"A": 1, "B": 1}
    assert match["stats"]["max_hits"] == 6


def test_rally_rejects_end_before_start_and_unknown_winner(client) -> None:
    match_id = upload(client).json()["id"]
    url = f"/matches/{match_id}/rallies"

    backwards = client.post(url, json=rally_body(500, 400, 1, "A"), headers=ALICE)
    unknown = client.post(url, json=rally_body(0, 100, 1, "C"), headers=ALICE)

    assert backwards.status_code == 422
    assert unknown.status_code == 422


def test_delete_rally_removes_it(client) -> None:
    match_id = upload(client).json()["id"]
    rally_id = client.post(f"/matches/{match_id}/rallies", json=rally_body(0, 100, 1, "A"), headers=ALICE).json()["id"]

    deleted = client.delete(f"/matches/{match_id}/rallies/{rally_id}", headers=ALICE)

    assert deleted.status_code == 204
    assert client.get(f"/matches/{match_id}", headers=ALICE).json()["rallies"] == []


def test_other_people_cannot_see_or_change_a_match(client) -> None:
    match_id = upload(client, headers=ALICE).json()["id"]

    assert client.get(f"/matches/{match_id}", headers=BOB).status_code == 404
    assert client.get(f"/matches/{match_id}/video", headers=BOB).status_code == 404
    assert client.post(f"/matches/{match_id}/rallies", json=rally_body(0, 100, 1, "A"), headers=BOB).status_code == 404
    assert client.get("/matches", headers=BOB).json() == []

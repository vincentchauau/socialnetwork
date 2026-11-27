from tests.rally.conftest import ALICE, BOB


def upload(client, headers=ALICE, name: str = "Final", filename: str = "game.mp4", body: bytes = b"video-bytes"):
    return client.post("/matches", data={"name": name}, files={"video": (filename, body, "video/mp4")}, headers=headers)


def test_upload_creates_match_and_streams_video(client) -> None:
    created = upload(client)

    assert created.status_code == 201
    video = client.get(f"/matches/{created.json()['id']}/video", headers=ALICE)
    assert video.content == b"video-bytes"


def test_upload_rejects_unsupported_extension(client) -> None:
    assert upload(client, filename="notes.txt").status_code == 415


class FakeThread:
    started: list[tuple] = []

    def __init__(self, target, args, daemon) -> None:
        self.target = target
        self.args = args

    def start(self) -> None:
        FakeThread.started.append(self.args)


def test_upload_starts_the_players_job_by_itself(client, monkeypatch) -> None:
    from api.rally import routes

    FakeThread.started = []
    monkeypatch.setattr(routes.threading, "Thread", FakeThread)

    match_id = upload(client).json()["id"]
    status = client.get(f"/matches/{match_id}/people", headers=ALICE).json()

    assert len(FakeThread.started) == 1
    assert status == {"status": "running", "samples": [], "shuttle": []}


def test_players_job_is_not_started_twice(client, monkeypatch) -> None:
    from api.rally import routes

    FakeThread.started = []
    monkeypatch.setattr(routes.threading, "Thread", FakeThread)
    match_id = upload(client).json()["id"]

    again = client.post(f"/matches/{match_id}/people", headers=ALICE)

    assert again.status_code == 409
    assert len(FakeThread.started) == 1


def test_players_are_not_read_by_another_person(client) -> None:
    match_id = upload(client).json()["id"]

    assert client.get(f"/matches/{match_id}/people", headers=BOB).status_code == 404


def test_other_people_cannot_see_or_change_a_match(client) -> None:
    match_id = upload(client, headers=ALICE).json()["id"]

    assert client.get(f"/matches/{match_id}", headers=BOB).status_code == 404
    assert client.get(f"/matches/{match_id}/video", headers=BOB).status_code == 404
    assert client.get("/matches", headers=BOB).json() == []

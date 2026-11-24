"""The face meter: a camera card that saves its numbers through the browser, and a card that shows what was saved."""

from tests.agent.test_tools import CALLS, clean, fake_http, post_tool  # noqa: F401  (clean resets the calls of each test)

ROWS = [
    {"id": 3, "createdAt": "2026-01-02T03:04:05Z", "symmetry": 91, "eye": 95, "nose": None, "mouth": 90, "ear": None, "angle": 2.5},
    {"id": 2, "createdAt": "2026-01-01T03:04:05Z", "symmetry": 80, "eye": None, "nose": None, "mouth": None, "ear": None, "angle": None},
]


def test_the_camera_card_says_where_the_numbers_are_kept_and_asks_nothing_of_the_service(client):
    client.app.state.http = fake_http({})
    card = post_tool(client, tool="face.measure", args={}).json()["card"]
    assert card["type"] == "camera" and card["tool"] == "face.measure" and CALLS == []
    step = card["upload"]["steps"][0]
    assert step["path"] == "/api/face/measurements" and step["kind"] == "json" and step["capture"] == {"measurement_id": "id"}
    assert step["fields"] == ["symmetry", "eye", "nose", "mouth", "ear", "angle"] and card["upload"]["send"] == ["measurement_id"]
    assert "image" not in card and all("file" not in field for field in step["fields"])  # no picture is ever part of it


def test_a_saved_measurement_is_looked_up_as_the_person_and_shown(client):
    client.app.state.http = fake_http({"/measurements": (200, ROWS)})
    card = post_tool(client, tool="face.measure", args={"measurement_id": 3}, confirmed=True).json()["card"]
    assert card["type"] == "detail" and card["lines"][0] == "Symmetry 91%" and "nose –" in card["lines"][1] and card["lines"][2] == "Head angle 2.5°"
    assert CALLS[-1][2]["Cookie"] == "sn_token=tok"
    missing = post_tool(client, tool="face.measure", args={"measurement_id": 99}, confirmed=True).json()["card"]
    assert missing == {"type": "error", "summary": "That measurement was not found"}


def test_the_history_lists_the_latest_measurements(client):
    client.app.state.http = fake_http({"/measurements": (200, ROWS)})
    items = post_tool(client, tool="face.history", args={}).json()["card"]["items"]
    assert [i["title"] for i in items] == ["Symmetry 91%", "Symmetry 80%"] and items[0]["subtitle"] == "2026-01-02 03:04"


def test_the_face_service_is_found_in_the_core(client):
    from api.chat.agent import tools

    assert tools.base("face") == "http://127.0.0.1:8000/face"
    assert post_tool(client, tool="face.measure", args={}, token="").json()["card"]["type"] == "error"

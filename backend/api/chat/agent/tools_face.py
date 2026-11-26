"""Tools of the face service: measure the symmetry of the face with the camera (the meter runs in the browser) and see what was kept.

The picture never leaves the browser. The card of type `camera` is the meter; when the person presses "Save", the browser keeps the numbers
with the service as that person (`upload`), and only the id of the saved measurement comes here, to be looked up and shown.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.chat.agent.tools import MAX_ITEMS, Http, NoArgs, Tool, ToolError, get_tools, write, action, register

SAVE = {
    "steps": [{"path": "/api/face/measurements", "kind": "json", "fields": ["symmetry", "eye", "nose", "mouth", "ear", "angle"], "capture": {"measurement_id": "id"}}],
    "send": ["measurement_id"],
}


class MeasurementRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measurement_id: int = Field(ge=1)


def pct(value: Any) -> str:
    return "–" if value is None else f"{value}%"


def lines_of(m: dict[str, Any]) -> list[str]:
    angle = "–" if m.get("angle") is None else f"{m['angle']}°"
    return [f"Symmetry {pct(m['symmetry'])}", f"Eyes {pct(m.get('eye'))} · nose {pct(m.get('nose'))} · mouth {pct(m.get('mouth'))} · ears {pct(m.get('ear'))}", f"Head angle {angle}"]


def camera_card(_: BaseModel, token: str, http: Http) -> dict[str, Any]:
    return {"type": "camera", "tool": "face.measure", "title": "Face symmetry", "args": {}, "upload": SAVE}


def measured(args: MeasurementRef, token: str, http: Http) -> dict[str, Any]:
    rows = get_tools("face", "/measurements", {"limit": 50}, token, http)
    found = next((m for m in rows if m["id"] == args.measurement_id), None)
    if found is None:
        raise ToolError("That measurement was not found")
    return {"type": "detail", "title": "Saved: face symmetry", "lines": lines_of(found), "actions": []}


def history(_: NoArgs, token: str, http: Http) -> dict[str, Any]:
    rows = get_tools("face", "/measurements", {"limit": MAX_ITEMS}, token, http)
    items = [
        {
            "title": f"Symmetry {pct(m['symmetry'])}", "subtitle": str(m.get("createdAt", ""))[:16].replace("T", " "),
            "actions": [action("Delete", "face.delete", {"measurement_id": m["id"]}, "ask")],
        }
        for m in rows[:MAX_ITEMS]
    ]
    return {"type": "list", "title": "Your face measurements", "items": items}


def delete_one(args: MeasurementRef, token: str, http: Http) -> dict[str, Any]:
    write("face", f"/measurements/{args.measurement_id}", {}, token, http, method="DELETE")
    return {"type": "done", "summary": "Deleted that measurement"}


def delete_all(_: NoArgs, token: str, http: Http) -> dict[str, Any]:
    write("face", "/measurements", {}, token, http, method="DELETE")
    return {"type": "done", "summary": "Deleted all your measurements"}


register(
    Tool("face.delete", MeasurementRef, True, delete_one, lambda a: "Delete this measurement"),
    Tool("face.clear", NoArgs, True, delete_all, lambda a: "Delete ALL your face measurements"),
    Tool("face.measure", MeasurementRef, True, measured, lambda a: "Show the saved measurement", form=camera_card),
    Tool("face.history", NoArgs, False, history),
)

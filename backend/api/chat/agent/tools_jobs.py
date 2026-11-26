"""Tools of the jobs service: post a job (a form), see who applied and move them along (buttons), see my jobs."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.chat.agent.tools import MAX_ITEMS, Http, NoArgs, Tool, get_tools, write, action, clip, field, form_card, register

EMPLOYMENT = [
    {"value": "full_time", "label": "Full time"},
    {"value": "part_time", "label": "Part time"},
    {"value": "contract", "label": "Contract"},
    {"value": "internship", "label": "Internship"},
    {"value": "freelance", "label": "Freelance"},
    {"value": "other", "label": "Other"},
]
JOB_STATES = [
    {"value": "draft", "label": "Draft"},
    {"value": "open", "label": "Open"},
    {"value": "paused", "label": "Paused"},
    {"value": "closed", "label": "Closed"},
    {"value": "filled", "label": "Filled"},
]
KINDS = "full_time|part_time|contract|internship|freelance|other"
# Where an employer may take an application from each step (the server keeps the same map).
CAN_HIRE = ("reviewing", "shortlisted", "interview", "offer")


class PostJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    company: str = Field(min_length=1, max_length=120)
    employment_type: str = Field(pattern=f"^({KINDS})$")
    location: str = Field(default="", max_length=120)
    remote: bool = False
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern="^[A-Za-z]{3}$")
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=10)


class JobId(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int = Field(ge=1)


class SetStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: int = Field(ge=1)
    status: str = Field(pattern="^(reviewing|shortlisted|interview|offer|rejected|hired)$")


def post_job_form(_: BaseModel, token: str, http: Http) -> dict[str, Any]:
    fields = [
        field("title", "Job title", "text", required=True, max=120),
        field("company", "Company", "text", required=True, max=120),
        field("employment_type", "Type", "select", required=True, options=EMPLOYMENT, value="full_time"),
        field("location", "Location", "text", max=120),
        field("remote", "Remote", "checkbox"),
        field("salary_min", "Salary from", "number", min=0),
        field("salary_max", "Salary to", "number", min=0),
        field("currency", "Currency (3 letters)", "text", max=3, value="USD"),
        field("description", "Description", "textarea", max=5000),
        field("tags", "Tags", "tags"),
    ]
    return form_card("jobs.post", "Post a job", fields, {}, "Post the job")


def post_job(args: PostJob, token: str, http: Http) -> dict[str, Any]:
    job = write("job", "/jobs", args.model_dump(exclude_none=True), token, http)
    return {"type": "done", "summary": f"Posted job #{job['id']}: {clip(job['title'])}", "href": "/job/employer"}


def my_jobs(_: NoArgs, token: str, http: Http) -> dict[str, Any]:
    rows = get_tools("job", "/me/jobs", {}, token, http)
    items = [
        {
            "title": f"#{p['id']} {clip(p['title'])}",
            "subtitle": f"{clip(p['company'], 40)} · {p['status']}",
            "href": "/job/employer",
            "actions": [
                action("Applicants", "jobs.applicants", {"job_id": p["id"]}),
                action("Edit", "jobs.editpost", {"job_id": p["id"]}),
                action("Remove", "jobs.removepost", {"job_id": p["id"]}, "ask"),
            ],
        }
        for p in rows[:MAX_ITEMS]
    ]
    return {"type": "list", "title": "Your job postings", "items": items}


def applicants(args: JobId, token: str, http: Http) -> dict[str, Any]:
    rows = get_tools("job", f"/jobs/{args.job_id}/applications", {}, token, http)
    items = []
    for a in rows[:MAX_ITEMS]:
        moves = []
        if a["status"] in ("submitted", "reviewing"):
            moves.append(action("Shortlist", "jobs.setstatus", {"application_id": a["id"], "status": "shortlisted"}, "do"))
        if a["status"] in ("reviewing", "shortlisted"):
            moves.append(action("Interview", "jobs.setstatus", {"application_id": a["id"], "status": "interview"}, "do"))
        if a["status"] in CAN_HIRE:
            moves.append(action("Hire", "jobs.setstatus", {"application_id": a["id"], "status": "hired"}, "ask"))
        if a["status"] not in ("rejected", "hired"):
            moves.append(action("Reject", "jobs.setstatus", {"application_id": a["id"], "status": "rejected"}, "ask"))
        items.append({
            "title": f"{clip(a['applicant_username'], 32)} · {a['status']}",
            "subtitle": clip(a.get("cover_letter") or "", 100),
            "href": "/job/employer",
            "actions": moves,
        })
    return {"type": "list", "title": f"Applicants of job #{args.job_id}", "items": items}


def set_status(args: SetStatus, token: str, http: Http) -> dict[str, Any]:
    write("job", f"/applications/{args.application_id}", {"status": args.status}, token, http, method="PATCH")
    return {"type": "done", "summary": f"Application #{args.application_id} is now {args.status}", "href": "/job/employer"}


register(
    Tool("jobs.post", PostJob, True, post_job, lambda a: f"Post the job {a.title}", form=post_job_form),  # type: ignore[attr-defined]
    Tool("jobs.myjobs", NoArgs, False, my_jobs),
    Tool("jobs.applicants", JobId, False, applicants),
    Tool("jobs.setstatus", SetStatus, True, set_status, lambda a: f"Mark application #{a.application_id} as {a.status}"),  # type: ignore[attr-defined]
)


# ---- jobs: look at one job, save jobs, withdraw, edit or remove a job -------------------------------


class Withdraw(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: int = Field(ge=1)


class EditPost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    company: str | None = Field(default=None, min_length=1, max_length=120)
    employment_type: str | None = Field(default=None, pattern=f"^({KINDS})$")
    location: str | None = Field(default=None, max_length=120)
    remote: bool | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern="^[A-Za-z]{3}$")
    description: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = Field(default=None, max_length=10)
    status: str | None = Field(default=None, pattern="^(draft|open|paused|closed|filled)$")


def job_detail(args: JobId, token: str, http: Http) -> dict[str, Any]:
    p = get_tools("job", f"/jobs/{args.job_id}", {}, token, http)
    pay = f"{p['salary_min'] or '?'}–{p['salary_max'] or '?'} {p['currency']}" if p.get("salary_min") or p.get("salary_max") else "Salary not shown"
    lines = [f"{clip(p['company'], 60)} · {clip(p['location'] or 'anywhere', 40)}{' · remote' if p.get('remote') else ''}", f"{p['employment_type'].replace('_', ' ')} · {pay}"]
    if p.get("tags"):
        lines.append("Tags: " + ", ".join(p["tags"][:8]))
    if p.get("description"):
        lines.append(clip(p["description"], 500))
    return {
        "type": "detail", "title": clip(p["title"]), "lines": lines,
        "actions": [action("Apply", "jobs.apply", {"job_id": p["id"]}, "ask")],
    }


def withdraw(args: Withdraw, token: str, http: Http) -> dict[str, Any]:
    write("job", f"/applications/{args.application_id}", {}, token, http, method="DELETE")
    return {"type": "done", "summary": f"Withdrew application #{args.application_id}"}


def edit_post_form(args: JobId, token: str, http: Http) -> dict[str, Any]:
    p = get_tools("job", f"/jobs/{args.job_id}", {}, token, http)
    fields = [
        field("title", "Job title", "text", required=True, max=120, value=p["title"]),
        field("company", "Company", "text", required=True, max=120, value=p["company"]),
        field("employment_type", "Type", "select", required=True, options=EMPLOYMENT, value=p["employment_type"]),
        field("location", "Location", "text", max=120, value=p.get("location", "")),
        field("remote", "Remote", "checkbox", value=bool(p.get("remote"))),
        field("salary_min", "Salary from", "number", min=0, value=p.get("salary_min")),
        field("salary_max", "Salary to", "number", min=0, value=p.get("salary_max")),
        field("description", "Description", "textarea", max=5000, value=p.get("description", "")),
        field("tags", "Tags", "tags", value=p.get("tags", [])),
        field("status", "State", "select", required=True, options=JOB_STATES, value=p.get("status", "open")),
    ]
    return form_card("jobs.editpost", f"Edit job #{args.job_id}", fields, {"job_id": args.job_id}, "Save")


def edit_post(args: EditPost, token: str, http: Http) -> dict[str, Any]:
    body = args.model_dump(exclude_none=True, exclude={"job_id"})
    write("job", f"/jobs/{args.job_id}", body, token, http, method="PATCH")
    return {"type": "done", "summary": f"Saved job #{args.job_id}", "href": "/job/employer"}


def remove_post(args: JobId, token: str, http: Http) -> dict[str, Any]:
    write("job", f"/jobs/{args.job_id}", {}, token, http, method="DELETE")
    return {"type": "done", "summary": f"Removed job #{args.job_id} and its applications"}


register(
    Tool("jobs.job", JobId, False, job_detail),
    Tool("jobs.withdraw", Withdraw, True, withdraw, lambda a: f"Withdraw application #{a.application_id}"),  # type: ignore[attr-defined]
    Tool("jobs.editpost", EditPost, True, edit_post, lambda a: f"Save the changes to job #{a.job_id}", form=edit_post_form, opening=JobId),  # type: ignore[attr-defined]
    Tool("jobs.removepost", JobId, True, remove_post, lambda a: f"Remove job #{a.job_id} for good"),  # type: ignore[attr-defined]
)

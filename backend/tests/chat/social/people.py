"""The people of the tests of the chat that need them (rows of `users`, as the social routes of the mounted app read them)."""

from sn_shared.testing import add_person


def join(client, uid, name, **profile):
    """Make `name` one of the people: a row of `users` (the profile of the account), with what it shows to others: every part given
    here is public, except the summary, which is for friends unless `summary_public` says so."""
    fields = {
        "name": profile.get("display_name"), "headline": profile.get("headline"), "region": profile.get("region"),
        "summary": profile.get("summary"), "avatar_url": profile.get("avatar"),
    }
    parts = {"name": "display_name", "headline": "headline", "location": "region", "avatar": "avatar"}
    visibility = {part: "public" for part, key in parts.items() if profile.get(key)}
    if profile.get("summary_public"):
        visibility["summary"] = "public"
    add_person(client.app.state.session_factory, uid, name, visibility=visibility, **{k: v for k, v in fields.items() if v})
    return {"user_id": uid, "username": name}


def make_people(client):
    for uid, name in ((1, "alice"), (2, "bob"), (3, "carol")):
        join(client, uid, name)

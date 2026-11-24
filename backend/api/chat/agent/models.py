"""What the agent knows about a virtual person: who they are in a story and how they speak.

It is read from `users` of center when the agent is asked to reply (a virtual person is a row there: `persona_role`, `speaking_style`
and the public profile), so nothing is kept here to be kept up to date.
"""

from dataclasses import dataclass, field

from sn_shared.directory import Person


@dataclass(frozen=True)
class Persona:
    user_id: int
    username: str
    display_name: str = ""
    role: str = ""  # who they are in a story
    style: str = ""  # how they speak
    headline: str = ""
    region: str = ""
    interests: list[str] = field(default_factory=list)


def persona_of(person: Person) -> Persona:
    """The script of a virtual person, from their row of `users`."""
    view = person.view()
    return Persona(
        user_id=person.user_id, username=person.username, display_name=view.display_name, role=(person.persona_role or "").strip(),
        style=(person.speaking_style or "").strip(), headline=view.headline, region=view.region, interests=view.interests,
    )

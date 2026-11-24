"""Tags: the words a thing is found by. The rules (length, characters, how many, how they are cleaned) are the same for every kind
of thing; each module keeps its own tags in its own row (a JSON list), so there is no table here.
"""

import re
from collections.abc import Iterable

TAG_MAX = 30
MAX_TAGS = 10
TAG_PATTERN = r"^[a-z0-9][a-z0-9 +#._-]*$"  # lower case: letters, digits, spaces and + # . _ - (c++, c#, .net, machine learning)
TAG_QUERY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9 +#._-]*$"  # what may be asked for: the case is mended when it is looked up


def clean_tag(value: str) -> str:
    """A tag as it is kept: trimmed, lower case. Raises ValueError when it is not a tag."""
    tag = value.strip().lower()
    if not tag or len(tag) > TAG_MAX or not re.fullmatch(TAG_PATTERN, tag):
        raise ValueError(f"A tag is up to {TAG_MAX} letters, digits, spaces or + # . _ -")
    return tag


def clean_tags(values: Iterable[str]) -> list[str]:
    """The tags without repeats, in the order given."""
    return list(dict.fromkeys(clean_tag(value) for value in values))

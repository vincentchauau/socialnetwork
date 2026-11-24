"""The columns every app writes the same way, so a person is one shape in every table.

A table that keeps who did something holds the id (`user_id`, or `<role>_id`: `owner_id`, `seller_id`...) and a copy of the name beside it
(`username`, or `<role>_username`): the name is a copy of `users.username`, which is at most `USERNAME_MAX` characters, so the copy has the
same room. The copy is kept up to date by the account events of each app.
"""

from typing import Annotated

from sqlalchemy import Integer, String
from sqlalchemy.orm import mapped_column

USERNAME_MAX = 32  # the length of `users.username`

UserId = Annotated[int, mapped_column(Integer)]
Username = Annotated[str, mapped_column(String(USERNAME_MAX))]

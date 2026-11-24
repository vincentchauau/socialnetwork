"""The social side of the platform: who is whose friend, who blocked whom, reports, notifications, and the virtual people a person drew.

The tables (`social_*`) and the rules live here because two apps need them: `social` (the pages and the routes of the people) and `chat` (a message
to somebody is refused when one blocked the other, a chat of two opens at once between friends, a virtual person drawn is a companion).
A person is a row of `users` of center, read through `sn_shared.directory`: nothing here keeps a copy of one.
"""

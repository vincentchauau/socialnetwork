"""Phone numbers: strict E.164 normalisation, allow-list and masking (a full number is never logged)."""

import re

import logging
logger = logging.getLogger(__name__)

E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
STRIP = re.compile(r"[ \-]")


# Premium-rate / satellite / revenue-share ranges abused for SMS toll fraud: never sent to.
# This is a floor, not a policy: the operator must still choose countries with SMS_ALLOWED_PREFIXES.
DENIED_PREFIXES = frozenset({
    "+882", "+883", "+878", "+979", "+881", "+870", "+871", "+872", "+873", "+874",
    "+1900", "+1976", "+1809", "+1829", "+1849", "+1876", "+1284", "+1473", "+1649", "+1664", "+1758",
})


def normalize_phone(raw: str, allowed_prefixes: tuple[str, ...] = ()) -> str | None:
    """`+84 912-345-621` -> `+84912345621`; None when it is not E.164 or not in the allow-list."""
    try:
        value = STRIP.sub("", raw or "")
        if not E164.fullmatch(value) or value.startswith(tuple(DENIED_PREFIXES)):
            return None
        if allowed_prefixes and not value.startswith(allowed_prefixes):
            return None
        return value
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("normalize_phone failed")
        raise


def mask_phone(phone: str | None) -> str:
    """`+84912345621` -> `+84*******21`: the country code and the last two digits only."""
    try:
        if not phone or not phone.startswith("+") or len(phone) < 6:
            return "***"
        return f"{phone[:3]}{'*' * (len(phone) - 5)}{phone[-2:]}"
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("mask_phone failed")
        raise


def log_phone(phone: str | None) -> str:
    """For log lines: every digit but the last two is hidden."""
    try:
        if not phone or len(phone) < 4:
            return "***"
        return "*" * (len(phone) - 2) + phone[-2:]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("log_phone failed")
        raise

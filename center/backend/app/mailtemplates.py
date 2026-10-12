"""One short Vietnamese template per event, as plain text and minimal HTML.

Every interpolated value is HTML-escaped in the HTML body. A code is never part of a link.
"""

from dataclasses import dataclass
from html import escape

APP_NAME = "Mạng xã hội"
LINE_BREAK = chr(10)
IGNORE = "Nếu không phải bạn, hãy bỏ qua email này."
SECURITY_TIP = "Nếu không phải bạn thực hiện, hãy đổi mật khẩu ngay và kiểm tra các phương thức đăng nhập trong tài khoản."


@dataclass(frozen=True)
class Rendered:
    subject: str
    text: str
    html: str


# kind -> (subject, what happened). Security notices only; the link mails are built below.
EVENTS: dict[str, tuple[str, str]] = {
    "password_changed": ("Mật khẩu của bạn đã được đổi", "Mật khẩu tài khoản {username} vừa được đổi."),
    "password_reset": (
        "Mật khẩu của bạn đã được đặt lại",
        "Mật khẩu tài khoản {username} vừa được đặt lại và mọi phiên đăng nhập đã bị đăng xuất.",
    ),
    "email_changed": (
        "Email đăng nhập của bạn đã thay đổi",
        "Email của tài khoản {username} vừa được đổi sang {new_email}. Địa chỉ này không còn gắn với tài khoản.",
    ),
    "email_removed": ("Email đã được gỡ khỏi tài khoản", "Email của tài khoản {username} vừa được gỡ."),
    "passkey_added": ("Đã thêm một passkey", "Một passkey vừa được thêm vào tài khoản {username}."),
    "passkey_removed": ("Đã xóa một passkey", "Một passkey vừa bị xóa khỏi tài khoản {username}."),
    "google_linked": ("Đã liên kết tài khoản Google", "Tài khoản Google vừa được liên kết với tài khoản {username}."),
    "google_unlinked": ("Đã hủy liên kết Google", "Liên kết Google của tài khoản {username} vừa bị gỡ."),
    "voice_added": ("Đã bật đăng nhập bằng giọng nói", "Đăng nhập bằng giọng nói vừa được bật cho tài khoản {username}."),
    "voice_removed": ("Đã tắt đăng nhập bằng giọng nói", "Đăng nhập bằng giọng nói của tài khoản {username} vừa bị gỡ."),
    "webcam_added": ("Đã bật đăng nhập bằng khuôn mặt", "Đăng nhập bằng khuôn mặt vừa được bật cho tài khoản {username}."),
    "webcam_removed": ("Đã tắt đăng nhập bằng khuôn mặt", "Đăng nhập bằng khuôn mặt của tài khoản {username} vừa bị gỡ."),
    "totp_enabled": ("Đã bật xác thực hai bước", "Xác thực hai bước bằng ứng dụng đã được bật cho tài khoản {username}."),
    "totp_disabled": (
        "Đã tắt xác thực hai bước",
        "Xác thực hai bước bằng ứng dụng của tài khoản {username} vừa bị tắt và mọi phiên đăng nhập khác đã bị đăng xuất.",
    ),
    "recovery_codes_regenerated": (
        "Đã tạo lại mã khôi phục",
        "Bộ mã khôi phục mới vừa được tạo cho tài khoản {username}; các mã cũ không còn dùng được.",
    ),
    "recovery_code_used": (
        "Một mã khôi phục đã được sử dụng",
        "Một mã khôi phục vừa được dùng để đăng nhập vào tài khoản {username}.",
    ),
    "account_deleted": ("Tài khoản của bạn đã bị xóa", "Tài khoản {username} vừa được xóa cùng toàn bộ dữ liệu."),
}

_LINK_MAILS: dict[str, tuple[str, str, str]] = {
    "verify": (
        "Xác minh địa chỉ email của bạn",
        "Nhấn vào liên kết để xác minh email (có hiệu lực 24 giờ):",
        "Hoặc nhập mã xác minh này trong tài khoản:",
    ),
    "login": (
        "Đăng nhập bằng email",
        "Nhấn vào liên kết để đăng nhập (có hiệu lực 15 phút):",
        "Hoặc nhập mã đăng nhập này:",
    ),
    "reset": (
        "Đặt lại mật khẩu",
        "Nhấn vào liên kết để đặt mật khẩu mới (có hiệu lực 30 phút):",
        "",
    ),
}


def _page(body: str) -> str:
    return f"<!doctype html><html><body><h2>{escape(APP_NAME)}</h2>{body}</body></html>"


def _p(text: str) -> str:
    return f"<p>{escape(text)}</p>"


def _link_mail(kind: str, link: str, code: str | None) -> Rendered:
    subject, intro, code_intro = _LINK_MAILS[kind]
    text = [intro, link]
    body = _p(intro) + f'<p><a href="{escape(link, quote=True)}">{escape(link)}</a></p>'
    if code:
        text += ["", code_intro, code]
        body += _p(code_intro) + f"<p><strong>{escape(code)}</strong></p>"
    text += ["", IGNORE]
    body += _p(IGNORE)
    return Rendered(subject=f"{subject} - {APP_NAME}", text=LINE_BREAK.join(text), html=_page(body))


def _notice(kind: str, **ctx: str) -> Rendered:
    subject, template = EVENTS[kind]
    values = {"username": "", "new_email": "", **ctx}
    what = template.format(**values)
    text = f"{what}\n\n{SECURITY_TIP}"
    escaped = {k: escape(str(v)) for k, v in values.items()}
    html = _page(f"<p>{template.format(**escaped)}</p>" + _p(SECURITY_TIP))
    return Rendered(subject=f"{subject} - {APP_NAME}", text=text, html=html)


def render(kind: str, **ctx: str | None) -> Rendered:
    """`verify`/`login`/`reset` need `link` (and `code` for verify/login); the others are notices."""
    if kind in _LINK_MAILS:
        return _link_mail(kind, str(ctx["link"]), ctx.get("code"))
    return _notice(kind, **{k: str(v) for k, v in ctx.items() if v is not None})

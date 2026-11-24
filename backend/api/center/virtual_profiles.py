"""The made-up life of each virtual person: the same name always gets the same profile (no clock, no global random state)."""

import random
from datetime import date

SEED = 20241018  # changing it changes who is in the pool and their lives: never do it on a live database

PLACES = (
    ("Hà Nội", "Miền Bắc"), ("Hải Phòng", "Miền Bắc"), ("Huế", "Miền Trung"), ("Đà Nẵng", "Miền Trung"),
    ("Nha Trang", "Miền Trung"), ("Đà Lạt", "Tây Nguyên"), ("TP.HCM", "Miền Nam"), ("Cần Thơ", "Miền Nam"),
)  # fmt: skip
INTERESTS = (
    "đọc sách", "nấu ăn", "chạy bộ", "bóng đá", "cầu lông", "leo núi", "chụp ảnh", "vẽ", "âm nhạc", "guitar", "phim", "cà phê",
    "du lịch", "làm vườn", "cờ vua", "board game", "lập trình", "học tiếng Anh", "đầu tư", "yoga", "nuôi mèo", "nuôi chó",
    "thủ công", "viết lách", "podcast", "xe đạp", "bơi lội", "thiền",
)  # fmt: skip
# (role in a story, a title for the headline, skills)
ROLES = (
    ("bạn đồng hành thân thiện, hay hỏi thăm", "Bạn trò chuyện", ("lắng nghe", "kể chuyện")),
    ("gia sư tiếng Anh kiên nhẫn", "Gia sư tiếng Anh", ("tiếng Anh", "giảng dạy")),
    ("người bán hàng biết mặc cả", "Người bán hàng", ("thương lượng", "bán hàng")),
    ("người mua hàng kỹ tính", "Người mua hàng", ("thương lượng", "so sánh giá")),
    ("nhà tuyển dụng hỏi phỏng vấn", "Nhà tuyển dụng", ("phỏng vấn", "nhân sự")),
    ("ứng viên đang tìm việc", "Ứng viên", ("giao tiếp", "làm việc nhóm")),
    ("bạn cùng chơi game, thích thắng", "Người chơi", ("chiến thuật", "board game")),
    ("người bạn bàn việc, hay đặt câu hỏi", "Cố vấn", ("lập kế hoạch", "phản biện")),
)  # fmt: skip
STYLES = (
    "vui vẻ, hay đùa", "ngắn gọn, thẳng thắn", "nhẹ nhàng, chậm rãi", "nhiệt tình, nhiều cảm thán", "điềm đạm, lịch sự",
    "hóm hỉnh, hay chơi chữ", "trang trọng, chu đáo", "thân mật như bạn lâu năm",
)  # fmt: skip
YEARS = (1978, 2004)  # born between: always an adult


def profile_for(username: str) -> dict[str, object]:
    """The profile columns of one virtual person, a pure function of the name."""
    rng = random.Random(f"{SEED}:{username.lower()}")
    city, region = rng.choice(PLACES)
    role, title, skills = rng.choice(ROLES)
    likes = rng.sample(INTERESTS, 3)
    return {
        "name": username.replace("_", " "),
        "birth_date": date(rng.randint(*YEARS), rng.randint(1, 12), rng.randint(1, 28)),
        "city": city, "region": region, "country": "Việt Nam",
        "headline": f"{title} ở {city}",
        "summary": f"Tôi thích {likes[0]}, {likes[1]} và {likes[2]}. Rất vui được làm quen.",
        "interests": likes,
        "skills": [{"name": skill} for skill in skills],
        "languages": [{"language": "Tiếng Việt", "proficiency": "native"}],
        "persona_role": role,
        "speaking_style": rng.choice(STYLES),
    }  # fmt: skip

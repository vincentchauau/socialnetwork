"""The talk and the games of the demo: chat rooms with their conversations, and the finished games of the Werewolf.

Messages are `(who, minutes after the room began, text)`: `who` is the position of a member of the room (0 is the owner).
"""

# (slug, title, description, category, region, messages)
ROOMS = (
    ("ca-phe-sang", "Cà phê sáng thứ Hai", "Nơi chia sẻ một ly cà phê và kế hoạch cho tuần mới.", "đời sống", "Hà Nội", (
        (0, 0, "Chào cả nhà, tuần mới vui vẻ nhé! Hôm nay mình thử cà phê rang xay Cầu Đất, thơm lắm."),
        (1, 4, "Nghe hấp dẫn quá. Bạn pha bằng phin hay máy?"),
        (0, 6, "Phin inox thôi, 4 phút là đủ. Nước 92 độ, đừng đổ sôi hẳn."),
        (2, 11, "Mình thì vẫn giữ thói quen cà phê sữa đá. Tuần này có ai đi họp lớp không?"),
        (3, 15, "Mình đi! Thứ Sáu 7 giờ tối ở quán quen nhé."),
        (1, 17, "Thứ Sáu thì mình kẹt dự án, để mình sắp xếp rồi báo lại."),
        (4, 22, "Ai đang tìm chỗ làm việc yên tĩnh ở Cầu Giấy không? Mình biết một quán có ổ cắm đầy đủ."),
        (2, 25, "Cho mình xin địa chỉ với, tuần sau mình đi thử."),
        (4, 27, "Ngõ 120 Trần Thái Tông, quán có cây hoa giấy ở cửa."),
        (0, 33, "Cảm ơn bạn. Chúc mọi người một tuần nhiều năng lượng!"),
    )),
    ("hoc-python", "Học Python cùng nhau", "Hỏi đáp, chia sẻ bài tập và tài liệu Python cho người mới.", "học tập", "Online", (
        (0, 0, "Chào mừng các bạn. Tuần này chúng ta ôn vòng lặp và hàm, ai có bài tập thì đăng lên nhé."),
        (1, 5, "Cho mình hỏi: khác nhau giữa list và tuple dùng khi nào ạ?"),
        (0, 8, "Tuple không sửa được sau khi tạo, hợp cho dữ liệu cố định như toạ độ (x, y). List dùng khi cần thêm bớt."),
        (2, 12, "Mình hay quên `enumerate`. Dùng `for i, x in enumerate(items)` là gọn nhất."),
        (3, 14, "Mình bị lỗi IndentationError mãi mà không thấy chỗ sai, ai xem giúp được không?"),
        (0, 16, "Bạn gửi đoạn code lên đây nhé, thường là lẫn tab với dấu cách."),
        (3, 19, "Đúng rồi, mình đã đổi hết sang 4 dấu cách và chạy được. Cảm ơn thầy!"),
        (4, 24, "Có khoá SQL cơ bản nào miễn phí không mọi người? Mình muốn học tiếp sau Python."),
        (1, 26, "Trong mục Learning có khoá SQL và cơ sở dữ liệu quan hệ cho người mới đó bạn."),
        (4, 28, "Mình thấy rồi, đăng ký ngay. Cảm ơn!"),
        (2, 35, "Cuối tuần mình tổ chức buổi giải bài cùng nhau, ai muốn tham gia thì thả tim nhé."),
    )),
    ("cho-thu-cong", "Chợ đồ thủ công", "Mua bán, trao đổi đồ handmade: gốm, vải, nến thơm, tranh thêu.", "mua bán", "Toàn quốc", (
        (0, 0, "Đầu tuần mình có thêm lô nến thơm sáp đậu nành mùi sả chanh, ai cần nhắn mình nhé."),
        (1, 7, "Nến cháy được bao lâu một cây vậy bạn?"),
        (0, 9, "Khoảng 35 giờ cho loại 200g. Sáp đậu nành nên ít khói và không độc."),
        (2, 15, "Bộ ấm trà gốm Bát Tràng của shop còn hàng không ạ?"),
        (3, 18, "Mình mới nhập thêm, có cả men rạn và men ngọc."),
        (2, 20, "Cho mình đặt một bộ men rạn, giao về Đà Nẵng được không?"),
        (3, 22, "Được bạn nhé, phí ship 30 nghìn, hàng bọc xốp chống vỡ hai lớp."),
        (4, 30, "Tranh lụa thêu tay cảnh làng quê của mình vừa hoàn thành, mình sẽ đăng ảnh vào mục Market."),
        (1, 34, "Mong được xem tranh! Ngày trước mình rất thích các làng nghề."),
    )),
    ("tim-viec-it", "Tìm việc IT", "Chia sẻ tin tuyển dụng, kinh nghiệm phỏng vấn và viết CV.", "việc làm", "TP.HCM", (
        (0, 0, "Công ty mình đang tuyển Backend Python, làm tại quận 1, thông tin chi tiết ở mục Jobs."),
        (1, 6, "Yêu cầu kinh nghiệm bao nhiêu năm vậy anh?"),
        (0, 8, "Từ 2 năm, biết FastAPI và PostgreSQL là lợi thế."),
        (2, 12, "Mình mới học xong khoá SQL, chưa có kinh nghiệm thực tế, có nên nộp thử không?"),
        (0, 14, "Cứ nộp, kèm các dự án nhỏ trên GitHub. Nhà tuyển dụng thích người chủ động học."),
        (3, 19, "Mẹo phỏng vấn: chuẩn bị ba câu chuyện thật về lỗi từng gặp và cách bạn sửa."),
        (4, 24, "Mình hay bí khi được hỏi điểm yếu. Mọi người trả lời thế nào?"),
        (3, 27, "Nói một điểm yếu thật nhưng đang cải thiện, ví dụ ngại trình bày, và bạn đang luyện nói ở câu lạc bộ."),
        (1, 31, "Cảm ơn mọi người, mình sẽ cập nhật CV theo gợi ý rồi nộp vào cuối tuần."),
    )),
    ("anh-dep-quanh-ta", "Ảnh đẹp quanh ta", "Chia sẻ ảnh chụp, góc phố, cảnh biển và kỹ thuật chụp.", "sở thích", "Miền Trung", (
        (0, 0, "Mình vừa đi Kỳ Co, nước biển xanh như ngọc. Đã đăng vài tấm vào Photos."),
        (1, 5, "Xem ảnh hải đăng mà muốn đi ngay. Bạn chụp bằng máy hay điện thoại?"),
        (0, 7, "Máy mirrorless, ống kính 24-70. Giờ vàng buổi chiều là đẹp nhất."),
        (2, 13, "Mình mới tập chụp đen trắng cho phố cổ, cảm giác ảnh có chiều sâu hơn."),
        (3, 16, "Đen trắng hợp với chân dung người lao động. Bạn thử chụp xích lô xem."),
        (2, 18, "Hay quá, cuối tuần mình sẽ thử ở phố cổ Hội An."),
        (4, 22, "Ai có mẹo chỉnh ảnh nhanh trên điện thoại không?"),
        (1, 25, "Tăng nhẹ độ tương phản và hạ điểm sáng, đừng lạm dụng bộ lọc là đẹp rồi."),
    )),
    ("ma-soi-toi-thu-sau", "Ma Sói tối thứ Sáu", "Hẹn nhau chơi Ma Sói mỗi tối thứ Sáu, vai nào cũng chơi.", "trò chơi", "Online", (
        (0, 0, "Tối nay 9 giờ mình mở phòng Ma Sói, đủ 8 người thì bắt đầu."),
        (1, 3, "Mình tham gia! Lần trước làm Sói mà bị lộ ngay ở ngày đầu."),
        (2, 5, "Vì bạn cười lớn khi bị hỏi. Lần này nhớ giữ mặt nghiêm."),
        (3, 8, "Mình xin làm Tiên tri được không? Mấy ván trước toàn làm dân thường."),
        (0, 10, "Vai chia ngẫu nhiên nhé, ai may mắn thì được. Nhớ vào phòng đúng giờ."),
        (4, 14, "Cho mình thêm một chỗ nhé, rủ thêm một bạn nữa."),
        (0, 16, "Ok, nhưng phòng tối đa 12 người. Hẹn gặp tối nay!"),
    )),
    ("hoc-tieng-anh", "Luyện tiếng Anh mỗi ngày", "Mỗi ngày một câu, sửa lỗi cho nhau, nói chuyện bằng tiếng Anh.", "học tập", "Online", (
        (0, 0, "Daily sentence: \"I'm looking forward to hearing from you.\" Hãy đặt một câu của bạn nhé."),
        (1, 4, "I'm looking forward to joining the English club this weekend."),
        (0, 6, "Perfect! Chỉ cần thêm \"the\" trước \"English club\" nếu nói về câu lạc bộ cụ thể, bạn viết đúng rồi."),
        (2, 10, "I look forward meeting new friends here. Is it right?"),
        (0, 12, "Gần đúng: \"I look forward to meeting new friends here.\" Sau \"look forward to\" dùng danh động từ."),
        (3, 17, "Cảm ơn thầy, mình nhớ rồi. Mai mình có thể thử gọi video để luyện nói không?"),
        (0, 19, "Được, tối mai 8 giờ mình mở cuộc họp trong phòng này."),
    )),
    ("clb-chay-bo", "Câu lạc bộ chạy bộ", "Rủ nhau chạy buổi sáng, chia sẻ lộ trình và kinh nghiệm tập luyện.", "thể thao", "Hà Nội", (
        (0, 0, "Sáng Chủ nhật chạy quanh Hồ Tây, tập trung 5 giờ 30 ở cổng công viên nước nhé."),
        (1, 4, "Đi bao nhiêu cây số vậy anh? Em mới chạy được 5 km."),
        (0, 6, "Một vòng hồ là 17 km, ai chạy 5 km thì quay lại sớm, không sao cả."),
        (2, 11, "Mình hay bị đau gối khi chạy xa, có mẹo nào không?"),
        (3, 13, "Chọn giày đúng cỡ và tăng quãng đường từ từ, mỗi tuần không quá 10%."),
        (4, 17, "Nhớ mang theo nước và một ít chuối nhé mọi người."),
        (1, 20, "Em đăng ký tham gia, hẹn gặp mọi người sáng Chủ nhật!"),
    )),
)

# (code, winner, days, [(role code, outcome, survived, days survived)], minutes the game lasted ago)
GAMES = (
    ("WW4A7K", "VILLAGER", 4, (("W:K", "lost", False, 3), ("W:K", "lost", False, 4), ("V:SF", "won", True, 4), ("V:N", "won", True, 4), ("V:N", "won", False, 2), ("V:BE", "won", True, 4), ("V:N", "won", True, 4)), 3),
    ("WW9C2M", "WOLF", 3, (("W:K", "won", True, 3), ("W:K", "won", True, 3), ("V:SF", "lost", False, 2), ("V:N", "lost", False, 1), ("V:N", "lost", False, 2), ("V:BE", "lost", False, 3)), 5),
    ("WW1D8P", "VILLAGER", 5, (("W:K", "lost", False, 4), ("V:SF", "won", True, 5), ("V:N", "won", True, 5), ("V:N", "won", False, 3), ("V:BE", "won", True, 5), ("V:N", "won", True, 5), ("W:K", "lost", False, 5), ("V:N", "won", True, 5)), 9),
    ("WW6E3R", "WOLF", 4, (("W:K", "won", True, 4), ("V:SF", "lost", False, 3), ("V:N", "lost", False, 2), ("V:N", "lost", False, 4), ("V:N", "lost", False, 1), ("W:K", "won", True, 4)), 12),
    ("WW2F5T", "VILLAGER", 3, (("W:K", "lost", False, 2), ("V:SF", "won", True, 3), ("V:N", "won", True, 3), ("V:N", "won", True, 3), ("V:BE", "won", False, 2)), 16),
    ("WW8H1V", "DRAW", 6, (("W:K", "draw", True, 6), ("V:SF", "draw", True, 6), ("V:N", "draw", False, 4), ("V:N", "draw", True, 6)), 21),
    ("WW3J9X", "WOLF", 3, (("W:K", "won", True, 3), ("W:K", "won", True, 3), ("V:N", "lost", False, 2), ("V:N", "lost", False, 1), ("V:SF", "lost", False, 3), ("V:N", "lost", False, 2), ("V:BE", "lost", False, 2)), 27),
    ("WW5K6Z", "VILLAGER", 4, (("W:K", "lost", False, 4), ("V:SF", "won", True, 4), ("V:N", "won", True, 4), ("V:N", "won", True, 4), ("V:N", "won", False, 3), ("V:BE", "won", True, 4)), 33),
)

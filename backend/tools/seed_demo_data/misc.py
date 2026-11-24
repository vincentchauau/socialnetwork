"""Demo words for face notes, reports, videos and searchable documents (Vietnamese)."""

# (symmetry, eye, nose, mouth, ear, angle, note); three people, oldest reading first
FACE_SERIES = [
    [
        (82, 85, 80, 78, 84, 4.5, "Đo buổi sáng, ánh sáng cửa sổ"),
        (84, 86, 82, 79, 85, 3.8, ""),
        (86, 88, 83, 82, 85, 3.1, "Ngủ đủ giấc nên mặt thư giãn hơn"),
        (85, 87, 84, 81, 86, 2.9, "Đo sau khi tập thể dục"),
    ],
    [
        (74, 76, 72, 70, 75, 9.2, "Lần đầu thử, camera hơi nghiêng"),
        (78, 80, 75, 74, 77, 6.4, "Đã chỉnh lại góc máy"),
        (80, 82, 77, 76, 79, 5.0, ""),
    ],
    [
        (90, 91, 88, 87, 92, 1.8, "Ánh sáng đèn bàn, ngồi thẳng lưng"),
        (88, 90, 86, 85, 90, 2.4, ""),
        (91, 92, 89, 88, 93, 1.5, "Kết quả tốt nhất tuần này"),
    ],
]

# (reason, details, status, target kind); the targets are real people, messages or rooms
REPORTS = [
    ("spam", "Liên tục gửi liên kết quảng cáo vào nhiều phòng trò chuyện.", "open", "user"),
    ("abuse", "Dùng lời lẽ xúc phạm trong cuộc trò chuyện nhóm.", "reviewed", "message"),
    ("impersonation", "Hồ sơ dùng ảnh và tên giống một người quen của tôi.", "actioned", "user"),
    ("other", "Phòng có nội dung bán hàng không liên quan đến chủ đề đã đặt.", "open", "room"),
]

VIDEO_JOBS = [
    {
        "prompt": "Video 30 giây giới thiệu cách pha cà phê phin đúng điệu cho người mới",
        "topic": "cach_pha_ca_phe_phin",
        "stories": [
            "[CAMERA: close-up] [VISUALS: Bàn tay đặt phin lên miệng ly, rót nước sôi tráng phin] [AUDIO: Narrator says: \"Bắt đầu bằng việc tráng phin cho nóng.\"]",
            "[CAMERA: overhead] [VISUALS: Cho 20 gram cà phê xay vào phin, lắc nhẹ cho phẳng] [AUDIO: Narrator says: \"Hai mươi gram cà phê, nén nhẹ tay.\"]",
            "[CAMERA: slow push-in] [VISUALS: Nước nóng chảy qua nắp phin, từng giọt nhỏ xuống ly] [AUDIO: Narrator says: \"Rót 30 ml nước để ủ, đợi một phút.\"]",
            "[CAMERA: wide establishing shot] [VISUALS: Ly cà phê nâu sánh đặt cạnh cửa sổ buổi sáng] [AUDIO: Narrator says: \"Chậm rãi, và bạn có ly cà phê trọn vị.\"]",
        ],
        "subtitles": ["Bắt đầu bằng việc tráng phin cho nóng.", "Hai mươi gram cà phê, nén nhẹ tay.", "Rót 30 ml nước để ủ, đợi một phút.", "Chậm rãi, và bạn có ly cà phê trọn vị."],
    },
    {
        "prompt": "Giới thiệu nhanh một ngày làm việc của lập trình viên backend",
        "topic": "mot_ngay_cua_lap_trinh_vien_backend",
        "stories": [
            "[CAMERA: wide establishing shot] [VISUALS: Văn phòng buổi sáng, ly cà phê cạnh bàn phím] [AUDIO: Narrator says: \"Một ngày bắt đầu bằng việc đọc nhật ký lỗi.\"]",
            "[CAMERA: over-the-shoulder] [VISUALS: Màn hình hiển thị mã Python và kết quả kiểm thử] [AUDIO: Narrator says: \"Viết tính năng mới cùng bộ kiểm thử đi kèm.\"]",
            "[CAMERA: tracking shot] [VISUALS: Nhóm đứng quanh bảng trắng vẽ sơ đồ hệ thống] [AUDIO: Narrator says: \"Cuộc họp ngắn để cùng chốt hướng giải quyết.\"]",
            "[CAMERA: slow pull-out] [VISUALS: Triển khai thành công, các chỉ số xanh trên màn hình] [AUDIO: Narrator says: \"Và đưa mọi thứ lên chạy ổn định.\"]",
        ],
        "subtitles": ["Một ngày bắt đầu bằng việc đọc nhật ký lỗi.", "Viết tính năng mới cùng bộ kiểm thử đi kèm.", "Cuộc họp ngắn để cùng chốt hướng giải quyết.", "Và đưa mọi thứ lên chạy ổn định."],
    },
    {
        "prompt": "Clip giới thiệu một quán cà phê nhỏ ở phố cổ Hà Nội vào buổi chiều mưa",
        "topic": "quan_ca_phe_pho_co_chieu_mua",
        "stories": [
            "[CAMERA: low angle] [VISUALS: Biển hiệu gỗ của quán, những giọt mưa rơi trên mái ngói] [AUDIO: Narrator says: \"Chiều mưa, ghé quán nhỏ trong ngõ.\"]",
            "[CAMERA: close-up] [VISUALS: Hơi nóng bốc lên từ tách cà phê trứng] [AUDIO: Narrator says: \"Tách cà phê trứng béo ngậy, ngọt dịu.\"]",
            "[CAMERA: tracking shot] [VISUALS: Khách ngồi đọc sách bên cửa sổ nhìn ra phố] [AUDIO: Narrator says: \"Ở đây, thời gian như chậm lại.\"]",
            "[CAMERA: overhead] [VISUALS: Bàn gỗ với sổ tay, bút và ly cà phê] [AUDIO: Narrator says: \"Hà Nội, một chiều như thế.\"]",
        ],
        "subtitles": ["Chiều mưa, ghé quán nhỏ trong ngõ.", "Tách cà phê trứng béo ngậy, ngọt dịu.", "Ở đây, thời gian như chậm lại.", "Hà Nội, một chiều như thế."],
    },
    {
        "prompt": "Video hướng dẫn 3 mẹo học SQL hiệu quả cho sinh viên",
        "topic": "ba_meo_hoc_sql_hieu_qua",
        "stories": [
            "[CAMERA: wide establishing shot] [VISUALS: Sinh viên ngồi ở thư viện với laptop] [AUDIO: Narrator says: \"Mẹo một: học qua dữ liệu thật mà bạn quan tâm.\"]",
            "[CAMERA: over-the-shoulder] [VISUALS: Màn hình hiển thị câu truy vấn SELECT và kết quả] [AUDIO: Narrator says: \"Mẹo hai: tự viết lại câu truy vấn thay vì chép.\"]",
            "[CAMERA: close-up] [VISUALS: Ghi chú dán trên màn hình về JOIN và GROUP BY] [AUDIO: Narrator says: \"Mẹo ba: ghi lại lỗi gặp phải và cách sửa.\"]",
            "[CAMERA: slow pull-out] [VISUALS: Sinh viên mỉm cười khi truy vấn chạy ra kết quả đúng] [AUDIO: Narrator says: \"Luyện mỗi ngày mười phút là đủ.\"]",
        ],
        "subtitles": ["Mẹo một: học qua dữ liệu thật mà bạn quan tâm.", "Mẹo hai: tự viết lại câu truy vấn thay vì chép.", "Mẹo ba: ghi lại lỗi gặp phải và cách sửa.", "Luyện mỗi ngày mười phút là đủ."],
    },
]

RAG_DOCS = [
    ("huong-dan-nhan-vien-moi.md",
     "# Hướng dẫn dành cho nhân viên mới\n\n## Tuần đầu tiên\nNgày đầu tiên bạn sẽ nhận máy tính, tài khoản email và quyền truy cập vào hệ thống nội bộ. "
     "Người hướng dẫn sẽ dành khoảng một giờ để giới thiệu về cấu trúc phòng ban, quy trình làm việc và các kênh trao đổi chung.\n\n"
     "Trong ba ngày đầu, hãy đọc tài liệu sản phẩm, cài đặt môi trường làm việc và chạy thử dự án mẫu. Nếu gặp khó khăn, bạn có thể nhắn vào kênh hỗ trợ nội bộ; "
     "thời gian phản hồi mục tiêu là trong vòng 30 phút vào giờ hành chính.\n\n## Giờ làm việc và nghỉ phép\nGiờ làm việc từ 8 giờ 30 đến 17 giờ 30, nghỉ trưa một giờ. "
     "Mỗi nhân viên có 12 ngày phép năm, tăng thêm một ngày sau mỗi ba năm làm việc. Đơn xin nghỉ phép cần được gửi cho quản lý trực tiếp ít nhất ba ngày làm việc trước ngày nghỉ, trừ trường hợp khẩn cấp.\n\n"
     "## Làm việc từ xa\nNhân viên chính thức có thể làm việc từ xa tối đa hai ngày mỗi tuần sau khi hết thời gian thử việc. Khi làm từ xa, bạn cần bật mạng riêng ảo của công ty, "
     "có mặt trong các buổi họp nhóm và cập nhật tiến độ vào cuối ngày.\n\n## Chế độ phúc lợi\nCông ty đóng bảo hiểm xã hội, bảo hiểm y tế đúng quy định và tặng thêm gói bảo hiểm sức khỏe tự nguyện. "
     "Mỗi quý có một buổi gặp mặt toàn công ty, và mỗi năm một chuyến du lịch đội nhóm."),
    ("chinh-sach-doi-tra-hang.md",
     "# Chính sách đổi trả hàng của cửa hàng\n\n## Điều kiện đổi trả\nKhách hàng có thể đổi hoặc trả sản phẩm trong vòng 7 ngày kể từ ngày nhận hàng nếu sản phẩm còn nguyên tem, nhãn, chưa qua sử dụng và còn đầy đủ phụ kiện đi kèm. "
     "Sản phẩm thực phẩm đã mở nắp, nến đã thắp và hàng đặt làm riêng theo yêu cầu không áp dụng chính sách này.\n\n"
     "## Cách yêu cầu đổi trả\nHãy vào mục Đơn hàng, chọn đơn cần xử lý và bấm vào nút yêu cầu đổi trả, kèm theo ảnh chụp tình trạng sản phẩm. "
     "Cửa hàng sẽ phản hồi trong vòng 24 giờ làm việc. Nếu yêu cầu được chấp nhận, bạn sẽ nhận được hướng dẫn gửi hàng về.\n\n"
     "## Hoàn tiền\nSau khi nhận và kiểm tra hàng trả về, tiền sẽ được hoàn qua đúng phương thức thanh toán ban đầu trong 3 đến 5 ngày làm việc. "
     "Phí vận chuyển chiều trả do cửa hàng chịu khi sản phẩm bị lỗi hoặc giao sai; trong các trường hợp còn lại, khách hàng chịu phí.\n\n"
     "## Hủy đơn\nĐơn hàng đã thanh toán nhưng chưa giao cho đơn vị vận chuyển có thể hủy bất cứ lúc nào và được hoàn tiền toàn bộ. Đơn đã gửi đi cần chờ nhận hàng rồi làm thủ tục đổi trả."),
    ("ghi-chu-hoc-sql.md",
     "# Ghi chú học SQL\n\n## Thứ tự thực thi của một truy vấn\nDù viết SELECT trước nhưng cơ sở dữ liệu xử lý theo thứ tự: FROM và JOIN, rồi WHERE, GROUP BY, HAVING, SELECT, ORDER BY và cuối cùng là LIMIT. "
     "Hiểu thứ tự này giải thích vì sao không thể dùng bí danh cột trong WHERE nhưng lại dùng được trong ORDER BY.\n\n"
     "## Các lỗi hay gặp\n- Quên điều kiện ON khi JOIN làm số dòng nhân lên bất ngờ.\n- Dùng = NULL thay vì IS NULL nên không bao giờ có kết quả.\n- Đặt điều kiện của bảng bên phải trong WHERE sau LEFT JOIN, vô tình biến nó thành INNER JOIN.\n\n"
     "## Mẹo viết truy vấn dễ đọc\nDùng CTE (WITH) để chia truy vấn lớn thành các bước có tên. Đặt tên bí danh bảng ngắn gọn nhưng có nghĩa. Mỗi mệnh đề một dòng để dễ so sánh khi sửa đổi.\n\n"
     "## Chỉ mục\nChỉ mục B-tree phù hợp với tìm kiếm bằng, so sánh khoảng và sắp xếp. Với truy vấn lọc nhiều cột, thứ tự cột trong chỉ mục ghép rất quan trọng: đặt cột lọc bằng trước, cột khoảng sau. "
     "Luôn kiểm tra bằng EXPLAIN ANALYZE trước khi quyết định thêm chỉ mục mới.\n\n## Giao dịch\nBọc các thay đổi liên quan trong BEGIN và COMMIT để tránh dữ liệu dở dang khi có lỗi giữa chừng."),
]

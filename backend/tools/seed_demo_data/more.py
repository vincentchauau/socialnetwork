"""More demo rows: extra products, extra jobs, the lines of reviews and of private conversations."""

# (name, description, price_cents, stock, category)
PRODUCTS = [
    ("Trà shan tuyết Hà Giang 200g", "Trà hái từ cây cổ thụ vùng Hà Giang, sao thủ công, nước vàng nhạt, hậu ngọt. Hộp giấy kraft kèm hướng dẫn pha.", 1790, 55, "thực phẩm"),
    ("Hạt điều rang muối Bình Phước 500g", "Điều loại một rang củi, vỏ lụa mỏng giòn thơm, đóng hộp thiếc giữ độ giòn đến ba tháng.", 1390, 80, "thực phẩm"),
    ("Nước mắm cá cơm Phú Quốc 500ml", "Nước mắm nhĩ ủ chượp 12 tháng, độ đạm 40, màu cánh gián, vị ngọt hậu, dùng chấm và nêm đều ngon.", 990, 90, "thực phẩm"),
    ("Mứt gừng dẻo handmade 300g", "Gừng tươi thái lát, sên với đường mía, vị cay ấm, hợp pha trà và làm quà Tết.", 790, 60, "thực phẩm"),
    ("Bột nghệ nguyên chất 250g", "Nghệ vàng sấy lạnh xay mịn, không chất phụ gia, dùng nấu ăn hoặc làm mặt nạ.", 590, 100, "thực phẩm"),
    ("Chén sứ men lam vẽ tay (bộ 6)", "Bộ sáu chén sứ trắng vẽ hoa văn lam, nung 1280 độ, an toàn cho lò vi sóng.", 2490, 30, "đồ gia dụng"),
    ("Thớt gỗ nghiến chống mốc", "Thớt gỗ nghiến nguyên tấm dày 3 cm, không cong vênh, đã tẩm dầu thực vật an toàn thực phẩm.", 1590, 45, "đồ gia dụng"),
    ("Khăn trải bàn thổ cẩm Tây Bắc", "Vải thổ cẩm dệt tay của người Thái, hoa văn truyền thống, nhuộm màu tự nhiên, kích thước 140x200 cm.", 2190, 22, "trang trí"),
    ("Đèn lồng Hội An bằng lụa", "Đèn lồng khung tre bọc lụa nhuộm, gấp gọn được, ánh sáng ấm khi thắp bóng LED.", 690, 120, "trang trí"),
    ("Lọ hoa gốm men hỏa biến", "Lọ cao 25 cm, men hỏa biến cho màu độc bản, miệng rộng cắm hoa khô rất đẹp.", 1890, 28, "trang trí"),
    ("Khung ảnh gỗ thông 20x30", "Khung gỗ thông sơn trắng mờ, kính cường lực, đi kèm chân đế và móc treo tường.", 590, 150, "trang trí"),
    ("Áo dài cách tân lụa tơ tằm", "Áo dài cách tân dáng suông, lụa tơ tằm mềm mát, thêu họa tiết sen ở tà, có các cỡ từ S đến L.", 5990, 15, "thời trang"),
    ("Khăn lụa vẽ tay hoa sen", "Khăn lụa 90x90 cm, vẽ tay và hấp màu thủ công, quàng cổ hoặc buộc túi xách.", 1490, 40, "thời trang"),
    ("Dép tông cói đan tay", "Quai vải, đế cói đan chắc chân, nhẹ, thích hợp đi biển và đi trong nhà.", 490, 110, "thời trang"),
    ("Túi đeo chéo da thủ công", "Da bò thuộc thực vật, khóa đồng cổ điển, đựng vừa điện thoại, ví và chìa khóa.", 3290, 20, "thời trang"),
    ("Bút máy ngòi mài nghiêng", "Bút kim loại, ngòi 0.5 mm mài nghiêng viết chữ đẹp, kèm hai ống mực xanh và đen.", 1290, 65, "văn phòng phẩm"),
    ("Bộ ba sổ tay kẻ chấm A6", "Ba cuốn sổ bìa giấy kraft, ruột kẻ chấm 96 trang, gáy lò xo mở phẳng.", 590, 140, "văn phòng phẩm"),
    ("Hộp bút gỗ khắc tên", "Hộp bút gỗ sồi khắc tên theo yêu cầu bằng laser, nắp trượt, đựng khoảng 20 cây bút.", 890, 50, "văn phòng phẩm"),
    ("Sạc dự phòng 10000mAh mỏng", "Pin lithium polymer, cổng USB-C hai chiều, sạc nhanh 18W, mỏng 12 mm vừa túi áo.", 2490, 60, "đồ công nghệ"),
    ("Tai nghe không dây chống ồn", "Kết nối Bluetooth 5.3, chống ồn chủ động, pin 30 giờ, có micro đàm thoại rõ.", 4890, 25, "đồ công nghệ"),
    ("Webcam Full HD tự lấy nét", "Webcam 1080p/30fps, micro kép khử tiếng ồn, nắp che riêng tư, cắm là chạy.", 2890, 35, "đồ công nghệ"),
    ("Đèn bàn LED chống chói", "Ba chế độ màu, điều chỉnh độ sáng vô cấp, cổng sạc USB, bảo vệ mắt khi đọc và làm việc khuya.", 1790, 42, "đồ công nghệ"),
    ("Sách: Python cho người mới bắt đầu", "Giáo trình 300 trang theo từng bài, bài tập cuối chương và đáp án, minh họa bằng dự án nhỏ.", 1390, 70, "sách"),
    ("Sách: Thiết kế cơ sở dữ liệu thực dụng", "Từ mô hình quan hệ đến chỉ mục và giao dịch, kèm ví dụ PostgreSQL cho ứng dụng bán hàng.", 1690, 55, "sách"),
]

REVIEW_TEXTS = {
    5: ("Hàng đúng như mô tả, đóng gói cẩn thận, giao nhanh. Sẽ ủng hộ shop lần sau.", "Chất lượng tuyệt vời so với giá, rất đáng mua.", "Người bán nhiệt tình, sản phẩm đẹp hơn trong ảnh.", "Dùng thích lắm, mình đã mua thêm làm quà cho bạn bè."),
    4: ("Sản phẩm tốt, giao hơi chậm một chút nhưng hài lòng.", "Chất lượng ổn, đúng mô tả, sẽ mua lại.", "Đóng gói kỹ, hàng đẹp, chỉ tiếc màu hơi khác ảnh một chút."),
    3: ("Dùng được, tạm ổn so với giá tiền.", "Hàng bình thường, không tệ nhưng cũng chưa ấn tượng lắm."),
}

# (title, company, department, location, remote, employment type, seniority, min years, [required skills], [preferred skills], (low, high, currency, period), description)
JOBS = [
    ("Kỹ sư DevOps", "Hải Âu Cloud", "Hạ tầng", "Hà Nội", True, "full_time", "senior", 4, ["Docker", "Linux", "Git"], ["PostgreSQL", "Python"], (35_000_000, 55_000_000, "VND", "month"),
     "Hải Âu Cloud vận hành hạ tầng cho hàng trăm doanh nghiệp nhỏ. Bạn sẽ xây dựng quy trình triển khai tự động, giám sát hệ thống và xử lý sự cố cùng đội ngũ."),
    ("Lập trình viên Frontend React", "Mây Trắng Studio", "Sản phẩm", "TP. Hồ Chí Minh", False, "full_time", "mid", 2, ["React", "JavaScript", "Git"], ["Figma", "Thiết kế UI"], (20_000_000, 32_000_000, "VND", "month"),
     "Mây Trắng Studio phát triển ứng dụng đặt lịch cho phòng khám và spa. Bạn sẽ dựng giao diện từ bản thiết kế, phối hợp chặt với nhà thiết kế và backend."),
    ("Chuyên viên phân tích dữ liệu", "Đồng Xanh Analytics", "Dữ liệu", "Đà Nẵng", False, "full_time", "mid", 2, ["SQL", "Excel", "Phân tích dữ liệu"], ["Python", "Thuyết trình"], (18_000_000, 28_000_000, "VND", "month"),
     "Đồng Xanh Analytics xây dựng báo cáo cho chuỗi bán lẻ. Công việc là làm sạch dữ liệu, viết truy vấn và trình bày những phát hiện cho ban điều hành."),
    ("Chuyên viên Marketing số", "Lúa Vàng Media", "Tiếp thị", "Hà Nội", True, "full_time", "junior", 1, ["Marketing số", "SEO", "Content marketing"], ["Excel", "Giao tiếp"], (12_000_000, 20_000_000, "VND", "month"),
     "Lúa Vàng Media thực hiện chiến dịch quảng bá cho thương hiệu thực phẩm sạch. Bạn lên kế hoạch nội dung, chạy quảng cáo và báo cáo hiệu quả hằng tuần."),
    ("Quản lý dự án phần mềm", "Núi Biếc Technology", "Quản lý sản phẩm", "TP. Hồ Chí Minh", False, "full_time", "senior", 5, ["Quản lý dự án", "Scrum", "Giao tiếp"], ["Tiếng Anh", "Làm việc nhóm"], (40_000_000, 60_000_000, "VND", "month"),
     "Núi Biếc Technology cần người dẫn dắt hai dự án cho khách hàng nước ngoài. Bạn lập kế hoạch, điều phối các nhóm và làm việc trực tiếp với khách hàng."),
    ("Thực tập sinh kiểm thử phần mềm", "Sông Hương Digital", "Chất lượng", "Huế", False, "internship", "intern", 0, ["Kiểm thử phần mềm"], ["SQL", "Tiếng Anh"], (4_000_000, 6_000_000, "VND", "month"),
     "Sông Hương Digital tuyển thực tập sinh tham gia kiểm thử ứng dụng di động. Bạn được kèm cặp từ viết kịch bản kiểm thử đến báo cáo lỗi."),
    ("Nhà thiết kế UI/UX", "Hoa Mai Creative", "Thiết kế", "TP. Hồ Chí Minh", True, "contract", "mid", 3, ["Thiết kế UI", "Figma"], ["Giao tiếp", "Thuyết trình"], (25_000_000, 40_000_000, "VND", "month"),
     "Hoa Mai Creative nhận thiết kế sản phẩm cho các thương hiệu thời trang. Hợp đồng sáu tháng, có thể gia hạn, làm việc từ xa với một buổi họp trực tiếp mỗi tuần."),
    ("Nhân viên chăm sóc khách hàng", "Trăng Non Travel", "Dịch vụ", "Nha Trang", False, "full_time", "junior", 0, ["Chăm sóc khách hàng", "Giao tiếp"], ["Tiếng Anh"], (9_000_000, 14_000_000, "VND", "month"),
     "Trăng Non Travel tư vấn tour cho khách trong và ngoài nước. Bạn trả lời yêu cầu, hỗ trợ đặt dịch vụ và chăm sóc khách trong suốt chuyến đi."),
    ("Kỹ sư dữ liệu", "Phù Sa Data", "Nền tảng dữ liệu", "Hà Nội", True, "full_time", "mid", 3, ["Python", "SQL", "PostgreSQL"], ["Docker", "Linux"], (28_000_000, 45_000_000, "VND", "month"),
     "Phù Sa Data xây dựng đường ống dữ liệu cho ngân hàng. Bạn thiết kế quy trình nạp, chuyển đổi và kiểm soát chất lượng dữ liệu hằng ngày."),
    ("Biên tập viên nội dung", "Gió Đông Books", "Nội dung", "Hà Nội", True, "part_time", "junior", 1, ["Content marketing", "Giao tiếp"], ["SEO"], (8_000_000, 12_000_000, "VND", "month"),
     "Gió Đông Books cần người viết và biên tập bài giới thiệu sách, bản tin hằng tuần và nội dung mạng xã hội. Làm việc bán thời gian, linh hoạt giờ giấc."),
    ("Lập trình viên Fullstack", "Sao Mai Tech", "Sản phẩm", "Cần Thơ", False, "full_time", "mid", 3, ["Python", "React", "SQL"], ["FastAPI", "Docker"], (24_000_000, 38_000_000, "VND", "month"),
     "Sao Mai Tech làm phần mềm quản lý nông trại cho hợp tác xã. Bạn làm từ giao diện đến API, đi thực tế cùng đội để hiểu người dùng."),
    ("Chuyên viên tuyển dụng", "Nắng Mới HR", "Nhân sự", "TP. Hồ Chí Minh", False, "full_time", "junior", 1, ["Giao tiếp", "Làm việc nhóm"], ["Tiếng Anh", "Excel"], (11_000_000, 17_000_000, "VND", "month"),
     "Nắng Mới HR tìm kiếm và phỏng vấn ứng viên ngành công nghệ cho khách hàng doanh nghiệp. Bạn quản lý hồ sơ, sắp lịch phỏng vấn và phản hồi cho ứng viên."),
]

# Pairs of lines of a private conversation: (the one who starts, the answer).
DIALOGUES = [
    [("Chào bạn, mình thấy bạn cũng học khoá Python. Bạn học đến bài nào rồi?", "Chào bạn! Mình đang ở bài vòng lặp, hơi khó một chút."),
     ("Mình cũng vậy, hay là tối nay mình giải bài cùng nhau nhé?", "Hay quá, 8 giờ tối được không? Mình sẽ mở một cuộc họp trong phòng chat.")],
    [("Bạn ơi, cái nón lá thêu hoa sen còn không? Mình muốn mua hai cái.", "Còn bạn nhé, mình mới nhập thêm sáng nay."),
     ("Tuyệt, mình đặt qua Market rồi, bạn xác nhận giúp mình.", "Mình thấy đơn rồi, sẽ gửi ngay trong chiều nay.")],
    [("Anh ơi, em ứng tuyển vị trí Backend Python, anh cho em hỏi quy trình phỏng vấn thế nào?", "Chào em, có hai vòng: một vòng kỹ thuật 60 phút và một vòng gặp trưởng nhóm."),
     ("Dạ vâng, em cần chuẩn bị phần nào nhiều nhất ạ?", "SQL và thiết kế API là chính, em ôn thêm cách tối ưu truy vấn nhé.")],
    [("Cuối tuần này bạn có đi chụp ảnh ở phố cổ không?", "Có chứ, mình định đi từ sáng sớm để bắt ánh nắng đầu ngày."),
     ("Mình đi cùng nhé, mình sẽ mang máy phim.", "Ok, 6 giờ sáng gặp nhau ở Hồ Gươm.")],
    [("Mình vừa chơi ván Ma Sói tối qua, bạn làm Tiên tri mà đoán đúng cả hai con sói luôn!", "Haha, may mắn thôi. Tối thứ Sáu này chơi tiếp nhé?"),
     ("Chắc chắn rồi, mình sẽ rủ thêm hai người bạn.", "Tuyệt, nhớ vào phòng trước 9 giờ nhé.")],
    [("Bạn ơi, mình muốn học thiết kế giao diện, bạn có gợi ý khoá nào không?", "Bạn thử xem khoá thiết kế UI cho người mới trong mục Learning, có bài tập thực hành."),
     ("Cảm ơn bạn, mình đăng ký ngay.", "Học xong có gì chưa hiểu cứ hỏi mình nhé.")],
]

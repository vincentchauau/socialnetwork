"""Demo market: products, orders and reviews (Vietnamese). Prices are USD cents (the market's only currency).

A seller slot is a number: 0..4 are virtual people drawn by the seeder, "admin" is user 1.
"""

ADMIN = "admin"

# (name, description, price_cents, stock, category, seller slot)
PRODUCTS = [
    ("Cà phê rang xay Cầu Đất 500g", "Arabica trồng ở Cầu Đất, Đà Lạt, rang vừa, hậu vị chocolate và hạt dẻ. Đóng gói túi zip có van một chiều giữ hương, phù hợp pha phin hoặc máy espresso.", 1450, 60, "thực phẩm", 0),
    ("Mật ong rừng U Minh 500ml", "Mật ong thu hoạch từ rừng tràm U Minh, màu hổ phách, vị ngọt thanh, không pha đường. Dùng pha nước chanh, trộn sữa chua hoặc làm quà biếu.", 1890, 40, "thực phẩm", 0),
    ("Phin cà phê inox kèm đế", "Phin inox 304 dày dặn, nắp đậy giữ nhiệt, kèm đế chống trượt. Dung tích 150ml cho một ly cà phê đậm đà đúng điệu Việt Nam.", 690, 120, "đồ gia dụng", 0),
    ("Bộ ấm trà gốm Bát Tràng", "Bộ một ấm và bốn chén men rạn thủ công từ làng gốm Bát Tràng. Giữ nhiệt tốt, mỗi bộ có hoa văn hơi khác nhau nên không bị trùng lặp.", 3490, 25, "đồ gia dụng", 1),
    ("Nón lá Huế thêu hoa sen", "Nón lá làm từ lá non phơi sương, khâu tay hai lớp, thêu hoa sen ở lớp trong. Nhẹ, thoáng, che nắng rất tốt khi đi chơi hoặc chụp ảnh.", 890, 50, "thời trang", 1),
    ("Tranh lụa thêu tay cảnh làng quê", "Tranh thêu tay trên lụa tơ tằm, kích thước 30x40cm, đóng khung gỗ. Mỗi bức mất khoảng hai tuần để hoàn thành, mang lại không khí bình yên cho phòng khách.", 4590, 8, "trang trí", 1),
    ("Nến thơm sáp đậu nành sả chanh", "Nến sáp đậu nành rót tay, tim cotton, cháy sạch và lâu khoảng 40 giờ. Mùi sả chanh giúp xua muỗi nhẹ và thư giãn sau ngày dài.", 1090, 70, "trang trí", 2),
    ("Túi vải canvas in hình phố cổ", "Túi tote vải canvas dày, in tranh vẽ tay các góc phố cổ Hà Nội, có túi nhỏ bên trong và khóa kéo. Đựng vừa laptop 14 inch.", 790, 90, "thời trang", 2),
    ("Sổ tay bìa da handmade A5", "Sổ 160 trang giấy kem định lượng 100gsm, bìa da bò thật khâu tay, gáy mở phẳng. Thích hợp ghi chép công việc hoặc làm nhật ký.", 1190, 45, "văn phòng phẩm", ADMIN),
    ("Bàn phím cơ 87 phím", "Bàn phím cơ không số, switch tactile êm tay, keycap PBT bền màu, kết nối cáp USB-C có thể tháo rời. Phù hợp lập trình viên và người viết nhiều.", 5490, 18, "đồ công nghệ", 3),
    ("Chuột không dây yên tĩnh", "Chuột không dây 2.4GHz và Bluetooth, nút bấm gần như không phát tiếng ồn, pin AA dùng khoảng 12 tháng. Vừa tay, thích hợp văn phòng chung.", 1690, 55, "đồ công nghệ", 3),
    ("Giá đỡ laptop nhôm gập", "Giá đỡ bằng nhôm nguyên khối, gấp gọn bỏ vừa túi, nâng được 6 mức độ cao giúp bạn ngồi làm việc đúng tư thế hơn.", 2290, 35, "đồ công nghệ", 3),
    ("Bình giữ nhiệt inox 750ml", "Bình hai lớp inox 304 giữ nóng 12 giờ, giữ lạnh 24 giờ, nắp kín không rò nước. Có quai xách tiện mang theo đi làm hoặc đi học.", 1990, 48, "đồ gia dụng", 4),
    ("Áo thun cotton in họa tiết Hà Nội", "Áo thun 100% cotton co giãn bốn chiều, in họa tiết hoa sữa và Hồ Gươm bằng mực nước thân thiện da. Có các cỡ từ S đến XL.", 1590, 80, "thời trang", 4),
    ("Sổ tay SQL bỏ túi (sách in)", "Cuốn sổ tay 120 trang tóm tắt cú pháp SQL, các mẫu truy vấn hay gặp và bài tập nhỏ. Thích hợp cho người mới học cơ sở dữ liệu.", 990, 100, "sách", ADMIN),
]

# (buyer slot, [(product index, quantity)], status, days ago). Buyer slots: 0..4 virtual people, "admin" is user 1.
ORDERS = [
    (0, [(0, 2), (2, 1)], "delivered", 50),
    (1, [(3, 1), (4, 1)], "delivered", 42),
    (2, [(9, 1), (10, 1), (11, 1)], "delivered", 35),
    (ADMIN, [(6, 2), (12, 1)], "delivered", 30),
    (0, [(13, 2), (7, 1)], "shipped", 6),
    (3, [(1, 1), (5, 1)], "paid", 3),
    (1, [(8, 1), (14, 2)], "paid", 2),
    (4, [(9, 1)], "cancelled", 20),
]

# (buyer slot, product index, quantity)
CART = [(2, 0, 1), (3, 12, 1), (4, 6, 2), (4, 13, 1), (ADMIN, 3, 1), (0, 9, 1)]

# product index -> (rating, text): each one is on a delivered order of the list above
REVIEWS = {
    0: (5, "Cà phê thơm, đậm vừa, pha phin ra màu rất đẹp. Mình đã mua lại lần hai cho cả nhà."),
    2: (4, "Phin chắc chắn, lọc chậm đúng điệu. Chỉ tiếc đế hơi nhỏ so với cốc to."),
    3: (5, "Men gốm đẹp hơn trong ảnh, giữ nhiệt tốt. Đóng gói cẩn thận, không vỡ chiếc nào."),
    4: (4, "Nón nhẹ, thêu hoa sen tinh tế. Giao hàng hơi chậm nhưng sản phẩm xứng đáng."),
    9: (5, "Gõ rất sướng, tiếng êm hơn mong đợi. Dùng cả ngày để lập trình không mỏi tay."),
    10: (3, "Chuột êm thật nhưng hơi nhỏ với bàn tay lớn. Dùng tạm ổn cho văn phòng."),
    6: (5, "Mùi sả chanh dễ chịu, cháy đều và lâu. Thắp buổi tối đọc sách rất thư giãn."),
    12: (4, "Bình giữ nóng tốt, buổi sáng pha trà đến chiều vẫn ấm. Nắp hơi khó mở lúc đầu."),
}

PHOTO_COMMENTS = [
    "Bức ảnh có ánh sáng rất đẹp, nhìn là thấy bình yên.",
    "Bố cục gọn gàng, màu sắc dịu mắt. Bạn chụp ở đâu vậy?",
    "Thích góc chụp này quá, cảm giác như đang đứng ngay đó.",
    "Đẹp quá! Lần sau mình cũng muốn thử chụp vào buổi sớm như vậy.",
    "Màu hơi ấm nhưng rất hợp với không khí của ảnh. Cảm ơn bạn đã chia sẻ.",
    "Ảnh này đáng để in ra treo tường đấy.",
]

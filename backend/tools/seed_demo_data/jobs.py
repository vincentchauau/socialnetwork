"""Demo job descriptions (Vietnamese), the skill catalog and the words of applications."""

SKILL_CATALOG = [
    "Python", "SQL", "PostgreSQL", "JavaScript", "React", "Docker", "Git", "Linux", "FastAPI", "Excel",
    "Phân tích dữ liệu", "Giao tiếp", "Thuyết trình", "Làm việc nhóm", "Quản lý dự án", "Scrum", "Thiết kế UI",
    "Figma", "Marketing số", "SEO", "Content marketing", "Tiếng Anh", "Chăm sóc khách hàng", "Kiểm thử phần mềm",
    "Machine learning",
]

EN = {"language": "Tiếng Anh", "proficiency": "conversational"}
VI = {"language": "Tiếng Việt", "proficiency": "native"}


def _s(name, level, years):
    return {"name": name, "level": level, "years": years}


JOBS = [
    {
        "title": "Lập trình viên Backend Python", "company": "Sao Việt Software", "department": "Khối công nghệ",
        "location": "Hà Nội", "remote": False, "employment_type": "full_time", "seniority": "mid", "openings": 2,
        "experience_min_years": 2, "education_min": "bachelor",
        "required": [_s("Python", "advanced", 2), _s("SQL", "intermediate", 2), _s("Git", "intermediate", 1)],
        "preferred": [_s("FastAPI", "intermediate", 1), _s("Docker", "beginner", None), _s("PostgreSQL", "intermediate", None)],
        "languages": [VI, EN],
        "responsibilities": ["Thiết kế và xây dựng API cho các sản phẩm thương mại điện tử", "Viết kiểm thử và tham gia đánh giá mã nguồn", "Tối ưu truy vấn và hiệu năng dịch vụ"],
        "benefits": ["Thưởng tháng 13 và thưởng dự án", "Bảo hiểm sức khỏe mở rộng", "Làm việc linh hoạt 2 ngày mỗi tuần tại nhà"],
        "salary": (22_000_000, 35_000_000, "VND", "month"), "tags": ["python", "backend", "api"],
        "description": "Sao Việt Software đang mở rộng đội ngũ phát triển nền tảng bán hàng trực tuyến phục vụ hàng nghìn cửa hàng nhỏ. Bạn sẽ làm việc trong nhóm 6 người, cùng thiết kế dịch vụ và đưa tính năng mới đến tay người dùng mỗi hai tuần.",
    },
    {
        "title": "Lập trình viên Frontend React", "company": "Mây Xanh Cloud", "department": "Sản phẩm web",
        "location": "TP. Hồ Chí Minh", "remote": True, "employment_type": "full_time", "seniority": "junior", "openings": 3,
        "experience_min_years": 1, "education_min": "bachelor",
        "required": [_s("React", "intermediate", 1), _s("JavaScript", "intermediate", 1), _s("Git", "beginner", None)],
        "preferred": [_s("Thiết kế UI", "beginner", None), _s("Tiếng Anh", "intermediate", None)],
        "languages": [VI, EN],
        "responsibilities": ["Dựng giao diện bảng điều khiển quản trị bằng React", "Phối hợp với thiết kế để hiện thực hóa mẫu giao diện", "Đảm bảo giao diện hiển thị tốt trên điện thoại"],
        "benefits": ["Làm việc từ xa hoàn toàn", "Ngân sách học tập 5 triệu đồng mỗi năm", "Máy tính xách tay do công ty cấp"],
        "salary": (15_000_000, 25_000_000, "VND", "month"), "tags": ["react", "frontend", "remote"],
        "description": "Mây Xanh Cloud cung cấp phần mềm quản lý kho và đơn hàng cho doanh nghiệp vừa và nhỏ. Chúng tôi cần một bạn frontend yêu thích giao diện gọn gàng, dễ dùng và sẵn sàng học hỏi từ các đồng nghiệp giàu kinh nghiệm.",
    },
    {
        "title": "Chuyên viên phân tích dữ liệu", "company": "Nam Phong Analytics", "department": "Dữ liệu và thông tin kinh doanh",
        "location": "Đà Nẵng", "remote": False, "employment_type": "full_time", "seniority": "mid", "openings": 1,
        "experience_min_years": 2, "education_min": "bachelor",
        "required": [_s("SQL", "advanced", 2), _s("Excel", "advanced", 2), _s("Phân tích dữ liệu", "intermediate", 2)],
        "preferred": [_s("Python", "intermediate", 1), _s("Thuyết trình", "intermediate", None)],
        "languages": [VI, EN],
        "responsibilities": ["Xây dựng báo cáo doanh thu và hành vi khách hàng hằng tuần", "Truy vấn và làm sạch dữ liệu từ nhiều nguồn", "Trình bày kết quả phân tích cho ban giám đốc"],
        "benefits": ["Lương cạnh tranh theo năng lực", "Du lịch công ty hằng năm", "Đào tạo nội bộ về phân tích nâng cao"],
        "salary": (18_000_000, 30_000_000, "VND", "month"), "tags": ["du lieu", "sql", "bao cao"],
        "description": "Nam Phong Analytics tư vấn dữ liệu cho các chuỗi bán lẻ ở miền Trung. Bạn sẽ biến số liệu thô thành những báo cáo giúp khách hàng quyết định nhanh và đúng hơn.",
    },
    {
        "title": "Kỹ sư DevOps", "company": "Lạc Hồng Digital", "department": "Hạ tầng",
        "location": "Hà Nội", "remote": True, "employment_type": "full_time", "seniority": "senior", "openings": 1,
        "experience_min_years": 4, "education_min": "bachelor",
        "required": [_s("Docker", "advanced", 3), _s("Linux", "advanced", 4), _s("Git", "advanced", 3)],
        "preferred": [_s("Python", "intermediate", 2), _s("PostgreSQL", "intermediate", 2)],
        "languages": [VI, EN],
        "responsibilities": ["Vận hành hệ thống chạy trên container và tự động hóa triển khai", "Giám sát, cảnh báo và xử lý sự cố ngoài giờ theo ca", "Hướng dẫn nhóm phát triển về quy trình CI/CD"],
        "benefits": ["Phụ cấp trực hệ thống", "Làm việc từ xa linh hoạt", "Chế độ nghỉ phép 15 ngày mỗi năm"],
        "salary": (2_000, 3_200, "USD", "month"), "tags": ["devops", "docker", "linux"],
        "description": "Lạc Hồng Digital vận hành các dịch vụ thanh toán điện tử cho khách hàng trong nước và khu vực. Chúng tôi tìm một kỹ sư có kinh nghiệm xây dựng hạ tầng ổn định và an toàn.",
    },
    {
        "title": "Nhân viên Marketing số", "company": "Hướng Dương Media", "department": "Tăng trưởng",
        "location": "TP. Hồ Chí Minh", "remote": False, "employment_type": "full_time", "seniority": "junior", "openings": 2,
        "experience_min_years": 1, "education_min": "bachelor",
        "required": [_s("Marketing số", "intermediate", 1), _s("Content marketing", "intermediate", 1)],
        "preferred": [_s("SEO", "beginner", None), _s("Giao tiếp", "intermediate", None), _s("Excel", "beginner", None)],
        "languages": [VI],
        "responsibilities": ["Lên kế hoạch và viết nội dung cho các kênh mạng xã hội của khách hàng", "Chạy và tối ưu quảng cáo trả phí", "Báo cáo kết quả chiến dịch hằng tháng"],
        "benefits": ["Thưởng hiệu quả theo chiến dịch", "Môi trường trẻ, năng động", "Khóa học chứng chỉ do công ty tài trợ"],
        "salary": (12_000_000, 18_000_000, "VND", "month"), "tags": ["marketing", "noi dung", "quang cao"],
        "description": "Hướng Dương Media là agency nhỏ chuyên chăm sóc thương hiệu cho các cửa hàng và quán cà phê địa phương. Bạn sẽ trực tiếp làm việc với chủ cửa hàng để biến ý tưởng thành chiến dịch thực tế.",
    },
    {
        "title": "Quản lý dự án phần mềm", "company": "Thăng Long Solutions", "department": "Quản lý chương trình",
        "location": "Hà Nội", "remote": False, "employment_type": "full_time", "seniority": "manager", "openings": 1,
        "experience_min_years": 5, "education_min": "bachelor",
        "required": [_s("Quản lý dự án", "advanced", 4), _s("Scrum", "advanced", 3), _s("Giao tiếp", "advanced", None)],
        "preferred": [_s("Tiếng Anh", "advanced", None), _s("Thuyết trình", "intermediate", None)],
        "languages": [VI, {"language": "Tiếng Anh", "proficiency": "fluent"}],
        "responsibilities": ["Điều phối 2-3 dự án phần mềm cho khách hàng nước ngoài", "Quản lý phạm vi, tiến độ, rủi ro và ngân sách", "Làm việc trực tiếp với khách hàng và nhóm kỹ thuật"],
        "benefits": ["Thưởng theo kết quả dự án", "Bảo hiểm sức khỏe cho cả gia đình", "Cơ hội công tác ở nước ngoài"],
        "salary": (35_000_000, 55_000_000, "VND", "month"), "tags": ["quan ly", "scrum", "du an"],
        "description": "Thăng Long Solutions gia công phần mềm cho khách hàng ở châu Âu và Nhật Bản. Bạn sẽ chịu trách nhiệm đưa dự án về đích đúng hạn, đúng chất lượng và giữ cho đội ngũ làm việc hiệu quả.",
    },
    {
        "title": "Nhà thiết kế giao diện UI/UX", "company": "Cầu Vồng Studio", "department": "Thiết kế",
        "location": "Đà Nẵng", "remote": True, "employment_type": "contract", "seniority": "mid", "openings": 1,
        "experience_min_years": 2, "education_min": None,
        "required": [_s("Thiết kế UI", "advanced", 2), _s("Figma", "advanced", 2)],
        "preferred": [_s("Giao tiếp", "intermediate", None), _s("React", "beginner", None)],
        "languages": [VI],
        "responsibilities": ["Thiết kế giao diện ứng dụng di động và web", "Xây dựng và duy trì hệ thống thiết kế dùng chung", "Thử nghiệm với người dùng và cải tiến luồng sử dụng"],
        "benefits": ["Hợp đồng 12 tháng, có thể gia hạn", "Giờ làm việc linh hoạt", "Được tham gia chọn dự án"],
        "salary": (20_000_000, 32_000_000, "VND", "month"), "tags": ["thiet ke", "ui", "figma"],
        "description": "Cầu Vồng Studio thiết kế ứng dụng cho các startup giáo dục và sức khỏe. Chúng tôi cần một nhà thiết kế có tư duy sản phẩm, biết lắng nghe người dùng và làm việc nhịp nhàng với lập trình viên.",
    },
    {
        "title": "Nhân viên chăm sóc khách hàng", "company": "Phố Cổ Coffee", "department": "Vận hành",
        "location": "Hà Nội", "remote": False, "employment_type": "part_time", "seniority": "intern", "openings": 4,
        "experience_min_years": 0, "education_min": "high_school",
        "required": [_s("Chăm sóc khách hàng", "beginner", None), _s("Giao tiếp", "intermediate", None)],
        "preferred": [_s("Làm việc nhóm", "intermediate", None), _s("Excel", "beginner", None)],
        "languages": [VI],
        "responsibilities": ["Tiếp nhận và trả lời tin nhắn, cuộc gọi của khách hàng", "Xử lý khiếu nại theo quy trình của cửa hàng", "Cập nhật thông tin khách hàng vào bảng theo dõi"],
        "benefits": ["Ca làm linh hoạt cho sinh viên", "Đồ uống miễn phí trong ca", "Cơ hội lên nhân viên chính thức"],
        "salary": (30_000, 40_000, "VND", "hour"), "tags": ["cham soc khach hang", "ban thoi gian"],
        "description": "Chuỗi cà phê Phố Cổ có tám cửa hàng ở Hà Nội và cần các bạn sinh viên nhiệt tình hỗ trợ khách hàng qua điện thoại và tin nhắn. Không yêu cầu kinh nghiệm, chúng tôi sẽ đào tạo từ đầu.",
    },
    {
        "title": "Kỹ sư kiểm thử phần mềm", "company": "Bến Thành Retail Tech", "department": "Bảo đảm chất lượng",
        "location": "TP. Hồ Chí Minh", "remote": False, "employment_type": "full_time", "seniority": "mid", "openings": 2,
        "experience_min_years": 2, "education_min": "bachelor",
        "required": [_s("Kiểm thử phần mềm", "advanced", 2), _s("SQL", "intermediate", 1)],
        "preferred": [_s("Python", "intermediate", 1), _s("Scrum", "beginner", None), _s("Tiếng Anh", "intermediate", None)],
        "languages": [VI, EN],
        "responsibilities": ["Viết kế hoạch và kịch bản kiểm thử cho hệ thống bán hàng", "Tự động hóa kiểm thử hồi quy", "Báo cáo lỗi rõ ràng và theo dõi đến khi sửa xong"],
        "benefits": ["Thưởng chất lượng theo quý", "Giảm giá nội bộ khi mua sắm", "Bảo hiểm sức khỏe"],
        "salary": (16_000_000, 26_000_000, "VND", "month"), "tags": ["kiem thu", "qa", "tu dong hoa"],
        "description": "Bến Thành Retail Tech phát triển hệ thống thanh toán và quản lý cửa hàng cho một chuỗi siêu thị. Mỗi phiên bản phát hành đều đi qua tay đội kiểm thử trước khi đến với hàng trăm cửa hàng.",
    },
    {
        "title": "Thực tập sinh Machine Learning", "company": "An Phúc AI Lab", "department": "Nghiên cứu ứng dụng",
        "location": "Hà Nội", "remote": True, "employment_type": "internship", "seniority": "intern", "openings": 2,
        "experience_min_years": 0, "education_min": "bachelor",
        "required": [_s("Python", "intermediate", None), _s("Machine learning", "beginner", None)],
        "preferred": [_s("Phân tích dữ liệu", "beginner", None), _s("SQL", "beginner", None), _s("Tiếng Anh", "intermediate", None)],
        "languages": [VI, EN],
        "responsibilities": ["Chuẩn bị và gán nhãn dữ liệu huấn luyện", "Thử nghiệm các mô hình phân loại văn bản tiếng Việt", "Ghi chép và trình bày kết quả thí nghiệm hằng tuần"],
        "benefits": ["Phụ cấp thực tập 6 triệu đồng mỗi tháng", "Có người hướng dẫn riêng", "Ưu tiên nhận chính thức khi kết thúc kỳ thực tập"],
        "salary": (6_000_000, 8_000_000, "VND", "month"), "tags": ["machine learning", "thuc tap", "python"],
        "description": "An Phúc AI Lab nghiên cứu ứng dụng xử lý ngôn ngữ tiếng Việt trong chăm sóc khách hàng. Kỳ thực tập kéo dài ba tháng, bạn sẽ tham gia một dự án thật từ khâu dữ liệu đến thử nghiệm mô hình.",
    },
]

COVER_LETTERS = [
    "Kính gửi anh/chị phụ trách tuyển dụng {company},\n\nEm đã đọc kỹ mô tả vị trí {title} và thấy kinh nghiệm của mình về {skills} phù hợp với yêu cầu. "
    "Ở công việc gần nhất em đã tự tay hoàn thành nhiều đầu việc tương tự và luôn chú trọng đến chất lượng. Em rất mong có cơ hội trao đổi thêm.\n\nTrân trọng cảm ơn.",
    "Chào {company},\n\nMình quan tâm đến vị trí {title} vì công việc gắn liền với {skills} - lĩnh vực mình theo đuổi những năm qua. "
    "Mình thích làm việc nhóm, chủ động học điều mới và sẵn sàng bắt đầu sớm. Hồ sơ của mình được đính kèm bên dưới.",
    "Thưa quý công ty,\n\nTôi xin ứng tuyển vị trí {title}. Tôi có nền tảng về {skills} và mong muốn đóng góp vào các dự án của {company}. "
    "Tôi có thể sắp xếp thời gian phỏng vấn trực tiếp hoặc trực tuyến vào bất kỳ ngày nào trong tuần.",
    "Xin chào đội ngũ {company},\n\nEm là người luôn đề cao sự cẩn thận và trách nhiệm. Với kiến thức về {skills}, em tin mình có thể nhanh chóng hòa nhập vào vị trí {title}. "
    "Rất mong nhận được phản hồi từ anh/chị.",
]

EMPLOYER_NOTES = [
    "Hồ sơ rõ ràng, kỹ năng khớp phần lớn yêu cầu. Cần hỏi thêm về kinh nghiệm làm việc nhóm.",
    "Đã gọi điện sơ bộ, ứng viên trao đổi tốt. Hẹn phỏng vấn kỹ thuật tuần sau.",
    "Kinh nghiệm chưa đủ so với yêu cầu, lưu hồ sơ cho vị trí junior.",
    "Phỏng vấn xong, đội kỹ thuật đánh giá cao. Chuẩn bị đề xuất mức lương.",
]

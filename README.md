# BOCONIC Book Connect

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI_0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SQLAlchemy](https://img.shields.io/badge/ORM-SQLAlchemy_2.0_Async-d71f00?style=flat-square&logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org)
[![aiogram](https://img.shields.io/badge/Telegram_Bot-aiogram_3.x-2CA5E0?style=flat-square&logo=telegram&logoColor=white)](https://docs.aiogram.dev)
[![Pydantic](https://img.shields.io/badge/Data_Validation-Pydantic_v2-E92063?style=flat-square&logo=pydantic&logoColor=white)](https://docs.pydantic.dev)
[![Tests](https://img.shields.io/badge/Tests-66%20Passed-brightgreen?style=flat-square&logo=pytest&logoColor=white)](tests/)

Boconic Telegram Bot là sản phẩm bot kết nối người mượn sách và người cho mượn sách. Techstack hoàn toàn dựa trên quy trình host, tự động hóa, quản lý các hệ thống thông tin đến từ người dùng. Sản phẩm chỉ sử dụng cho mục đích học tập và phục vụ quá trình học tập, nghiên cứu tại Trường. Hiện tại, sản phẩm này là một phần nằm trong bài làm thử tuyển chọn Câu lạc bộ Trí tuệ nhân tạo – UIT. 

**Sinh viên:** Nguyễn Huỳnh Đăng Nhựt.  
**Bot:** [@boconic_bot](https://t.me/boconic_bot) - Bot sẽ live cho đến khi hết đợt tuyển hoặc đến khi VPS không sử dụng được ;-;

Toàn bộ README này trình bày vấn đề mà em tiếp cận, cách Boconic kết nối nhu cầu với tài nguyên đang có, cấu trúc kỹ thuật và quy trình để khởi chạy, kiểm tra, quản lý sản phẩm. Với mỗi user, em xem họ vừa là một người học đang cần tài liệu, vừa có thể là người đang giữ những tài nguyên mà người khác cần. 
Do thời gian ngắn (Có hạn) của quy trình nộp sản phẩm và các vấn đề gia đình liên quan, toàn bộ sản phẩm khi này được tổ chức logic, tech, quá trình xử lý, mô hình, công cụ bởi em. Và xử lý kỹ thuật đến khoảng 55% trên Antigravity – model Gemini 3.8 Flash và 20% trên Model Claude Opus 4.6. Bot được xây dựng dựa theo Botfather Auth – VPS được dùng trên máy Ubuntu (Own Host), dữ liệu không công khai và đảm bảo các quyền riêng tự, và các vấn đề liên quan đến pháp luật hiện hành; em mong các anh chị sẽ thông cảm cho em!



![Bot Telegram](assets/bot-telegram.jpg)
*Hình 1. Bot Telegram và các tính năng của ẻm.*

![Trang quản lý](assets/ql-bot.jpg)
*Hình 2. Trang quản lý toàn bộ.*


## 1 Tiếp cận ban đầu:

Khi mùa tựu trường bắt đầu, việc thiếu sách ở một số nơi có thể khiến phụ huynh phải tìm qua nhiều điểm bán, còn học sinh chưa có đầy đủ tài liệu để theo kịp bài học. Ngày 14/9/2026, Báo điện tử Chính phủ thông tin về yêu cầu của Bộ Giáo dục và Đào tạo rà soát học sinh còn thiếu sách, điều chuyển sách từ nơi dư đến nơi thiếu và hướng dẫn tiếp cận sách điện tử miễn phí. Điều này cho thấy bài toán cần giải quyết còn nằm ở việc xác định đúng nhu cầu và kết nối với nguồn sách phù hợp. Chính vì thế, dưới góc nhìn của một người đã từng là học sinh, em đặt ra câu hỏi: Nếu có người đang cần một quyển sách, trong khi một người khác đang có quyển đó nhưng chưa sử dụng, làm thế nào để hai người biết đến nhau và thực hiện việc mượn một cách rõ ràng? Các giải pháp hiện tại vẫn có giá trị, nhưng khi đi vào từng trường hợp, mỗi giải pháp lại có những giới hạn riêng. Sách cũ có thể tiếp tục sử dụng nếu đúng ấn bản và nội dung học; nếu khác bộ sách hoặc phiên bản, việc dùng lại phải được kiểm tra. Sách điện tử giúp tiếp cận nội dung nhanh hơn, nhưng người học vẫn có thể cần sách giấy để mang đến lớp, ghi chú và học trong điều kiện ít sử dụng thiết bị. Dùng chung sách ở trường giải quyết được một phần nhu cầu, còn khi về nhà, người học vẫn cần tài liệu theo tiến độ của mình.
Từ đó, em tiếp cận Boconic theo hướng quản lý tài nguyên đang có và nhu cầu đang thiếu. Một người có thể cho mượn sách nguyên cuốn, đăng thông tin về phần tài liệu mình đang giữ, hoặc giới thiệu một nguồn tài nguyên được phép sử dụng. Người đang thiếu sách có thể tìm đúng ấn bản, tạo yêu cầu và theo dõi quá trình được hỗ trợ. Bot đóng vai trò connection để những thông tin này gặp nhau, thay vì để mỗi người tự hỏi trong nhiều nhóm mà không biết nguồn nào còn sẵn.

## 2 Quy cách sử dụng

Chính vì thế, dưới cương vị của một người đã từng là một học sinh, đây là vấn đề hết sức khó khăn. Nếu tiếp cận các giải pháp như dùng lại sách cũ, mượn sách từ những học sinh cũ từ khóa trước là hoàn toàn KHÔNG KHẢ THI do việc thay đổi còn một đầu sách, cũng như các điều chỉnh kiến thức liên quan.
Các giải pháp hiện tại đã phát huy tác dụng của nó, nhưng vẫn có những hạn chế nhất định:
- Dùng bản điện tử: Dù là các bản điện tử đã được công khai từ rất sớm, nhưng thời điểm hiện tại không phải à khả thi khi các học sinh ở trường vẫn ưu tiên hình thức học tập trên giấy.
- Dùng chung sách: Học sinh có thể chia sẻ sách, vở tại bàn; nhưng nếu tại nhà – thì đâu mới là giải pháp tốt nhất: Giữa sách giấy và sách được sử dụng từ các thiết bị thông minh?
- Hỗ trợ từ giáo viên: Giáo viên trực tiếp in các nội dung cần thiết cho học sinh – vậy, chi phí khi đó bỏ ra là rất lớn. Các hình thức liên quan đến thu quỹ lớp học đã được quy định tại Thông tư 81/2026/TT-BGDDT.
Để giải quyết vấn đề này triệt để, em đã tiếp cận theo hướng: Khai thác lỗ hổng từ nghị định 17/2023/ND-CP. Điều đặt ra duy nhất ở đây, đó chính là trên mỗi cá nhân – chỉ được 10%, vậy – nếu chỉ cần 10 cá nhân là đã có thể photocopy hoàn toàn quyển sách – điều đó hoàn toàn không bị giới hạn tại bất kỳ nghị định nào, kể cả các quyết định luật pháp liên quan đến quyền cho thuê, mượn, ...
Với quy cách tiếp cận như trên, với mỗi cá nhân – chỉ cần đóng góp < 10% của tài liệu – với mức thu nhập hiện tại, điều đó là hoàn toàn khả thi; nằm trong mức cho phép khi kết hợp với nhiều giải pháp liên quan. Sau khi đã tham khảo từ nhiều nguồn, cũng như một vài kiến thức trong việc quản lý database, tự động hóa quá trình, ... Em đã tương đối hoàn thành prototype đầu tiên của Boconic. Mỗi Users ở đây sẽ tương ứng như một người học – một người thiếu sách và cũng là một người dư sách: Họ cần các chương quy định, và họ có khả năng trao đổi các chương họ đang có để lấy các tài liệu mới, cũng như mỗi cá nhân khi có dư các tài liệu, có thể xem bot như một connection để kết nối với nhau, kiếm các giải pháp, quy trình cụ thể để xử lý sách – tránh ảnh hưởng các vấn đề về pháp lý.

## 3 Mục tiêu và cách tổ chức sản phẩm

Em muốn Boconic hỗ trợ người học tìm được tài nguyên phù hợp với phần đang cần, đồng thời giúp người có sách biết cách cho mượn, theo dõi giao nhận và nhận lại sách. Đối tượng mà sản phẩm hướng đến là học sinh, sinh viên, phụ huynh và những nhóm hỗ trợ học tập trong cộng đồng. Để thực hiện điều đó, sản phẩm được tổ chức quanh các nhóm chứuc năng:
1. Tìm sách theo tên, ấn bản, nhà xuất bản và thông tin chương trình học.
2. Tạo nhu cầu tìm sách nguyên cuốn hoặc theo chương, sau đó kết nối với người có tài nguyên phù hợp.
3. Quản lý yêu cầu mượn, giữ chỗ, giao nhận và hoàn trả qua xác nhận của hai bên.
4. Quản lý thư viện cá nhân, phần tài liệu đang giữ và tiến độ học theo chương.
5. Tương tác qua Telegram Bot bằng menu, các bước nhập thông tin và thông báo.
6. Quản trị qua web để quản lý sách, người dùng, quyền truy cập, báo cáo và hoạt động hệ thống.

## 4 Mở Telegram

Người dùng bắt đầu bằng cách mở [@boconic_bot](https://t.me/boconic_bot), chọn Start hoặc gửi `/start`, rồi thao tác từ menu. Telegram là nơi trao đổi duy nhất; các quyết định được xử lý ở backend.

### 4.1 Ý nghĩa từng lựa chọn trong menu

| Lựa chọn | Người dùng thực hiện | Kết quả cần theo dõi |
| --- | --- | --- |
| Tìm sách | Tìm đúng sách và ấn bản, xem tài nguyên có liên quan | Bản sách phù hợp và bước gửi yêu cầu |
| Thư viện của tôi | Xem những sách và tài nguyên đã lưu vào thư viện cá nhân | Danh sách của chính người dùng |
| Tài nguyên đang dùng | Xem tài liệu đang sử dụng cho việc học | Tài nguyên gắn với tiến độ hiện tại |
| Quản lý theo chương | Xem mục lục, cập nhật tiến độ và đề xuất điều chỉnh | Chương học và trạng thái tiến độ |
| Yêu cầu sách | Tạo nhu cầu về một quyển sách hoặc các chương cụ thể | Nhu cầu được lưu để tìm nguồn hỗ trợ |
| Nhu cầu của tôi | Theo dõi các nhu cầu đã tạo và phản hồi liên quan | Mức đáp ứng và tình trạng xử lý |
| Mượn tài liệu 1 phần | Tìm phần tài liệu có phạm vi nội dung phù hợp | Yêu cầu đối với tài nguyên đủ điều kiện |
| Up tài liệu 1 phần | Đăng thông tin phần tài liệu đang giữ và nguồn của nó | Bản ghi phạm vi, quyền truy cập và kiểm duyệt |
| Đăng sách | Đăng bản sách mình sở hữu hoặc có quyền cho mượn | Bản sách có chủ sở hữu và trạng thái rõ ràng |
| Thư viện cộng đồng | Xem những tài nguyên được phép hiển thị cho cộng đồng | Danh mục công khai trong phạm vi cho phép |
| Đang mượn | Xem sách đang giữ, hạn mượn và bước hoàn trả | Giao dịch của người mượn |
| Đang cho mượn | Xem sách đang được người khác giữ | Giao dịch của người cho mượn |
| Yêu cầu mượn | Xử lý hoặc theo dõi các đề nghị mượn liên quan | Chấp nhận, từ chối hoặc tiếp tục giao nhận |
| Tài nguyên mở | Tiếp cận các nguồn có điều kiện sử dụng phù hợp | Đường dẫn nguồn và điều kiện sử dụng |
| Hồ sơ và Cài đặt | Xem, cập nhật thông tin và lựa chọn cá nhân | Hồ sơ, vị trí và thiết lập của người dùng |
| Báo cáo và Hỗ trợ | Phản ánh tài nguyên, người dùng hoặc giao dịch có vấn đề | Báo cáo được chuyển tới quản trị |

### 4.2 Flowchart Telegram

![Flowchart các lựa chọn menu Telegram](assets/flowchart-telegram.png)

*Hình 3. Flowchart các tính năng Telegram và hướng kết nối dữ liệu.*

Sơ đồ trên trình bày các nhánh từ menu đến tìm kiếm, tài nguyên, yêu cầu và xử lý. 

## 5 Các quy tắc nắm bản quyền

### 5.1 Tạo nhu cầu và matching

Book request là nhu cầu của người học; borrow request là đề nghị mượn một bản tài nguyên cụ thể. Hoàn toàn được minh hcuwsng: Quy trình matching bắt đầu từ sách và ấn bản cần tìm, sau đó xét phạm vi nội dung, tình trạng tài nguyên và điều kiện của chủ tài nguyên. Với nhu cầu nguyên cuốn, kết quả phải phân biệt rõ bản đầy đủ với phần tài liệu chỉ đáp ứng được một phần. Với nhu cầu theo chương, hệ thống đối chiếu phần người học cần với phần tài nguyên đang có. Nếu chỉ đáp ứng một phần, người dùng cần nhìn thấy phần đã có và phần còn thiếu. Việc có giao nhau về số trang giúp tìm ứng viên, nhưng chưa đủ để khẳng định nhu cầu đã được đáp ứng hoàn toàn. Khi chủ sách phản hồi, kết quả matching mới được nối sang luồng mượn tương ứng.

### 5.2 Mượn và trả qua xác nhận hai bên

| Trạng thái | Ý nghĩa | Điều kiện chuyển tiếp |
| --- | --- | --- |
| `reserved` | Bản sách đã được giữ chỗ cho một giao dịch | Hoàn thành xác nhận giao nhận của hai bên |
| `active` | Giao dịch đang diễn ra; người mượn đã nhận sách | Khởi tạo bước hoàn trả theo quy trình |
| `return_pending` | Đang chờ hoàn tất xác nhận trả sách | Hai bên xác nhận hoàn trả |
| `returned` | Giao dịch đã hoàn tất | Lưu lịch sử; tài nguyên được xử lý theo trạng thái sau trả |

Thời gian giữ chỗ trong thiết kế là 72 giờ để tránh một bản sách bị giữ nhưng không có giao nhận thực tế. Khi hết thời hạn, hệ thống cần xử lý việc giải phóng giữ chỗ và lưu lý do. Người dùng không được tự mượn sách của mình; hai yêu cầu đồng thời cũng không được cùng giữ chỗ một bản sách.

Điều em muốn giữ ở đây là sự rõ ràng: một thao tác bấm nút của một bên chưa đủ để thay thế việc xác nhận của bên còn lại. Các trường hợp hủy, quá hạn hoặc tranh chấp phải có lịch sử để admin xem lại, tránh sửa trạng thái mà không biết vì sao giao dịch thay đổi.

## 6 Quản trị và trách nhiệm vận hành

Web Admin Console được truy cập tại `/admin`. Em tổ chức trang quản trị để việc quản lý, mọi vấn đều phát sinh chỉ cần 1 user àm admin để quản trị toàn hệ thống, kết nối được người dùng, tài nguyên và lịch sử xử lý khi có vấn đề phát sinh.

| Nhóm quản trị | Phạm vi công việc |
| --- | --- |
| Người dùng và quyền | Quản lý hồ sơ, tài khoản admin, vai trò và quyền truy cập |
| Catalog và bản sách | Quản lý đầu sách, tác giả, nhà xuất bản, bản sách và tình trạng |
| Chương và tiến độ | Kiểm tra cấu trúc chương, đề xuất thay đổi và dữ liệu liên quan |
| Nhu cầu và hỗ trợ | Theo dõi yêu cầu cộng đồng, phản hồi hỗ trợ và kết quả matching |
| Mượn trả | Xem giao dịch, xác nhận, người đang giữ và lịch sử thay đổi |
| Tài nguyên số | Quản lý nguồn, file, quyền truy cập và các collection đủ điều kiện |
| Kiểm duyệt và uy tín | Xử lý báo cáo, cảnh báo, đánh giá và sự kiện liên quan đến uy tín |
| Vận hành | Theo dõi tác vụ nền, outbox, audit, nhập xuất dữ liệu và sao lưu |

Các thao tác quản trị cần được giới hạn bằng RBAC, tức phân quyền dựa trên vai trò. Quyền không chỉ được kiểm tra ở nút hiển thị trên giao diện mà còn phải được kiểm tra ở backend. Một tài khoản không có quyền sửa dữ liệu không được sửa qua API dù biết địa chỉ endpoint. Khi sửa tài nguyên, xử lý báo cáo hoặc can thiệp giao dịch, admin cần để lại lý do và dấu vết audit phù hợp. Em xem đây là cơ sở để giải thích lại một quyết định, đặc biệt khi việc thay đổi ảnh hưởng đến người mượn, người cho mượn hoặc điểm tin cậy.

## 7 Kiến trúc hệ thống

Sản phẩm được tổ chức thành Telegram Bot Gateway, ứng dụng FastAPI, các service nghiệp vụ, database và worker xử lý nền. Bot nhận thao tác từ Telegram rồi gọi backend qua HTTP; trang quản trị đi qua các route web của backend. Dữ liệu nghiệp vụ được quản lý bằng SQLAlchemy, còn worker có nhánh truy cập ORM trực tiếp theo sơ đồ database. Tương ứng:
| Thành phần | Trách nhiệm trong Boconic |
| --- | --- |
| Telegram và aiogram | Nhận message, callback, điều hướng menu và các bước nhập thông tin |
| FastAPI và Pydantic | Cung cấp API, tiếp nhận dữ liệu, kiểm tra cấu trúc và trả kết quả |
| Services | Xử lý catalog, nhu cầu, matching, chương học, mượn trả và quyền |
| SQLAlchemy AsyncSession | Thao tác với dữ liệu qua ORM và giao dịch database |
| SQLite hoặc PostgreSQL | Lưu dữ liệu nghiệp vụ theo cấu hình môi trường |
| Web Admin | Cung cấp giao diện quản trị qua Jinja2, HTMX và CSS |
| Worker và outbox | Tiếp tục xử lý các sự kiện, tác vụ nền và ghi nhận kết quả |
| File storage | Lưu file ngoài database; database lưu đường dẫn và metadata |

Bot sử dụng long polling trong kiến trúc mô tả. Kết nối nội bộ với API dùng `BOT_API_KEY`, và`BOT_TOKEN`. BotFather cấp token cho bot, không thay thế cơ chế phân quyền người dùng của Boconic.

## 8 Techstack và công cụ đã sử dụng

Do thời gian nộp sản phẩm có hạn và một số vấn đề gia đình liên quan, em sử dụng công cụ AI để hỗ trợ quá trình triển khai. Em tự tổ chức logic sản phẩm, quá trình xử lý, mô hình dữ liệu và lựa chọn công cụ; Antigravity cùng các mô hình Gemini và Claude hỗ trợ viết, điều chỉnh và kiểm tra mã nguồn. Các tỷ lệ hỗ trợ khoảng 55% và 20% là ước lượng cá nhân của em về quá trình làm việc, không phải kết quả đo độ đúng hay độ hoàn thiện của sản phẩm. (NHẮC LẠI)

Bot được đăng ký qua BotFather; môi trường host mà em lựa chọn là máy Ubuntu do em tự quản lý. Việc tự host giúp em chủ động cấu hình và quản lý dữ liệu, đồng thời đặt trách nhiệm sao lưu, bảo mật và duy trì hoạt động về phía người vận hành.

| Công nghệ | Vai trò |
| --- | --- | 
| Python 3.12 trở lên | Ngôn ngữ và môi trường chạy sản phẩm |
| FastAPI và Uvicorn | Backend API và server ASGI; FastAPI hỗ trợ OpenAPI và tài liệu API |
| Pydantic v2 | Mô hình dữ liệu, kiểm tra kiểu và ràng buộc đầu vào |
| SQLAlchemy 2.0 với asyncio | ORM và thao tác database bất đồng bộ | 
| SQLite và PostgreSQL | Database cho môi trường cục bộ và triển khai tương ứng |
| Alembic | Quản lý thay đổi schema bằng migration |
| aiogram 3.x | Tích hợp Telegram Bot API, handler, keyboard và FSM |
| HTTPX | Giao tiếp HTTP giữa bot và API |
| Jinja2, HTMX và CSS | Render và cập nhật giao diện quản trị |
| pytest | Tổ chức và chạy kiểm thử tự động |

## 9 Database và phân phối dữ liệu

### 9.1 Flowchart database

![Flowchart phân phối database của Boconic](assets/flowchart-database.png)

*Hình 4. Database chung, các nhóm bảng và phạm vi dữ liệu cho user và admin.*

### 9.2 Các nhóm dữ liệu trong sơ đồ

Sơ đồ thể hiện 9 nhóm với tổng cộng 57 bảng. Toàn bộ như sau:

| Nhóm | Số bảng | Các bảng được thể hiện |
| --- | --- | --- |
| Danh tính và phân quyền | 9 | `users`, `user_locations`, `user_settings`, `admin_accounts`, `admin_sessions`, `roles`, `permissions`, `role_permissions`, `admin_role_assignments` |
| Catalog và thư viện | 7 | `books`, `authors`, `book_authors`, `publishers`, `book_copies`, `copy_coverage_ranges`, `library_entries` |
| Chương và tiến độ học | 6 | `chapters`, `chapter_proposals`, `user_chapter_progress`, `chapter_watches`, `topics`, `chapter_topics` |
| Nhu cầu và matching | 3 | `community_requests`, `support_offers`, `request_matches` |
| Mượn trả và người giữ | 5 | `borrow_requests`, `loans`, `handover_confirmations`, `loan_events`, `custody_events` |
| Tài liệu số và collection | 6 | `resources`, `media_files`, `chapter_resources`, `authorized_collections`, `collection_contributions`, `assembly_jobs` |
| Tổ chức và thiếu sách | 4 | `organizations`, `organization_members`, `parties`, `school_shortages` |
| Moderation và uy tín | 5 | `reports`, `user_blocks`, `reviews`, `trust_events`, `user_warnings` |
| Vận hành và hệ thống | 12 | `custom_field_definitions`, `background_jobs`, `outbox_events`, `notification_deliveries`, `audit_logs`, `system_settings`, `feature_flags`, `import_jobs`, `import_rows`, `export_jobs`, `saved_views`, `backup_jobs` |

## 10 Cấu trúc thư mục dự án

Các thư mục chính được tổ chức như sau:

| Đường dẫn | Nội dung |
| --- | --- |
| `app/admin/` | Route và template của Web Admin Console |
| `app/api/v1/` | API cho catalog, mượn trả, nhu cầu và dữ liệu cá nhân |
| `app/bot/` | Handler, keyboard và client HTTP của Telegram Bot |
| `app/core/` | Cấu hình, bảo mật, RBAC và logging |
| `app/db/` | Model SQLAlchemy và database session |
| `app/jobs/` | Worker, outbox và các tác vụ nền |
| `app/services/` | Logic nghiệp vụ dùng chung giữa các giao diện |
| `assets/` | Flowchart, ảnh giao diện và tài nguyên minh chứng |
| `data/` | Database cục bộ, file runtime và backup |
| `docs/` | Thiết kế kỹ thuật, ERD và hướng dẫn vận hành |
| `migrations/` | Các phiên bản migration Alembic |
| `scripts/` | Script setup, dữ liệu demo, backup và smoke test |
| `tests/` | Các kiểm thử tự động |

## 11 Set up .env

### 11.1 Những thông tin cần có

Cần set up sau:

```dotenv
APP_ENV=development
APP_TIMEZONE=Asia/Ho_Chi_Minh
APP_BASE_URL=http://localhost:8000

DATABASE_URL=sqlite+aiosqlite:///./data/boconic.db
# Nếu triển khai PostgreSQL, thay bằng URL phù hợp:
# DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/boconic

BOT_TOKEN=REPLACE_WITH_TOKEN_FROM_BOTFATHER
BOT_USERNAME=boconic_bot
BOT_API_KEY=REPLACE_WITH_RANDOM_INTERNAL_KEY

ADMIN_USERNAME=REPLACE_WITH_ADMIN_USERNAME
ADMIN_TELEGRAM_ID=REPLACE_WITH_NUMERIC_TELEGRAM_ID
ADMIN_LOGIN=admin
SECRET_KEY=REPLACE_WITH_RANDOM_SECRET

STORAGE_DIR=./data/storage
BACKUP_DIR=./data/backups
UPLOAD_MAX_MB=10
```

### Secret token data:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`STORAGE_DIR`, `BACKUP_DIR` và `UPLOAD_MAX_MB` quy định nơi lưu file, sao lưu và giới hạn upload. Khi chỉnh giới hạn này, cần kiểm tra cả dung lượng ổ đĩa và giới hạn ở reverse proxy nếu có. File `.env`, token và bản sao dữ liệu không được đưa vào phần minh chứng công khai. [5]

## 12 Khởi chạy sản phẩm

### 12.1 Ubuntu hoặc Linux

```bash
cp .env.example .env
# Chỉnh .env bằng token và cấu hình của bạn trước khi tiếp tục.
chmod +x start.sh
./start.sh
```

### 12.2 Windows

Tạo `.env` từ mẫu và chỉnh cấu hình trước, sau đó chạy tệp batch:

```cmd
copy .env.example .env
start.cmd
```

Không ghi đè `.env` đang sử dụng nếu đã cấu hình. Nếu không chạy được, kiểm tra Python, quyền truy cập thư mục và log do script tạo ra.

### 12.3 Docker Compose

Sau khi chuẩn bị `.env`, chạy tại thư mục có `compose.yaml`:

```bash
docker compose up --build
```

### 12.4 Địa chỉ truy cập

| Địa chỉ | Mục đích |
| --- | --- |
| `http://127.0.0.1:8000/admin` | Web Admin Console |
| `http://127.0.0.1:8000/docs` | Tài liệu API và giao diện thử endpoint |
| `http://127.0.0.1:8000/health/live` | Kiểm tra tiến trình API đang phản hồi |
| `https://t.me/boconic_bot` | Mở bot theo username của dự án |

## 13 Các vấn đề phát sinh - xung đột backend

| Nhóm | Tình huống trọng yếu | Kết quả mong đợi |
| --- | --- | --- |
| Mượn trả | Hai user cùng giữ chỗ một bản | Chỉ một giao dịch giữ chỗ thành công |
| Mượn trả | User mượn bản sách của mình | Yêu cầu bị từ chối |
| Xác nhận | Một bên xác nhận giao hoặc trả | Không chuyển sang trạng thái hoàn tất trước điều kiện hai bên |
| Thời hạn | Giữ chỗ quá 72 giờ | Xử lý hết hạn và lưu lịch sử theo quy trình |
| Matching | Nhu cầu nguyên cuốn gặp tài liệu một phần | Không báo là đã đáp ứng nguyên cuốn |
| Độ phủ | Các khoảng trang trùng nhau | Hợp khoảng được tính đúng, không đếm lặp |
| Chương học | Hai đề xuất sửa cùng dữ liệu | Phát hiện xung đột phiên bản, xử lý HTTP 409 |
| Quyền riêng tư | User truy cập dữ liệu của người khác | Backend từ chối hoặc lọc đúng phạm vi |
| Quyền admin | Tài khoản gọi API ngoài quyền được giao | Không thực hiện được thao tác |
| Xuất dữ liệu | Giá trị có thể bị hiểu thành công thức CSV | Không thực thi công thức ngoài ý muốn khi mở file |
| Thông báo | Worker restart hoặc gửi Telegram thất bại | Sự kiện có trạng thái, có thể kiểm tra và thử lại phù hợp |
| Sao lưu | Khôi phục database và file | Bản ghi và file vẫn đối chiếu, mở được |

## 14 Giới hạn hiện tại và hướng phát triển

Prototype đầu tiên đã tổ chức: ai đang cần, ai đang có, tài nguyên là gì và việc trao đổi đang ở bước nào. Những phần em cần tiếp tục hoàn thiện:

1. Hoàn tất fanout thông báo và lưu kết quả gửi cho từng người nhận, kiểm tra lại sau lỗi hoặc restart.
2. Tăng độ rõ ràng của kiểm duyệt tài nguyên và căn cứ quyền sử dụng; chỉ mở tổng hợp nội dung khi đủ điều kiện.
3. Cải thiện tính liên tục của hội thoại khi triển khai, với cơ chế lưu FSM bền vững phù hợp. 
4. Đối chiếu schema, menu, endpoint và test trên cùng phiên bản; cập nhật flowchart khi có thay đổi nghiệp vụ.
5. Thử nghiệm trong phạm vi nhỏ để đo thời gian tìm được sách, tỷ lệ nhu cầu được đáp ứng và tỷ lệ hoàn trả đúng hạn.
6. Em vẫn sẽ tiếp tục thử nghiệm sản phẩm, dù đây là dự án để apply vào CLB AI, nhưng các stack em làm vẫn còn sơ xài, vẫn chưa đủ các tiến trình liên quan đến AI, RAG, ... Ở các bản nâng cấp sau, em vẫn hy vọng nó sẽ biến thành sản phẩm thực để thật sự phục vụ triệt để được vấn đề này.

## 15 Cảm ơn

Để hoàn thiện bản thảo lần này, em đã tham khảo qua không ít ý kiến của các phụ huynh có con em đang học tập tại các cơ sở giáo dục, tham khảo qua ý kiến từ xưởng in của gia đình tại quê nhà, và không ít các tài nguyên liên quan đến AI quota, các telegram testing account.

Em cảm ơn các anh chị vì đã đọc qua về đề xuất của em, về mô hình và cách ứng dụng, về việc xây dựng, hoàn thiện sản phẩm. Em rất mong được là một thành viên của CLB để học hỏi và phát triển!

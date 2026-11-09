# k4f_chan — Hướng dẫn sử dụng

Ứng dụng Windows độc lập đọc chữ tiếng Anh từ vùng màn hình bạn chọn và dịch sang tiếng Việt. Đây là công cụ cộng đồng, không phải sản phẩm chính thức của NIKKE.

## Bắt đầu
1. Giải nén **toàn bộ** gói vào thư mục có quyền ghi. Giữ `k4f_chan.exe`, `_internal`, `models`, `assets` và các thông báo giấy phép cạnh nhau. Không chỉ sao chép riêng EXE.
2. Dùng Windows 10/11 x64 và cài OCR tiếng Anh trong Windows Language options nếu được yêu cầu. Để game ở chế độ cửa sổ hoặc không viền.
3. Chọn **OPUS offline** hoặc **GPT API**. OPUS đã kèm mô hình, chạy CPU, không cần mạng/key cho phần dịch và không tự chuyển sang API. Chất lượng theo ngữ cảnh có thể kém GPT.
4. Kênh 1 dành cho lời NIKKE. Kênh 2 dành cho lời/lựa chọn người chơi. Chọn riêng vùng chữ và bấm Bật dịch cho từng kênh. Không khoanh trùng vùng. Chuyển tab không dừng kênh khác. Xưng hô tự đổi theo trạng thái dịch của kênh 2, xem bên dưới.
5. Kéo thanh tiêu đề bảng chat để di chuyển, kéo cạnh/góc để đổi kích thước; cuộn để đọc lịch sử. Lịch sử tối đa 50 tin nhắn mỗi bảng, chỉ giữ trong phiên, không ghi vào settings.

Giao diện **k4f_chan** dùng ảnh nền cục bộ, tự canh theo kích thước cửa sổ và phủ tối để giữ chữ dễ đọc. Giữ `assets/interface-background.jpg` trong gói. Ảnh nền không được gửi lên API; việc đổi tên/giao diện không đổi vùng OCR, chức năng dịch hay nơi lưu key Windows hiện có.

## Tự đổi xưng hô theo cuộc hội thoại
- **Bật dịch cả hai kênh:** kênh 1 mặc định **em → anh**, kênh 2 **anh → em**.
- **Chỉ bật dịch kênh 1, tạm dừng kênh 2:** kênh 1 mặc định xưng **tôi**, gọi người đối thoại là **cậu/cô/anh…** theo ngữ cảnh, không mặc định người nghe là Commander. Phù hợp cảnh các NIKKE nói chuyện với nhau.
- Chỉ chuyển tab hoặc bấm **Mở khung chat** không đổi cách xưng hô. Bấm **Tạm dừng** hoặc đóng bảng chat kênh 2 sẽ dừng kênh đó và chuyển kênh 1 sang cách xưng hô trung tính.
- Khi đổi trạng thái kênh 2, nếu kênh 1 đang dịch thì câu đang hiện sẽ được đọc và dịch lại theo chế độ mới. Lịch sử cũ được giữ nguyên, không sửa lại các tin đã dịch. Chế độ chụp ảnh và khoanh vùng chỉ tạm dừng để thao tác, không phải nút chọn xưng hô.
- API xét ngữ cảnh; OPUS offline chỉ sửa ngôi tự xưng có căn chỉnh từ đáng tin cậy và giữ cách gọi người nghe do mô hình chọn, nên có thể kém tự nhiên hơn. Cả hai vẫn cần giữ đúng lời kể, tên riêng, số nhiều và quan hệ được nói rõ trong câu gốc.


## API và khóa cá nhân
- Với OpenAI, dùng endpoint chính thức `https://api.openai.com/v1`, model có trong tài khoản và **API key của chính bạn**. Phí API tách biệt gói ChatGPT.
- Nhập/nạp khóa chỉ đưa khóa vào bộ nhớ. Bấm **Lưu key vào Windows** nếu muốn ghi nhớ trong Windows Credential Manager của tài khoản Windows hiện tại trên máy hiện tại.
- Khóa được ràng buộc với endpoint HTTPS đã chuẩn hóa. Đổi endpoint sẽ xóa khóa cũ khỏi ô và tạm dừng kênh; không tự gửi khóa sang địa chỉ mới.
- Không có khóa của người đóng gói trong bản chia sẻ. Sao chép thư mục app không sao chép Windows vault. Không gửi key cho người khác, không đặt key trong ZIP.
- Không có dịch vụ lồng tiếng AI33 trong app: AI33 chỉ được dùng tạo giọng thuyết minh cho video hướng dẫn riêng.

## Chụp ảnh có bảng chat
Bình thường bảng chat bị loại khỏi ảnh chụp để hạn chế OCR đọc lại bản dịch. Bật **Chế độ chụp ảnh** ở đầu cửa sổ: hai kênh tạm dừng và bảng chat được cho phép xuất hiện trong ảnh. Dùng Win+Shift+S chọn vùng màn hình gồm game và chat; tắt chế độ chụp để tiếp tục những kênh đang chạy trước đó. Ghi riêng cửa sổ game có thể không lấy các bảng chat nằm ngoài game. Cơ chế loại khỏi ảnh phụ thuộc Windows/công cụ ghi hình, không phải ranh giới bảo mật.

## Dữ liệu và giới hạn an toàn
- Luồng đã rà soát đọc điểm ảnh màn hình và dùng Windows OCR tại máy; không chèn mã, sửa bộ nhớ game hoặc hook ghi bàn phím. Phím tắt dùng RegisterHotKey của Windows.
- OPUS dịch tại máy. Với API, **chữ OCR từ vùng đã chọn** được gửi tới endpoint bạn cấu hình, không phải ảnh trong luồng này. Vùng đó có thể chứa thông tin riêng tư ngoài game: chọn sát chữ, tránh toàn màn hình và tạm dừng trước khi mở thông tin nhạy cảm.
- Nhà cung cấp API nhận văn bản và thông tin kết nối thông thường; chính sách lưu trữ dữ liệu thuộc nhà cung cấp. Chỉ dùng endpoint đáng tin cậy; app không kiểm chứng người vận hành mọi endpoint tùy chỉnh.
- `settings.json` được tạo tại máy người dùng và chứa vùng OCR, vị trí bảng chat, bộ dịch, endpoint/model — **không chứa key hay lịch sử chat**. Hãy kiểm tra/xóa cấu hình cá nhân trước khi tự đóng gói lại.
- Không có cam kết 100% không mã độc, không bị anti-cheat hạn chế, hoặc không thể phân tích ngược chương trình. Bản này không có chữ ký số nhà phát hành; Windows có thể cảnh báo danh tiếng. Không tắt phần mềm bảo vệ để chạy app. Kiểm tra nguồn tải và SHA-256 trước khi dùng.
- Rà soát mã và quét bảo vệ là kiểm tra có phạm vi, không phải chứng nhận an toàn tuyệt đối. Các kết quả thực tế của bản phát hành được ghi trong `VERIFICATION.json`.

## Mang sang máy Windows khác
- Giải nén toàn bộ gói portable vào thư mục có quyền ghi; không chạy trực tiếp trong ZIP. **Không cần cài Python, Node.js, CUDA hoặc phần mềm dựng video.** OPUS chạy CPU và mô hình đã nằm trong gói.
- Cần **Windows 10/11 x64** và thành phần **OCR tiếng Anh của Windows**. Nếu app báo chưa có OCR, mở **Settings → Time & language → Language & region → English → Language options**, cài **Optical character recognition** rồi mở lại app. Gói portable không tự cài hay thay đổi thành phần Windows.
- Dùng OPUS không cần key/mạng cho phần dịch. Dùng API cần mạng và key riêng của người dùng. Key trong Windows vault của máy này không đi theo gói chia sẻ.
- Không thể bảo đảm mọi máy có cấu hình, driver hoặc chính sách bảo mật khác nhau đều giống máy đã thử. Xem phạm vi kiểm thử thực tế và giới hạn trong `VERIFICATION.json`; không tắt antivirus hay anti-cheat để khắc phục lỗi.


## Thành phần bên thứ ba
Phiên bản phần mềm và giấy phép đi kèm nằm trong `DEPENDENCIES.json` và `LICENSES/`. Mô hình OPUS có nguồn, revision và hash trong `models/opus/provenance.json`; nguồn Helsinki-NLP/OPUS, giấy phép Apache-2.0.

Qt/PySide6 được liên kết động, không có hạn chế sửa/thay thế thư viện trong gói này. Tham khảo LGPLv3 và thông báo kèm theo; mã nguồn tương ứng của PySide/Qt có tại các dự án chính thức:
- https://code.qt.io/cgit/pyside/pyside-setup.git/
- https://code.qt.io/cgit/qt/qtbase.git/
- https://download.qt.io/official_releases/QtForPython/
- https://github.com/OpenNMT/CTranslate2
- https://github.com/google/sentencepiece
- https://github.com/pywinrt/pywinrt
- https://github.com/pyinstaller/pyinstaller (bootloader exception áp dụng)

Ảnh nhân vật dùng làm biểu tượng và nền giao diện do người yêu cầu cung cấp; nhân vật, nhãn hiệu và hình ảnh game thuộc chủ sở hữu tương ứng. Gói này không cấp lại quyền đối với tài sản NIKKE và không tuyên bố liên kết với nhà phát hành. Kiểm tra quyền sử dụng trước khi phát hành rộng rãi hoặc thương mại.

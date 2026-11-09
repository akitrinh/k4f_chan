# k4f_chan

Công cụ Windows dịch hội thoại **NIKKE từ tiếng Anh sang tiếng Việt** bằng OCR tại máy, sử dụng **OPUS offline** hoặc API tương thích OpenAI do người dùng tự cấu hình.

**[Tải bản Windows portable](https://github.com/akitrinh/k4f_chan/releases/latest/download/k4f_chan-Portable.zip)** · **[Các bản phát hành](https://github.com/akitrinh/k4f_chan/releases)** · **[Hướng dẫn chi tiết](README-VI.md)**

> **Trạng thái bảo trì:** phát hành nguyên trạng để cộng đồng sử dụng, tìm hiểu và tự fork. Tác giả không có kế hoạch cập nhật tiếp hoặc cam kết hỗ trợ. Không có tính năng tự cập nhật.

## Dành cho người dùng

1. Tải `k4f_chan-Portable.zip` từ **Releases**; không tải nhầm gói **Source code** nếu chỉ muốn chạy app.
2. Giải nén **toàn bộ** ZIP vào thư mục có quyền ghi. Không chạy ngay trong ZIP hoặc chỉ lấy riêng EXE.
3. Mở `k4f_chan.exe`, chọn bộ dịch và khoanh sát vùng chữ tiếng Anh.
4. Bật dịch từng kênh cần dùng; kéo/đổi cỡ bảng chat cho vừa hai bên game.

Bản portable đã kèm Python/Qt, thư viện OPUS và mô hình. **Không cần cài Git, Python, Node.js hay CUDA để chạy bản portable.** OPUS chạy CPU, không cần API key hoặc kết nối mạng cho phần dịch.

### Yêu cầu

- Windows 10/11 **x64**.
- Thành phần **OCR tiếng Anh của Windows**. Nếu app báo thiếu, thêm English trong **Settings → Time & language → Language & region → Language options → Optical character recognition**.
- Dùng game ở chế độ cửa sổ/không viền; không bảo đảm tương thích mọi anti-cheat hay mọi công cụ chụp ảnh.
- Dùng API cần mạng, endpoint/model hợp lệ và key của chính người dùng. Phí API tách biệt gói ChatGPT.

### Hai kênh và xưng hô

- **Kênh 1:** lời NIKKE. Khi kênh 2 tắt, mặc định xưng **tôi**, gọi người nghe theo ngữ cảnh như cậu/cô/anh…; không mặc định là Commander.
- **Kênh 2:** lời/lựa chọn người chơi. Khi kênh này bật dịch, kênh 1 mặc định **em → anh**, kênh 2 **anh → em**.
- Chế độ dựa vào nút **Bật dịch/Tạm dừng**, không dựa vào việc chỉ mở bảng chat hay chuyển tab. Dòng **Xưng hô** cho biết chế độ hiện tại.
- Đổi trạng thái kênh 2 sẽ loại bỏ kết quả đang chờ của cách xưng hô cũ và cho phép dịch lại cùng câu; giữ nguyên lịch sử đã dịch.
- OPUS hiểu ngữ cảnh kém API: chỉ chỉnh ngôi tự xưng căn chỉnh chắc chắn trong chế độ trung tính, giữ cách gọi người nghe do mô hình chọn.

### Điều khiển

- **Ctrl+Alt+T:** bật/tạm dừng kênh đang chọn.
- **Ctrl+Alt+F:** đổi vùng hội thoại/toàn màn hình của kênh đang chọn. Toàn màn hình có thể đọc cả chữ riêng tư; ưu tiên khoanh vùng nhỏ.
- Nếu phím tắt bị ứng dụng khác chiếm, dùng nút trong giao diện. Kích hoạt phím tắt vật lý chưa được xác minh đầy đủ trong phiên kiểm thử ban đầu.
- Bật **Chế độ chụp ảnh** trước khi chụp hai bảng chat; app tạm dừng OCR/dịch rồi khôi phục các kênh trước đó khi tắt chế độ.

## Dữ liệu và an toàn

- Chỉ đọc điểm ảnh màn hình hiển thị qua Windows và nhận dạng OCR tại máy. Không chèn mã, đọc/sửa bộ nhớ game hoặc chặn lưu lượng game.
- OPUS dịch cục bộ. Trong luồng API, **chỉ chữ OCR** gửi tới endpoint đã cấu hình, **không gửi ảnh**. Chọn đúng vùng, tránh thông tin nhạy cảm.
- Key chỉ ở bộ nhớ nếu nhập/nạp. **Lưu key vào Windows** mới lưu vào Credential Manager, theo tài khoản Windows và endpoint HTTPS. Không có key dùng chung trong bản phát hành.
- `settings.json` chỉ chứa thiết lập/vị trí, không chứa key hay lịch sử chat. Không chia sẻ cấu hình cá nhân nếu không cần.
- Không có cam kết tuyệt đối về mã độc, anti-cheat, tài khoản game hay khả năng chống phân tích ngược. EXE chưa có chữ ký số; không tắt antivirus để chạy app. Đối chiếu SHA-256 của Release.
- Mã nguồn có thể được kiểm tra và sửa đổi; GitHub không phải chứng nhận an toàn. Các kiểm tra đã thực hiện được ghi ở phần release notes và tài liệu đi kèm.

## Chạy mã nguồn

Khác bản portable, chạy/build mã nguồn cần **Python 3.14 x64**, Windows OCR tiếng Anh và Internet để cài dependency ban đầu. Mô hình OPUS cùng tokenizers đã nằm trong `models/opus`; nguồn/revision/hash nằm trong `provenance.json`.

```bat
Setup.cmd
Launch.cmd
```

`Setup.cmd` tạo `.venv` trong repo và cài các phiên bản cố định từ `build-requirements.txt`. Không tìm key ngoài repo và không cần nhập key để dùng OPUS.

### Kiểm thử

```bat
.venv\Scripts\python.exe -B -m unittest test_voices test_subtitles test_capture test_credentials test_offline
```

Các kiểm thử tự động không gọi API thật hay đọc Windows vault cá nhân. Kiểm thử OPUS dùng mô hình đi kèm. Kết quả kiểm thử trên một máy không bảo đảm mọi bản Windows/CPU/driver/chính sách bảo mật đều giống nhau.

### Đóng gói

```bat
Build.cmd
```

Kết quả: `dist\k4f_chan\`. Giữ EXE, `_internal`, `models`, `assets`, thông báo giấy phép và tài liệu cạnh nhau. Không đóng gói `.venv`, cache, key, settings cá nhân hoặc file `.lnk` của máy build.

## Giấy phép và tài sản bên thứ ba

- Mã ứng dụng và script gốc: **[MIT](LICENSE)**, copyright akitrinh.
- Mô hình OPUS và thư viện bên thứ ba giữ giấy phép riêng: xem **[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**, `DEPENDENCIES.json`, `LICENSES/` và `models/opus/provenance.json`.
- **MIT không cấp lại quyền với ảnh nhân vật, biểu tượng, thương hiệu hoặc tài sản NIKKE.** Các ảnh do người yêu cầu cung cấp; quyền thuộc chủ sở hữu tương ứng. Kiểm tra quyền trước khi tái phân phối/thương mại hóa. Đây không phải sản phẩm chính thức hay được nhà phát hành NIKKE bảo trợ.
- Không có dịch vụ lồng tiếng AI33 trong app. Nhạc, giọng thuyết minh và dự án video hướng dẫn không nằm trong repo này.

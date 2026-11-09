# Thay đổi bản phát hành

## k4f_chan — giao diện ảnh nền
- Đổi tên ứng dụng, file chạy và gói portable thành k4f_chan; không đổi phạm vi khóa Windows để giữ key đã lưu.
- Thêm ảnh nền nhân vật cục bộ, co theo cửa sổ và canh vùng gương mặt; lớp phủ tối và các ô điều khiển bán trong suốt giữ chữ dễ đọc.
- Giữ nguyên hai kênh, tự đổi xưng hô, OCR, API và OPUS. Video và dự án dựng video không thay đổi.

## Tự đổi xưng hô theo kênh 2
- Kênh 2 bật dịch: kênh 1 mặc định em → anh, kênh 2 anh → em. Kênh 2 tắt: kênh 1 xưng tôi và gọi người nghe theo ngữ cảnh, không mặc định là Commander.
- Đổi trạng thái kênh 2 sẽ bỏ kết quả đang chờ của chế độ cũ và cho phép dịch lại cùng câu; không xóa hay viết lại lịch sử chat.
- Chụp ảnh/khoanh vùng chỉ tạm dừng thao tác; giữ chế độ xưng hô đến khi khôi phục xong. Đóng kênh 2 trong lúc tạm dừng không tự bật lại kênh đó.
- OPUS trung tính giữ cách gọi người nghe của mô hình, chỉ chỉnh ngôi tự xưng căn chỉnh đáng tin cậy. API dùng hướng dẫn theo ngữ cảnh; giữ ngôi kể, số nhiều, lời trích dẫn và quan hệ thân tộc rõ ràng.
- Cập nhật hướng dẫn và công thức dựng portable Windows x64. Bộ thư viện Python/Qt/OPUS được đóng kèm; OCR tiếng Anh là thành phần cần có của Windows.
- Sửa nạp mô hình OPUS trong đường dẫn tiếng Việt/có dấu bằng luồng tệp Unicode của Python; không tạo bản sao mô hình hay đòi đổi tên thư mục. Bổ sung MSVCP140 ở thư mục DLL dùng chung để tránh phụ thuộc bộ Visual C++ đã cài trên máy đóng gói.

## Bản nhận diện và bảo vệ khóa
- Biểu tượng mới tập trung gương mặt nhân vật, gồm icon Windows nhiều kích thước.
- Thêm lưu/nạp khóa qua Windows Credential Manager cho tài khoản Windows hiện tại; mỗi endpoint có phạm vi khóa riêng.
- Bỏ tự động tìm tệp API.txt bên ngoài thư mục app. Khóa nhập/nạp không tự được ghi vào Windows nếu chưa bấm nút lưu.
- Đổi endpoint sẽ xóa khóa cũ khỏi ô nhập và tạm dừng kênh tương ứng; lớp tạo yêu cầu cũng kiểm tra phạm vi endpoint.
- Gói chia sẻ không kèm khóa, settings cá nhân, lịch sử chat hoặc bản sao nguồn bảo trì.
- Giữ hai kênh độc lập, xưng hô anh/em, OPUS offline, xử lý con trỏ gạch dưới và chế độ chụp ảnh.
- Bổ sung video hướng dẫn tiếng Việt bằng Three.js + Remotion, thuyết minh Adam từ AI33 Clone.

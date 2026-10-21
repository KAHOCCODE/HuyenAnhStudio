# HUYỄN ẢNH Studio 0.3.2 — quy trình thống nhất

Ứng dụng desktop dành cho Windows để chỉnh hình, che phụ đề gốc, thêm chữ/logo, phụ đề Việt và giọng đọc. Giao diện làm việc theo năm bước với một bảng chỉnh cố định bên phải.

## 1. Cài đặt và mở

1. Đặt mã nguồn trong một thư mục riêng, ví dụ `E:\HuyenAnhStudio`. Nếu tải dạng ZIP, giải nén toàn bộ trước khi mở.
2. Máy cần Python **64-bit 3.11, 3.12 hoặc 3.13**. Nếu máy đã có Python 3.11.9 thì có thể dùng bản đó. Bộ cài tạo môi trường riêng, không dùng chung môi trường ứng dụng khác.
3. Máy cần **FFmpeg và FFprobe**. Nếu hai lệnh này chạy được trong CMD, không cần cài lại. Nếu chưa, đặt `ffmpeg.exe` và `ffprobe.exe` vào thư mục `tools` của app. Dùng bản có libass và libx264. Nguồn tải: https://ffmpeg.org/download.html
4. Chạy **`install.cmd`** một lần, có kết nối mạng để tải các thư viện.
5. Khi báo cài đặt xong, chạy **`start.cmd`**. Những lần sau chỉ mở `start.cmd`.

Đây là bản mã nguồn kèm trình khởi chạy, chưa phải tệp EXE độc lập. Không cần API key. Video được đọc và xử lý trên máy. Khi tạo giọng, văn bản câu phụ đề được gửi đến dịch vụ giọng nói trực tuyến qua Edge TTS; không gửi cả video lên dịch vụ này.

## 2. Năm bước thao tác

Thanh phía trên có năm bước. Các bước chỉnh hình, chữ/logo, phụ đề và giọng đọc đều là tùy chọn. Chuyển bước chỉ thay đổi giao diện, không tự bật vùng che, lật hình hay thay đổi dữ liệu dự án. Bảng chỉnh ở bên phải dùng chung, không mở thêm cửa sổ chỉnh hình/chữ. Khi tác vụ đang chạy, các thao tác sửa và chuyển bước được khóa; vẫn có thể bấm Hủy tác vụ.

### 1 · Nguồn

Bấm **Chọn / thay video…**. Tên, kích thước và thời lượng nguồn hiển thị ngay bên dưới. Trong **Khắc phục khi xem bị giật / mất tiếng** có tạo bản xem nhẹ toàn phim, dùng bộ phát CPU và chọn lại loa/tai nghe. Các bản xem nhẹ không làm thay đổi nguồn dùng khi xuất.

### 2 · Hình ảnh

**Che sub gốc** dành cho phụ đề hoặc chữ có sẵn trong hình. Bật vùng che, chọn vùng mẫu và kiểu mờ thường, mờ mềm, ô vuông/mosaic hoặc phủ màu. Bật **Kéo vùng che** để di chuyển và kéo góc dưới phải để đổi kích thước. Chế độ này tạm hiển thị hình nguồn để đặt vùng chính xác. Các thông số tọa độ, màu, độ đậm và quản lý nhiều vùng nằm trong phần nâng cao. Vùng chính áp dụng suốt video; các vùng thêm có mốc thời gian riêng. Mờ hay mosaic không khôi phục được cảnh thật phía sau chữ.

**Khung và màu** dành cho lật gương, crop/giữ đủ hình, zoom và tỷ lệ xuất. Có kích thước nguồn, ngang 16:9, dọc 9:16, vuông 1:1, 4:3 và kích thước tự nhập. Chọn tự nhập để mở rộng/cao; giá trị là số chẵn từ 64 đến 7680 px. Zoom từ 1 đến 3 lần. Kéo hình trên preview hoặc cuộn chuột để zoom khi đang ở tab này. Tọa độ crop, nền màu, nền mờ và viền nằm trong phần nâng cao; màu sắc và lớp phủ có phần riêng có thể mở rộng.

Đổi sang tab Khung và màu hoặc rời bước Hình ảnh sẽ tự thoát chế độ kéo vùng che. Thứ tự dựng là **che hình nguồn → lật / đổi khung → chữ, logo và phụ đề Việt**. Chữ có sẵn trong video bị lật; chữ Việt và logo thêm bằng app vẫn đúng chiều.

### 3 · Chữ / logo

Thêm chữ, ảnh logo PNG/JPG/WebP/BMP hoặc biểu tượng. Có mẫu thông báo hai dòng với vạch đỏ, cùng mẫu chữ viền trắng, vàng, nhãn nền tối và xanh ngọc. Biểu tượng có trái tim, ngôi sao, nút phát, nốt nhạc và thông tin.

Chọn một lớp trong danh sách rồi chỉnh nội dung, phông/cỡ/màu phù hợp loại lớp. Logo không hiện các thông số chữ; biểu tượng không hiện phần nhập văn bản. Kéo lớp trên preview để di chuyển, kéo góc dưới phải để đổi kích thước. **Vị trí, thời gian và trang trí** chứa tọa độ, mốc đầu/cuối theo giây nguồn, viền, bóng, nền, bo góc và vạch dọc. Tăng rộng/cao nếu chữ bị cắt trong khung.

Có thể nhân đôi, xóa hoặc đổi thứ tự lớp. Lớp cuối danh sách được vẽ trên các lớp trước; phụ đề SRT được ghép sau các lớp trang trí. Ảnh logo được tham chiếu bằng đường dẫn gốc; khi chuyển dự án sang máy khác, chọn lại ảnh nếu đường dẫn không còn đúng.

Bật **Chừa dải bên** nếu muốn đặt tên kênh/logo ở phần bên phải hoặc trái của khung. Các thông số nền và độ rộng chỉ hiện khi bật dải bên. Nút **Đặt lớp đang chọn vào dải bên** đưa lớp vào vùng đó. Kích thước xuất không đổi; nếu chưa bật chỉnh khung, video giữ đủ hình trong phần còn lại. Nếu đã bật, kiểu crop/fit/nền mờ đang chọn tiếp tục được dùng.

### 4 · Sub và giọng

Danh sách phụ đề tự hiện ở bước này. Bật **Dòng thời gian** khi cần chỉnh mốc hoặc chọn vùng. Bấm **Nhập SRT…** ở danh sách trái để nhập một hay nhiều tệp phụ đề Việt. SRT dùng mốc nguồn, mã hóa UTF-8 hoặc UTF-16 có BOM; câu vượt thời lượng nguồn cần sửa trước khi xuất. Các mục trống được giữ nhưng không hiện chữ và không đọc.

Trong **Kiểu phụ đề**, chọn một trong sáu mẫu, phông, cỡ và màu chữ. Vị trí phụ đề hiện ngay trong phần chính: chọn Trên/Giữa/Dưới hoặc nhập X/Y và chiều rộng. Bật **Kéo vị trí phụ đề trên video** để kéo khung vàng trên preview; vị trí áp dụng cho toàn bộ SRT và được giữ đúng chiều sau khi lật hình. Khi có dải bên, vị trí tính theo phần video còn lại. Viền, nền, in nghiêng, giãn chữ và hiện/ẩn mềm nằm ở phần nâng cao. Khi tự thay đổi thông số, bộ chọn mẫu hiển thị Tùy chỉnh nếu không còn khớp mẫu sẵn. Khi có dải bên, vị trí và chiều rộng phụ đề dựa trên phần video còn lại.

Nhấp đúp câu để sửa trong khung gắn ở đáy app. Mốc câu ở dạng 00:01:23,456 theo nguồn. Nội dung được áp dụng khi chuyển câu, rời bước, lưu hoặc bắt đầu tác vụ; mốc sai cần sửa trước. Kéo khối câu để dịch mốc, kéo mép để đổi thời lượng; giữ Ctrl để chọn nhiều và Shift+kéo để chọn vùng. Các thanh phụ đề và voice của cùng câu dùng chung mốc. Đóng/mở **Dòng thời gian** để có thêm diện tích xem; khi sửa câu, dòng thời gian tạm thu lại.

Trong **Âm thanh / giọng đọc**, mục **Tốc độ video dựng ×** nằm ngay trên phần tạo giọng, không ở trong nâng cao. Nếu lời quá dài, giảm tốc video trước (ví dụ 0,8×), rồi chọn giọng, tốc độ đọc và phạm vi, bấm **Tạo / cập nhật giọng đọc…**. Chỉ có một nút tạo, với bốn phạm vi: theo đợt, toàn bộ dự án, câu đang chọn hoặc vùng thời gian. Theo đợt phù hợp video dài. **Kiểm tra / sửa giọng đọc** chứa câu thiếu/lỗi, câu quá dài và lưu WAV. Số câu tạo đồng thời, giới hạn ép câu, xóa dữ liệu giọng và tách âm nền nằm trong phần nâng cao.

- Giọng ngắn hơn khoảng câu được thêm im lặng; giọng dài hơn được tăng tốc trong giới hạn. Nếu vẫn quá dài, sửa câu, tăng khoảng câu hoặc đổi thiết lập rồi tạo/ghép lại.
- MP3 có cùng văn bản, giọng và tốc độ được dùng lại khi chạy tiếp. Có tiến độ, thử lại khi lỗi và hủy tác vụ; không tự rút gọn văn bản.
- Các lượt dùng chung giới hạn 1–6 câu đồng thời, không nhân theo số lượt. App bắt đầu bằng 1 câu thật rồi tăng dần đến mức đã chọn. Khi lỗi tạm thời, các câu cùng chờ 5 rồi 10 giây (hoặc thời gian dịch vụ yêu cầu), chỉ 1 câu thử phục hồi; lỗi cùng thời điểm không cộng dồn thời gian chờ. Sau 3 lần dịch vụ không phục hồi, app dừng cả hàng đợi và giữ MP3 để chạy tiếp.
- Âm video gốc giảm cả tiếng nói, nhạc và hiệu ứng. **Tắt âm thanh gốc** bỏ toàn bộ tiếng này khi xem/xuất và giữ mức âm lượng cũ để khôi phục khi bỏ chọn. Giọng Việt có âm lượng riêng.
- **Giảm nền / chỉ giữ lời nói…** mở bộ tách AI: nền 0% dùng trực tiếp phần giọng đã tách; mức cao hơn trộn lại một phần nền. Có lọc nhẹ tiếng ù/nhiễu, có thể làm giọng mỏng đi. Hãy nghe lượt thử 30 giây trước khi áp dụng toàn video. Đổi mức nền hoặc lọc dùng lại các đoạn AI đã hoàn tất. Cần cài riêng bằng CAI-GIAM-NHAC.cmd, hoặc CAI-GPU-GTX.cmd cho DirectML. Không có cam kết tách sạch mọi tiếng động.
- Edge TTS cần mạng, văn bản được gửi tới dịch vụ ngoài và có thể gặp lỗi/giới hạn. Voice dài nhiều giờ cần thời gian và dung lượng; WAV mono 24 kHz dùng khoảng 173 MB/giờ, chưa tính tệp từng câu.

Nếu nhật ký báo **HTTP 403**, dịch vụ đang từ chối kết nối. Bản 0.3.2 dùng **edge-tts 7.3.1** thay cho 7.2.8 và dừng hàng đợi ngay khi gặp lỗi này. Đóng app, cập nhật mã rồi chạy **install.cmd** để cập nhật thư viện; chỉ git pull và mở lại chưa đủ. Giữ nguyên dự án và thư mục voice, sau đó chạy tiếp các lượt đang thiếu. Nhật ký ghi phiên bản Edge TTS khi tạo giọng. Nếu đã dùng 7.3.1 mà vẫn 403, kiểm tra ngày giờ Windows và mạng/dịch vụ, tránh chạy lại hàng nghìn câu liên tiếp. Nguồn sửa lỗi: [Edge TTS #490](https://github.com/rany2/edge-tts/issues/490), [bản 7.3.1](https://github.com/rany2/edge-tts/releases/tag/7.3.1).

### 5 · Xuất video

Đây là nơi duy nhất chọn chế độ và xuất video hoàn chỉnh. Kiểm tra kích thước, thời lượng nguồn/bản xuất và âm thanh trong phần tóm tắt. Bật **Ghép giọng Việt đã tạo** nếu cần; không có hộp thoại thứ hai để chọn lại âm thanh hay tự tăng âm gốc về 100%.

Ba mức xuất là Nhanh, Nhanh nhất tự dùng GPU và Nén gọn. Mức nhanh nhất thử NVIDIA NVENC, Intel Quick Sync, AMD AMF bằng một lượt mã hóa ngắn ở đúng kích thước; nếu không khả dụng sẽ dùng CPU ultrafast và ghi lý do vào nhật ký. Hai mức còn lại dùng CPU. GPU chỉ tăng tốc mã hóa; hiệu ứng và phụ đề vẫn có thể giới hạn tốc độ. Tiến độ hiển thị bộ mã hóa, tốc độ thực tế và thời gian còn lại; thời gian là ước tính.

**Xem thử 10 giây** bên dưới preview dùng cùng thiết lập hình và lựa chọn âm thanh/giọng Việt ở bước Xuất, bắt đầu tại con trỏ. Xem thử không tạo lại voice. Nếu đã chọn ghép giọng nhưng voice chưa hợp lệ, cần cập nhật hoặc bỏ chọn trước. **Xuất toàn bộ video…** luôn dựng từ đầu đến cuối, không phụ thuộc vùng timeline. Chọn tên MP4 mới; video nguồn và tệp đã có không bị ghi đè. Kết quả hoàn chỉnh mở trong trình phát của app.

Tốc độ dựng được chỉnh ở bước **Sub và giọng → Âm thanh / giọng đọc** trước khi tạo voice. **Tốc độ bản cuối và thời lượng** ở bước Xuất chỉ chỉnh tốc độ bản cuối. Tổng tốc độ bằng tích hai mức; thời lượng bản xuất bằng thời lượng nguồn chia tổng tốc độ. Ví dụ nguồn 7 giờ ở tổng tốc độ 0,7× thành 10 giờ. Đổi tốc độ dựng ảnh hưởng việc ghép giọng; đổi tốc độ cuối không gọi lại dịch vụ TTS. Có thể nghe theo tốc độ dựng hoặc bản cuối ở bước Sub và giọng. Giảm rồi tăng tốc trở lại không tạo thêm thời gian đọc trong bản cuối.

## 3. Lưu, cập nhật và khôi phục

**Lưu dự án** hoặc Ctrl+S lưu `.ha.json`: nguồn, SRT, vùng che, hiệu ứng, lớp chữ/logo, dải bên và âm lượng. **Dự án** chứa mở, tạo mới và lưu thành. Ctrl+Z/Ctrl+Y để hoàn tác/làm lại. Dự án cũ vẫn mở được; thiết lập mới có mặc định khi chưa lưu trong dự án.

App tham chiếu nguồn và ảnh logo, không sao chép chúng vào dự án. Voice nằm trong thư mục dữ liệu người dùng của app; giữ lại khi cần mở tiếp. Chuyển máy cần chọn lại nguồn/ảnh và mang theo dữ liệu voice hoặc tạo lại giọng.

Cập nhật: đóng app, chạy `git pull --ff-only origin feat/video-frame-effects` trong thư mục dự án rồi mở start.cmd. Chỉ cần cài lại thư viện nếu requirements thay đổi. Không xóa dự án, video hay bộ nhớ voice để xử lý lỗi giao diện.

Nếu lỗi, mở **Nhật ký**. Lỗi khởi động nằm trong startup-error.log cạnh main.py. Tùy chọn giải mã CPU, bản xem nhẹ và khôi phục loa nằm ở phần khắc phục của bước Nguồn.

## 4. Kiểm tra và giới hạn

Đã kiểm tra trên Linux với Qt chế độ không màn hình, có xuất MP4 thực tế. Chưa chạy trực tiếp trên máy Windows của bạn, chưa kiểm tra chất lượng tách AI hoặc dịch vụ TTS trên video thực tế của bạn. Preview có độ phân giải thấp hơn bản xuất; logo/chữ tĩnh được dựng một lần và ghép theo nhóm cùng thời gian. Không có cắt ghép nhiều nguồn hoặc keyframe cho vùng che.

Lệnh kiểm tra dành cho phát triển:

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Nguồn kỹ thuật: [FFmpeg](https://ffmpeg.org/ffmpeg-filters.html), [Qt](https://doc.qt.io/qtforpython-6/), [Edge TTS](https://github.com/rany2/edge-tts).

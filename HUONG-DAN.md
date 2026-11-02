# HUYỄN ẢNH Studio — bản 0.3.0

## Mới: giữ tốc độ đọc, làm chậm video cục bộ

- Giữ hai giọng Edge TTS hiện tại: Nam Minh và Hoài My. Không thêm dịch vụ trả phí.
- Trong **Lồng tiếng Edge TTS**, bật **Câu dài: làm chậm video, giữ giọng** (mặc định bật). Khi câu đọc dài hơn khoảng hình dành cho câu đó, app kéo dài đúng khoảng hình bằng cách phát chậm. Các câu sau và phụ đề được dời theo cùng đồng hồ mới; không tăng tốc TTS để nhét vào câu.
- Ví dụ câu từ `00:00:02,433` đến `00:00:03,233` có voice dài 2,567 giây: đoạn hình 0,8 giây được kéo thành 2,567 giây, kết thúc ở `00:00:05,000`; toàn bộ phần sau dời thêm 1,767 giây.
- Nếu SRT có các câu chồng mốc, phần hình của câu trước dừng ở mốc bắt đầu câu sau. Các câu cùng mốc bắt đầu được đọc lần lượt theo thứ tự SRT, có khoảng nghỉ 40 ms, trong cùng đoạn hình được kéo dài.
- Sau khi tạo/sửa voice, bấm **Phát** hoặc **Câu quá dài…** để ghép và tính lại thời gian. MP3 đã tạo được dùng lại, không gọi lại dịch vụ chỉ vì đổi cách đồng bộ.
- Timeline và các ô sửa vẫn dùng **mốc video gốc**. Khi lưu SRT chọn **Mốc bản cuối** để lấy mốc đã kéo giãn; SRT nguồn và dữ liệu mốc gốc không bị sửa chồng lên nhau.
- Xem trước dùng tốc độ video thay đổi theo từng đoạn. **Xuất vùng chọn / thử 10 giây** là cách kiểm tra bằng bộ dựng FFmpeg thật; vùng 10 giây nguồn có thể dài hơn 10 giây sau kéo giãn.
- **Tốc độ đọc (%)** vẫn là điều chỉnh bạn chủ động chọn. **Tăng tốc bản cuối ×** vẫn tác động cả hình lẫn voice; để `1,00×` nếu muốn giữ tốc độ giọng đã tạo.
- Tắt tùy chọn làm chậm video để dùng cách ép tốc độ giọng cũ. Cách cũ vẫn có thể tràn lời khi vượt giới hạn ép câu.
- **Tắt âm gốc khi lồng tiếng** mặc định bật để tiếng Trung không chồng với tiếng Việt. Tùy chọn này tắt cả nhạc và hiệu ứng gốc, không tách riêng tiếng nói. Bỏ chọn để trộn âm gốc theo mức **Âm gốc (%)**; khi đó tiếng Trung cũng có thể nghe thấy. Xuất không kèm voice vẫn giữ âm gốc theo mức đã chọn.
- Xuất chỉ một phần dùng mốc gốc của vùng đã chọn; lời nằm ngoài biên vùng sẽ được cắt theo biên đó. Xuất toàn video giữ đủ câu đọc cuối cùng.
- Xuất được chia thành các đoạn nhỏ, xử lý lần lượt với giới hạn luồng để giảm tải máy RAM 8 GB. Các đoạn chỉ mã hóa hình một lần; ghép cuối không mã hóa lại hình. Cần dung lượng đĩa tạm cho các đoạn trung gian. Video xuất giữ tỉ lệ khung nguồn và dùng 30 khung hình/giây; đoạn làm chậm có thể thấy lặp khung, không có nội suy chuyển động AI.

## Mới: cắt khung và lật ngang

- **Mở rộng khung xem** chỉ thay bố cục giao diện; tên mới giúp phân biệt với phóng/cắt hình thật.
- Trong **Cắt khung & lật hình**, tăng **Phóng để cắt ×** rồi chỉnh vị trí ngang/dọc để chọn phần hình giữ lại. Hoặc bấm **Chọn khung cắt trên hình**, kéo vùng muốn giữ trên hình gốc. Khung được điều chỉnh theo tỉ lệ video gốc, tối đa phóng 4 lần; phần ngoài khung bị loại bỏ, phần giữ lại được phóng đầy kích thước xuất ban đầu.
- **Lật ngang video** lật phần hình. Phụ đề tiếng Việt chính được đặt sau bước cắt/lật nên vẫn đọc bình thường. Vùng che bám theo tọa độ hình gốc và được cắt/lật cùng hình.
- **Khôi phục toàn khung** bỏ cắt và lật. Có hỗ trợ lưu dự án, hoàn tác và làm lại các thay đổi này.
- Cắt khung, lật hình và thay đổi tốc độ là công cụ biên tập; không có cam kết tránh Content ID.

## Kiểm tra cho người phát triển

Chạy `python -m unittest discover -s tests -v` sau khi cài các thư viện. Các bài kiểm tra dựng video dùng FFmpeg/FFprobe có libass và libx264; không gọi Edge TTS. Chúng kiểm tra ánh xạ thời gian, câu chồng mốc, câu cuối dài, SRT, tương thích dự án cũ, đổi chế độ/dùng lại MP3, xuất vùng, tốc độ bản cuối, tắt âm gốc và xuất nhiều đoạn.

Các mục bên dưới mô tả chức năng nền và cách ép tốc độ giọng cũ. Với chế độ làm chậm video mới đang bật, áp dụng quy tắc đồng bộ ở phần trên.

Ứng dụng desktop dành cho Windows, tập trung vào ghép phụ đề tiếng Việt, che phụ đề có sẵn và lồng tiếng. Bố cục tham khảo cách làm việc của trình dựng video như CapCut: danh sách nguồn/phụ đề ở trái, video ở giữa, thiết lập ở phải, timeline ở dưới. Không phải phần mềm của CapCut.

Ứng dụng dùng video và SRT bất kỳ bạn chọn. Không đi kèm, không chỉnh sửa và không phụ thuộc file SRT đã gửi để tham khảo.

## 1. Cài đặt và mở

1. Giải nén toàn bộ `HuyenAnhStudio-v0.1.0.zip` vào một thư mục riêng, ví dụ `F:\HuyenAnhStudio`. Không mở ứng dụng trực tiếp trong ZIP.
2. Máy cần Python **64-bit 3.11, 3.12 hoặc 3.13**. Nếu máy đã có Python 3.11.9 thì có thể dùng bản đó. Bộ cài tạo môi trường riêng, không dùng chung môi trường ứng dụng khác.
3. Máy cần **FFmpeg và FFprobe**. Nếu hai lệnh này chạy được trong CMD, không cần cài lại. Nếu chưa, đặt `ffmpeg.exe` và `ffprobe.exe` vào thư mục `tools` của app. Dùng bản có libass và libx264. Nguồn tải: https://ffmpeg.org/download.html
4. Chạy **`install.cmd`** một lần, có kết nối mạng để tải các thư viện.
5. Khi báo cài đặt xong, chạy **`start.cmd`**. Những lần sau chỉ mở `start.cmd`.

Đây là bản mã nguồn kèm trình khởi chạy, chưa phải tệp EXE độc lập. Không cần API key. Video được đọc và xử lý trên máy. Khi tạo giọng, văn bản câu phụ đề được gửi đến dịch vụ giọng nói trực tuyến qua Edge TTS; không gửi cả video lên dịch vụ này.

## 2. Quy trình chính

### Chọn nguồn

- Bấm **＋ Video** để chọn video trên máy.
- Bấm **＋ SRT** để nhập phụ đề tiếng Việt. File cần UTF-8 hoặc UTF-16 có BOM.
- SRT phải sử dụng mốc của video gốc đã chọn. App kiểm tra và chặn xử lý nếu có câu vượt thời lượng video.
- App giữ cả mục SRT trống; những mục này không hiện chữ và không được đọc.

### Đặt phụ đề và che chữ cũ

- Chọn một câu để nhảy video đến vị trí đó.
- Chỉnh phông, cỡ chữ, màu, in đậm, viền, bóng và chiều rộng trong bảng bên phải.
- Có ba kiểu sẵn: trắng viền đen, vàng viền đen, trắng nền đen.
- Kéo trực tiếp chữ trên khung video, hoặc nhập vị trí X/Y theo phần trăm khung hình.
- Bật **vùng che**, chọn làm mờ hoặc phủ màu. Chỉ vùng hình chữ nhật đã chọn bị tác động.
- Bật **Kéo vùng che**, kéo trong khung video để di chuyển. Kéo góc phải dưới để đổi kích thước; cũng có thể nhập X/Y/rộng/cao.
- Thu nhỏ vùng che vừa đủ ôm chữ Trung để hạn chế ảnh hưởng đến hình ảnh.
- Làm mờ chỉ che nội dung vùng chọn, không tái tạo cảnh bị chữ che khuất. Chữ cũ có thể vẫn lộ nếu chọn vùng hoặc cách che chưa đủ.
- Vùng che hiện áp dụng cố định suốt video; bản này chưa có keyframe cho vùng che di chuyển.

Khung xem trực tiếp mô phỏng kiểu chữ và vùng mờ để chỉnh nhanh. **Xuất thử 10 giây** dùng bộ dựng FFmpeg thật để kiểm tra kết quả, vì cách xuống dòng, bóng/viền và mức mờ có thể khác đôi chút giữa hai bộ hiển thị.

### Chỉnh câu và timeline

- Danh sách trái có ô tìm nội dung và bộ lọc câu voice quá dài.
- Chọn câu → sửa văn bản, bắt đầu, kết thúc → bấm **Áp dụng câu**.
- Mốc trong ô chỉnh câu là mốc **video gốc**, dạng `00:01:23,456`.
- Sửa trong ô sẽ được áp dụng khi chuyển câu, lưu dự án hoặc bắt đầu xuất/tạo voice. Mốc không hợp lệ phải sửa trước khi tiếp tục.
- Kéo khối câu trên timeline để di chuyển. Kéo mép trái/phải để đổi bắt đầu/kết thúc.
- Khối voice và phụ đề cùng một câu được liên kết: kéo ở một thanh sẽ thay đổi cùng mốc, không tách voice trôi sang câu khác.
- Thanh VIDEO đại diện cho toàn bộ nguồn. Bản này không có cắt ghép nhiều video hoặc nhiều lớp hình.
- Dùng thanh thu phóng, Ctrl + lăn chuột, thanh cuộn ngang hoặc **Vừa toàn bộ**.
- Bấm vùng trống trên timeline để tua. Có thanh tua bên dưới khung video và nút lùi/tiến 5 giây.
- Ctrl+Z hoàn tác, Ctrl+Y làm lại; lưu tối đa 40 bước trong phiên mở app. F11 vào/thoát toàn màn hình.

### Chọn tốc độ trước khi tạo giọng

Mọi câu luôn lưu mốc theo video gốc. Các tốc độ chỉ biến đổi cách phát và cách xuất; không sửa chồng lên mốc gốc sau mỗi lần điều chỉnh.

| Thiết lập | Ý nghĩa |
|---|---|
| Tốc độ dựng | Ví dụ 0,80×: video chậm lại, khoảng dành cho từng câu đọc dài gấp 1,25 lần. |
| Tăng tốc bản cuối | Áp dụng cùng lúc lên video, sub cứng và voice khi xuất. |
| Bản cuối về tốc độ gốc | Đặt tốc độ cuối bằng nghịch đảo tốc độ dựng. |
| Chế độ xem trước | Chọn nghe/xem theo tốc độ dựng hoặc theo tốc độ bản cuối. |

Ví dụ câu ở mốc gốc 10–12 giây:

- Dựng 0,80× → câu xuất hiện và voice được đặt ở 12,5–15 giây.
- Xuất tăng 1,25× → cả ba thành phần trở về mốc 10–12 giây.
- Voice cũng nhanh thêm 1,25× khi xuất. Vì vậy, làm chậm rồi tăng trở lại không tạo thêm thời gian đọc trong bản cuối. Hãy nghe thử ở chế độ **Theo tốc độ bản cuối**.

App dùng thay đổi tốc độ âm thanh có giữ cao độ bằng FFmpeg; ép quá nhanh vẫn làm giọng khó nghe. Hình ảnh xuất theo từng khung hình nên độ chính xác hiển thị bị giới hạn bởi tốc độ khung hình, dù SRT được lưu đến mili-giây.

### Tạo và nghe voice

- Chọn **Nam Minh · Nam** hoặc **Hoài My · Nữ**.
- Có tốc độ đọc chung và tốc độ cộng thêm riêng từng câu. Có thể chọn giọng riêng từng câu để luân phiên nam/nữ.
- **Nghe câu** tạo giọng câu đang chọn. Nếu câu đủ điều kiện, phát bản đã khớp thời lượng; nếu quá dài, phát bản chưa ép và thông báo rõ.
- Bấm **Tạo / cập nhật voice** để tạo toàn bộ.
- App đọc tuần tự, có tiến độ, thử lại khi kết nối lỗi và lưu từng MP3 đã hoàn tất. Bấm **Hủy tác vụ** để dừng. Khi chạy lại, câu có cùng nội dung/giọng/tốc độ sẽ dùng lại MP3 đã tạo.
- Voice ngắn hơn ô thời gian: thêm im lặng vào cuối ô. Voice dài hơn: tăng tốc trong giới hạn bạn chọn.
- Nếu vượt **Giới hạn ép câu**, app đánh dấu `Dài …×` và chưa ghép voice hoàn chỉnh. Không tự rút gọn nội dung hay cố tình cắt bỏ phần cuối lời đọc để vượt kiểm tra.
- Bạn có thể giảm tốc độ dựng, tăng giới hạn ép nếu chấp nhận giọng nhanh hơn, kéo dài khoảng câu hoặc tự sửa câu ngắn lại, rồi tạo tiếp. Nếu kéo dài mốc, kiểm tra không đè lời của câu kế tiếp.
- Thay đổi nội dung, mốc, giọng hoặc tốc độ dựng khiến bản voice tổng cần ghép lại. Đổi màu chữ, vùng che, âm lượng hoặc tốc độ cuối không cần gọi lại TTS.
- Voice dài nhiều giờ sẽ cần thời gian và dung lượng ổ đĩa; WAV mono 24 kHz dùng khoảng 173 MB mỗi giờ, chưa tính MP3 và WAV từng câu.
- Edge TTS cần mạng và phụ thuộc dịch vụ bên ngoài, có thể lỗi hoặc giới hạn kết nối. Không có cam kết sử dụng không giới hạn hay luôn hoạt động.

### Nghe cùng video và xuất

- Khi voice đã đầy đủ, bấm **Phát** để nghe cùng video.
- **Âm gốc** giảm toàn bộ âm thanh gốc, gồm giọng Trung, nhạc và hiệu ứng. Bản này chưa tách riêng giọng Trung khỏi nhạc. Đặt 0% để tắt toàn bộ âm gốc.
- **Voice Việt** chỉnh âm lượng lớp lồng tiếng.
- **Xuất thử 10 giây** bắt đầu tại vị trí đang xem, theo tốc độ bản cuối; có voice nếu bản voice đang hợp lệ. Nếu chưa có voice hợp lệ, đoạn thử chỉ chứa sub và âm gốc theo thiết lập.
- **Xuất video** cho chọn có hoặc không kèm voice. Xuất MP4 H.264/AAC với sub được ghi cứng vào hình.
- Khi xuất, sub được dựng theo mốc nguồn rồi toàn bộ hình được đổi tốc độ, vì vậy chữ bám theo video. Không cần tạo tệp trung gian chỉ để khóa sub.
- Không ghi đè video nguồn hoặc tệp MP4 đã tồn tại: chọn tên xuất mới.
- **Lưu SRT** có ba lựa chọn: mốc gốc, mốc dựng, mốc bản cuối.
- **Lưu voice WAV** lưu riêng lớp tiếng Việt theo **tốc độ dựng**.

## 3. Lưu và mở lại

- Ctrl+S hoặc **Lưu** tạo tệp dự án `.ha.json`, giữ nguồn video, toàn bộ phụ đề và thiết lập.
- App tham chiếu video gốc, không chép video vào dự án. Nếu video đã chuyển chỗ, lúc mở lại app sẽ yêu cầu chọn đúng nguồn.
- Voice được lưu ở thư mục dữ liệu người dùng của app, tách khỏi thư mục mã nguồn. Không xóa bộ nhớ voice khi đang cần dùng lại dự án.
- Chép riêng tệp dự án sang máy khác không mang theo video và bộ nhớ voice. Cần chọn lại video và tạo lại voice trên máy mới.
- Cập nhật mã nguồn sau này: đóng app, thay các tệp chương trình; giữ nguyên các tệp dự án và video. Chỉ chạy lại `install.cmd` nếu thư viện thay đổi.

## 4. Kiểm tra và giới hạn bản này

Đã kiểm tra trên môi trường Linux chạy Python 3.12 và Qt chế độ không màn hình:

- Mở giao diện, nạp danh sách SRT dài, chỉnh câu, tự áp dụng khi chuyển câu, hoàn tác, đổi tốc độ.
- 9 bài kiểm tra tự động: giữ mili-giây/mục trống/nhiều dòng, từ chối SRT sai, cập nhật bộ nhớ voice, căn vị trí âm thanh theo mẫu, ghép im lặng, hủy tác vụ, chặn voice cũ, xuất MP4 thực tế.
- Xuất thử cả phủ màu và làm mờ, sub tiếng Việt, phối âm và hai mức tốc độ. Đo thời lượng tệp và kiểm tra chữ/âm thanh trước–trong–sau khoảng câu.

Chưa chạy thử trực tiếp trên máy Windows của bạn. Lệnh gọi trực tiếp danh sách giọng Edge TTS trong môi trường kiểm tra bị hết thời gian chờ, nên chưa xác minh được tải giọng thật tại đây. Phần xử lý âm thanh đã được kiểm tra bằng âm tổng hợp, không được coi là kiểm thử dịch vụ TTS trực tiếp. Sau khi cài, hãy dùng **Nghe câu** và **Xuất thử 10 giây** trước khi tạo cả phim dài.

Nếu lỗi, mở **Nhật ký** để lấy thông báo. Lỗi khởi động được ghi vào `startup-error.log` cạnh `main.py`. Không xóa video hay dự án để xử lý lỗi cài thư viện.

Muốn tự chạy kiểm tra dành cho phát triển:

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Nguồn kỹ thuật

- Edge TTS: https://github.com/rany2/edge-tts
- FFmpeg filters: https://ffmpeg.org/ffmpeg-filters.html
- Qt video: https://doc.qt.io/qtforpython-6/PySide6/QtMultimediaWidgets/QGraphicsVideoItem.html

Ảnh `Giao-dien.png` được chụp từ giao diện thật của ứng dụng, dùng nền minh họa và ba câu mẫu tự tạo; không phải video hay SRT của người dùng.


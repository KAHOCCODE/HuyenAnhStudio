# HUYỄN ẢNH Studio — bản 0.1.0

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
- **Tắt âm thanh gốc** tắt toàn bộ lời thoại, nhạc và hiệu ứng của video khi xem và xuất, kể cả âm đã xử lý giảm nhạc. Voice Việt vẫn giữ riêng. Bỏ chọn để khôi phục mức âm lượng trước đó; trạng thái này được lưu cùng dự án.
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

## Tùy chỉnh khung hình và màu sắc

Trong **03 THIẾT LẬP**, mở **Khung hình & màu sắc…**. Các ô nhập luôn thao tác được; thay đổi thông số hoặc kéo hình sẽ tự bật tùy chỉnh.

- **Kích thước xuất:** giữ kích thước gốc, 16:9 (1920×1080), 9:16 (1080×1920), 1:1 (1080×1080), 4:3 (1440×1080), hoặc tự nhập rộng/cao. Kích thước tự nhập phải là số chẵn, từ 64 đến 7680 px.
- **Zoom:** chọn nhanh 110% / 115% hoặc nhập từ 1 đến 3 lần. X/Y điều chỉnh vị trí lấy hình; 50/50 là chính giữa.
- **Cách đặt video:** lấp đầy và cắt mép; giữ đủ hình trên nền màu; nền video làm mờ; hoặc nền mờ kèm viền động. Với nền mờ, có thể chỉnh khoảng nền và độ mờ. Viền động nằm quanh khung xuất.
- **Lật ngang:** bật thủ công khi phù hợp nội dung. Chữ có sẵn trong phim cũng bị lật; phụ đề Việt và chữ thay thế do ứng dụng thêm vẫn đọc bình thường.
- **Màu sắc:** chỉnh độ bão hòa, tương phản, độ sáng và tông lạnh/ấm. Giá trị trung tính lần lượt là 1, 1, 0, 0.
- **Lớp phủ:** sương sáng nhẹ, bụi sáng chuyển động hoặc ánh sáng chuyển động. Cường độ từ 0 đến 0,3; đặt 0 để bỏ tác động.

Bấm **Xem thử 10 giây** để áp dụng thiết lập và xuất đoạn thử từ vị trí đang xem. Đoạn thử có voice nếu voice đã ghép còn khớp với dự án; nếu chưa có, dùng âm gốc theo mức âm lượng đã chọn. Preview chính cũng hiển thị thay đổi khung hình, màu và hiệu ứng khi phát hoặc dừng video. Khi bật chế độ đặt vùng che/chọn vùng chữ, preview tạm trở về hình nguồn để đặt tọa độ chính xác; tắt chế độ đó để xem lại hiệu ứng.

Các thiết lập được lưu cùng dự án và có thể hoàn tác. Thay đổi tự áp dụng vào dự án đang mở; **Đặt lại** đưa về mặc định, **Đóng** chỉ đóng bảng chỉnh. Dùng hoàn tác nếu cần bỏ thay đổi. Tắt tùy chỉnh để dùng lại luồng xuất gốc. Có thể xuất video chỉ chỉnh hình mà không cần SRT; chọn **Không** khi được hỏi xuất kèm voice.

Vùng che xử lý trước khi đổi bố cục. Chữ thay thế trên hình đi theo nội dung nên có thể bị cắt nếu nằm ngoài vùng crop. Phụ đề SRT được vẽ sau khi đổi khung và chỉnh màu, theo vị trí phần trăm của khung xuất, nên không bị lật hay crop theo video nguồn.

### Chỉnh trực tiếp trên video

- Mở **Khung hình & màu sắc…** để hiện bảng chỉnh bên phải, nằm trong cửa sổ app.
- Giữ chuột trái kéo ngay trên preview chính để đổi bố cục. Với khung vừa khít ở zoom 100%, tăng zoom hoặc chọn tỷ lệ khác để có khoảng dịch hình.
- Cuộn chuột trên preview để zoom. X/Y/Zoom cập nhật theo thao tác và dùng cho bản xuất.
- Preview cập nhật sau một nhịp xử lý ngắn, cả khi video đang dừng. Bản xem được dựng ở độ phân giải tối đa 960×540 để giảm tải; bản xuất vẫn dùng kích thước đã chọn. Không cần xuất thử 10 giây chỉ để thấy thay đổi.
- **Lưu thiết lập** áp dụng vào trạng thái dự án đang mở. **Đóng** giữ thay đổi; dùng **Lưu dự án** để giữ cho lần mở sau. Bỏ tích bật tùy chỉnh để trở lại hình gốc.

### Ba mức xuất và tốc độ xử lý

Bảng chỉnh dùng chung lựa chọn tốc độ xuất của app: `ultrafast` (nhanh nhất), `veryfast` và `medium`. Mức nhanh hơn thường tạo tệp lớn hơn. Cả ba mức đều áp dụng khi xuất video đã đổi khung. Xuất thử 10 giây dùng `ultrafast`.

Bộ giải mã preview tạm dừng trong lúc xuất để tránh tranh tài nguyên. Nền mờ được xử lý ở kích thước nhỏ rồi phóng lên; các bước chỉnh màu trung tính được bỏ qua. Thời gian xuất vẫn phụ thuộc độ dài, độ phân giải, hiệu ứng và CPU; chọn mức nhanh nhất nếu ưu tiên thời gian.

### Áp dụng vào video hoàn chỉnh

Sau khi chỉnh khung, bấm **Áp dụng & xuất toàn bộ video** ngay dưới khung chỉnh. Chọn giữ nguyên âm lượng video gốc, dùng âm lượng theo dự án, hoặc ghép voice Việt. Chọn nơi lưu MP4 mới; ứng dụng xuất từ đầu đến cuối với khung, màu và hiệu ứng đã chọn, không phụ thuộc vị trí con trỏ hoặc vùng timeline. Không cần có SRT hay voice nếu chọn âm gốc, và không bắt buộc lưu tệp dự án trước khi xuất.

Xuất xong, bản hoàn chỉnh được mở trong cửa sổ phát của ứng dụng, có thanh tua và nút phát/tạm dừng. Bấm **Về chỉnh sửa** để trở lại dự án gốc. Video nguồn không bị ghi đè và hiệu ứng không bị áp dụng hai lần lên bản đã xuất. **Lưu thiết lập** chỉ lưu thay đổi vào trạng thái dự án đang mở, không dựng lại video; **Xem thử 10 giây** chỉ tạo đoạn thử. Dùng **Lưu dự án** nếu muốn giữ thiết lập cho lần mở sau.

### Xuất nhanh bằng GPU

Mức **Nhanh nhất · tự dùng GPU** kiểm tra NVIDIA NVENC, Intel Quick Sync rồi AMD AMF bằng một lượt mã hóa ngắn ở đúng kích thước xuất. Nếu dùng được, app xuất H.264 bằng bộ mã hóa đó; nếu không, dùng CPU ultrafast và ghi lý do vào nhật ký. Hai mức còn lại tiếp tục dùng CPU như trước. Xuất thử cũng kiểm tra GPU.

Tiến độ hiển thị tên bộ mã hóa, tốc độ thực tế (ví dụ 2× nghĩa là xử lý khoảng hai giây video đầu ra mỗi giây) và thời gian còn lại. Ước tính bắt đầu sau 15 giây, vẫn có thể thay đổi theo cảnh. GPU chỉ tăng tốc mã hóa; vùng che, phụ đề, đổi khung và hiệu ứng vẫn xử lý trên CPU. Chất lượng và dung lượng tệp giữa các bộ mã hóa có thể khác nhau. Không có cam kết thời gian xuất cố định.

## Che sub → lật hình → chữ, logo và phụ đề Việt

Thanh thao tác bên dưới preview có bốn bước: **1 · Che sub**, **2 · Lật gương**, **3 · Chữ / logo**, **4 · Chèn SRT**. Vùng che được dựng trên video nguồn trước khi lật. Chữ, logo, biểu tượng thêm bằng bảng mới và phụ đề SRT được ghép trên khung xuất sau bước lật, nên luôn đúng chiều.

### Che phụ đề gốc

Trong **Che phụ đề tiếng Trung**, chọn mờ thường, mờ mềm, ô vuông/mosaic hoặc phủ màu; chỉnh cường độ, màu, độ đậm và vị trí. Có vùng mẫu cho dải dưới rộng/hẹp, dải trên và dải tối dưới hình. Bật **Kéo vùng che** để chỉnh trên tọa độ nguồn; tắt để xem bản dựng đã lật/đổi khung. Nút **2 · Lật gương** tự thoát chế độ đặt vùng che để hiển thị ngay kết quả lật.

**Thêm nhiều vùng che…** quản lý các vùng riêng, có thời gian hiện. Để chỉ che chữ, để trống nội dung chữ thay thế. Mờ hay mosaic chỉ che nội dung bằng hiệu ứng; không phục hồi được hình thật phía sau chữ.

### Chữ / logo / biểu tượng

Bảng này nằm trong app, tự áp dụng vào preview và bản xuất. Có thể thêm nhiều lớp chữ, ảnh logo PNG/JPG/WebP/BMP và năm biểu tượng vẽ sẵn: trái tim, ngôi sao, nút phát, nốt nhạc, thông tin. Mỗi lớp có tên, bật/tắt, mốc đầu/cuối theo giây nguồn, vị trí, kích thước và độ hiện. Dùng **Hiện suốt video** cho nhận diện kênh.

- Chữ có phông, cỡ, đậm, căn trái/giữa/phải, màu, viền, bóng, nền, độ hiện nền, bo góc và vạch dọc. Các mẫu gồm trắng có viền, thông báo vạch đỏ, vàng, nhãn nền tối và xanh ngọc. Hai dòng mẫu “Phim được làm bởi AI / Khán giả trên 18+” có thể sửa tự do, giống ảnh mẫu đã gửi.
- Chọn lớp rồi kéo ngay trên preview để di chuyển; kéo vùng góc dưới phải để đổi kích thước. Nới chiều cao/rộng nếu chữ bị cắt trong khung. Tọa độ lớp tính theo toàn khung xuất, không đi theo crop hay lật của hình nguồn.
- Danh sách hỗ trợ nhân đôi, xóa, lên/xuống. Lớp ở cuối danh sách được vẽ trên các lớp trước. Phụ đề SRT luôn nằm trên lớp trang trí.
- **Dải bên** chừa một phần khung xuất bên phải hoặc bên trái, có màu và độ rộng 10–40%. Bấm **Đặt lớp đang chọn vào dải bên** để chuyển chữ/logo vào đó; việc này cũng áp dụng cho biểu tượng. Kích thước xuất không đổi. Nếu chưa bật tùy chỉnh khung, video giữ đủ hình trong phần còn lại; nếu đã bật, cách crop/fit/nền mờ hiện chọn vẫn được dùng.
- Ảnh logo được tham chiếu theo đường dẫn gốc. Khi chuyển dự án sang máy khác, giữ ảnh hoặc chọn lại ảnh qua **Chọn / thay ảnh logo**. Các lớp và dải bên được lưu trong `.ha.json`, hỗ trợ hoàn tác.

Chữ/logo tĩnh được vẽ thành ảnh một lần cho mỗi lần dựng, ghép các lớp liền nhau có cùng mốc thời gian để giảm số bước xử lý. Preview dùng cùng thứ tự ghép với bản xuất, ở độ phân giải thấp hơn.

### Phụ đề Việt

Nhập SRT bằng **4 · Chèn SRT**, rồi chỉnh tại **Phụ đề**. Có sáu mẫu: trắng viền đen, vàng viền đen, trắng nền tối, trắng ngà điện ảnh, xanh ngọc viền tím, hồng nhạt nền tím. Có thể chỉnh màu viền/nền, in nghiêng, giãn chữ và thời gian hiện/ẩn mềm 0–500 ms. Chữ được dựng sau bước lật. Khi có dải bên, vị trí và vùng xuống dòng của phụ đề dựa trên phần video còn lại.

### Chỉ giữ lời nói

**Chỉ giữ lời nói · nền 0%…** mở bộ tách nhạc với mức trộn lại nền bằng 0. Phần giọng đã tách được dùng trực tiếp, không đọc và trộn lại toàn bộ âm gốc thêm lần nữa. Có tùy chọn lọc nhẹ tiếng ù/nhiễu sau tách; nên nghe thử vì lọc có thể làm giọng mỏng đi. Các đoạn AI đã xử lý được dùng lại khi đổi mức giữ nền hoặc bật lọc, không chạy lại AI cho đoạn đã hoàn tất.

Đây vẫn là bộ tách AI đang dùng, không có cam kết xóa sạch mọi tiếng động hay giữ nguyên hoàn toàn lời thoại. Hãy dùng lượt thử 30 giây và so sánh âm gốc/kết quả trước khi xử lý toàn bộ. **Tắt âm thanh gốc** là lựa chọn riêng để bỏ toàn bộ tiếng trong video, chỉ giữ voice Việt khi xuất kèm voice.

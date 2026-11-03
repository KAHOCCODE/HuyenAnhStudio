# HUYỄN ẢNH Studio 0.3.8 — thêm chế độ thử lại từng câu

## Cập nhật từ nhánh đang dùng

Đóng ứng dụng rồi chạy trong CMD như trước:

```bat
cd /d E:\HuyenAnhStudio
git pull --ff-only origin feat/video-frame-effects
install.cmd
start.cmd
```

Chạy **install.cmd** sau khi kéo mã để cài Edge TTS 7.2.8 cho đợt thử. Chỉ chạy git pull sẽ chưa đổi phiên bản thư viện.

## Bản 0.3.8: gửi song song và thử lại từng câu

Trong **4 · Sub và giọng → Âm thanh / giọng đọc → Chế độ gửi**, chọn **Thử lại từng câu · tối đa 6** rồi đặt **Số câu tạo cùng lúc** từ 1 đến 6. Hộp chạy theo đợt cũng có lựa chọn này. App thử một câu trước; có âm thanh thành công mới mở số kết nối đã chọn. Giới hạn dùng chung giữa tất cả các lượt, không phải 6 kết nối cho mỗi lượt.

- Khi gặp **NoAudioReceived**, mỗi câu có tối đa **9 lần gửi tổng cộng**. Khoảng chờ tăng theo lần thử: 1,5 giây × số lần đã thử, cộng ngẫu nhiên dưới 1 giây. Câu đang chờ không giữ chỗ kết nối; những câu khác vẫn tiếp tục. Phản hồi rỗng không tự làm giảm tải hoặc dừng toàn bộ hàng đợi trong chế độ này.
- Câu vẫn lỗi sau 9 lần được ghi vào danh sách lỗi; các câu còn lại tiếp tục. Dùng **Rà thiếu / thử lại câu lỗi** để chạy lại phần thiếu. Không đổi lời hoặc giọng tự động.
- Chế độ **Tự giảm tải · tối đa 2** vẫn là mặc định, kể cả dự án cũ: tối đa 5 lần/câu, giảm tải và nghỉ chung 10/20/40 giây khi lỗi rỗng dồn dập. Phần hướng dẫn phục hồi bên dưới áp dụng cho chế độ này.
- Cả hai chế độ vẫn nghỉ chung khi gặp HTTP 429/lỗi mạng và dừng khi HTTP 403 hoặc lỗi chứng chỉ. Không tắt kiểm tra HTTPS. Chế độ 6 kết nối không bảo đảm dịch vụ sẽ luôn trả âm thanh hoặc nhanh hơn.
- Đổi chế độ gửi không làm mất MP3 đã tạo; chạy tiếp dùng lại âm thanh hợp lệ của dự án. Không cần cài FastAPI, mở máy chủ hoặc cài thêm thư viện. MP3 được kiểm tra có âm thanh bằng FFprobe, không loại câu ngắn chỉ vì tệp dưới 1 KB.

## Bản 0.3.7: giảm tải và thử phục hồi trước khi dừng

- Sửa trường hợp tạo được vài câu rồi nhiều phản hồi rỗng từ cùng một đợt làm app dừng quá sớm. Các lỗi đang chạy cùng đợt chỉ khởi động một khoảng nghỉ chung; không cộng thành nhiều đợt phục hồi thất bại.
- Trong chế độ Tự giảm tải, giới hạn là 1–2 kết nối cho toàn bộ lượt. Dự án cũ lưu 6 vẫn mở được và tự giới hạn khi chạy; không cần sửa file dự án. Chỉ tăng từ 1 lên 2 sau 4 câu thành công liên tiếp.
- Khi lỗi dồn dập, app ghi rõ thời gian nghỉ chung 10, 20, 40 giây. Sau mỗi khoảng nghỉ chỉ 1 yêu cầu thử phục hồi; thành công thì tiếp tục và tăng tải từ từ. Có thể bấm Hủy trong lúc nghỉ.
- Không xóa giọng đã tạo. Chạy lại lượt cũ dùng lại MP3 thành công, chỉ gửi các câu còn thiếu.

## Mới: tạo giọng và xử lý NoAudioReceived

- Bản thử dùng `edge-tts==7.2.8` với hai giọng Nam Minh và Hoài My để kiểm tra lỗi NoAudioReceived.
- Trong chế độ Tự giảm tải, câu lỗi được xếp lại sau các câu chưa thử, tối đa 5 lần/câu. Lỗi dồn dập không còn bị dừng ngay sau 8 phản hồi rỗng: app nghỉ chung 10 giây rồi chỉ 1 câu thử phục hồi. Nếu chưa được, nghỉ 20 rồi 40 giây; sau 3 đợt nghỉ và thử vẫn lỗi mới tạm dừng. Những phản hồi đã đang chạy từ cùng một đợt không bị đếm thành nhiều lần phục hồi thất bại.
- Thời lượng MP3 mới được ghi vào bộ nhớ đệm sau khi kiểm tra; bước chuẩn bị âm thanh dùng lại kết quả thay vì chạy FFprobe lần hai. Không cần xóa giọng đã tạo.
- Vào **4 · Sub và giọng → Âm thanh / giọng đọc → Kiểm tra kết nối hai giọng**. App gửi đúng một câu mẫu ngắn cho mỗi giọng, báo có/không có âm thanh, thời gian chờ hoặc loại lỗi; không lưu file thử và không sửa dự án. Kết quả chỉ phản ánh thời điểm kiểm tra.
- Mỗi yêu cầu dùng giới hạn kết nối 10 giây, chờ dữ liệu 30 giây; câu ngắn còn có giới hạn tổng 45 giây, câu dài được nới theo độ dài. Có thể hủy khi đang gửi hoặc đang chờ lượt thử lại.
- Nếu vẫn lỗi, dùng **Rà thiếu / thử lại câu lỗi** để chạy lại phần thiếu. Xem nút kiểm tra kết nối trước khi chạy lại toàn bộ; nếu một giọng lỗi còn giọng kia hoạt động, bạn tự chọn giọng phù hợp. Không cam kết khắc phục hoàn toàn việc dịch vụ Edge trả rỗng.

## Mới: làm chậm hình thay vì ép nhanh câu đọc

- Ở **4 · Sub và giọng → Âm thanh / giọng đọc**, tùy chọn **Câu dài: làm chậm video, giữ giọng** mặc định bật. App giữ tốc độ giọng đã tạo, kéo dài đoạn hình tương ứng và dời những câu sau cùng phụ đề. Không sửa chồng lên mốc SRT gốc.
- Ví dụ đoạn `00:00:02,433 → 00:00:03,233` dài 0,8 giây, voice dài 2,567 giây: hình đoạn này phát chậm đến `00:00:05,000`; phần sau dời thêm 1,767 giây.
- Nếu mốc SRT chồng nhau, khoảng hình của câu trước được giới hạn bởi mốc bắt đầu câu sau. Các câu có cùng mốc bắt đầu được đọc lần lượt theo thứ tự SRT, có khoảng nghỉ 40 ms.
- Bấm **Phát** hoặc **Câu quá dài…** để ghép lại giọng đã có sau khi chỉnh. MP3 cũ được dùng lại; không gọi lại Edge TTS chỉ vì đổi chế độ đồng bộ. Timeline và các ô sửa vẫn dùng mốc nguồn; khi lưu SRT chọn **Mốc bản cuối** để lấy mốc sau kéo giãn.
- Giữ **Tăng tốc bản cuối × = 1,00** nếu muốn giữ nguyên tốc độ giọng đã tạo. Tốc độ đọc thủ công và tốc độ bản cuối vẫn có tác dụng khi bạn chủ động chỉnh. Bỏ chọn làm chậm video để dùng chế độ ép giọng cũ.
- **Tắt âm gốc khi ghép giọng Việt** mặc định bật, tránh thoại Trung nghe chồng lên tiếng Việt. Nó tắt cả nhạc và hiệu ứng gốc, không tách riêng tiếng nói. Bỏ chọn nếu muốn trộn âm nguồn theo mức âm lượng đang đặt. Tùy chọn tắt âm gốc riêng vốn có vẫn được giữ.
- **Xem thử 10 giây** kiểm tra kết quả dựng bằng FFmpeg. Đoạn nguồn 10 giây có thể dài hơn sau khi giãn. Xuất toàn video giữ đủ câu đọc cuối; xuất vùng chỉ giữ lời trong đúng biên vùng đã chọn.
- Bản xuất đồng bộ dùng 30 fps, có thể thấy lặp khung ở đoạn chậm; không có nội suy chuyển động AI. Xử lý lần lượt các đoạn nhỏ, hỗ trợ bộ mã hóa GPU đang có và dùng CPU khi không khả dụng. Cần dung lượng đĩa tạm; ghép cuối không mã hóa lại hình.
- Chỉnh cắt khung/lật vẫn ở **2 · Hình ảnh → Khung và màu**; chữ/logo và phụ đề Việt giữ đúng chiều. Cắt/lật không bảo đảm tránh Content ID.

Kiểm tra dành cho người phát triển: `python -m unittest discover -s tests -v`. Các bài kiểm tra mới dựng video và âm thanh tổng hợp bằng FFmpeg, không gọi Edge TTS; cần thử thêm trên Windows với video thực tế.

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

Trong **Âm thanh / giọng đọc**, mục **Tốc độ video dựng ×** nằm ngay trên phần tạo giọng, không ở trong nâng cao. Nếu lời quá dài, giảm tốc video trước (ví dụ 0,8×), rồi chọn giọng, tốc độ đọc và phạm vi, bấm **Tạo / cập nhật giọng đọc…**. Chỉ có một nút tạo, với bốn phạm vi: theo đợt, toàn bộ dự án, câu đang chọn hoặc vùng thời gian. Theo đợt phù hợp video dài. **Kiểm tra / sửa giọng đọc** chứa câu thiếu/lỗi, câu quá dài và lưu WAV. Chế độ gửi và số câu tạo đồng thời hiện ngay trong phần giọng đọc. Giới hạn ép câu, xóa dữ liệu giọng và tách âm nền nằm trong phần nâng cao.

- Giọng ngắn hơn khoảng câu được thêm im lặng. Khi bật làm chậm video, câu dài kéo giãn đoạn hình và dời các câu sau; khi tắt, app tăng tốc giọng trong giới hạn đã đặt.
- MP3 có cùng văn bản, giọng và tốc độ được dùng lại khi chạy tiếp. Có tiến độ, thử lại khi lỗi và hủy tác vụ; không tự rút gọn văn bản.
- Trong chế độ **Tự giảm tải**, các lượt dùng chung tối đa **2 kết nối**, kể cả dự án cũ đã lưu 3–6. App bắt đầu bằng 1 kết nối, chỉ tăng lên 2 sau 4 câu thành công liên tiếp của đợt hiện tại. Khi có phản hồi rỗng, app về 1 kết nối. Hai lỗi liên tiếp bắt đầu đợt nghỉ chung; phản hồi cũ đang chạy được thu hồi mà không kéo dài thêm thời gian nghỉ. Câu lỗi được thử lại sau các câu mới, tối đa 5 lần/câu. Không tự đổi lời hoặc giọng đọc.
- Khi bị giới hạn **429**, lỗi mạng hoặc lỗi dịch vụ, các câu cùng chờ 5 rồi 10 giây (hoặc thời gian dịch vụ yêu cầu), chỉ 1 câu thử phục hồi; sau 3 lần chưa phục hồi thì dừng. Trong chế độ Tự giảm tải, với **NoAudioReceived dồn dập**, dùng các đợt nghỉ 10, 20, 40 giây và thử lần lượt bằng 1 câu trước khi dừng. Lỗi chứng chỉ HTTPS vẫn dừng ngay, không tắt xác minh TLS. Có thể hủy khi đang nghỉ. MP3 đã thành công và lỗi của các câu đã xử lý được giữ để chạy tiếp.
- Âm video gốc giảm cả tiếng nói, nhạc và hiệu ứng. **Tắt âm thanh gốc** bỏ toàn bộ tiếng này khi xem/xuất và giữ mức âm lượng cũ để khôi phục khi bỏ chọn. **Giọng Việt (%)** trong **4 · Sub và giọng → Âm thanh / giọng đọc** chỉnh riêng từ **0 đến 600%**: 100% giữ mức giọng đã tạo, 200% khuếch đại 2 lần, 300% là 3 lần. Mức trên 100% có bộ giới hạn đỉnh để hạn chế vỡ tiếng; độ lớn cảm nhận còn phụ thuộc bản giọng và phần âm gốc đang trộn.
- Mức giọng Việt được dùng khi nghe trên timeline, nghe từng câu, xem thử 10 giây, xuất toàn bộ video và lưu giọng WAV. Đổi âm lượng dùng lại MP3/giọng đã ghép, không cần gọi lại TTS. Lần đầu nghe mức trên 100%, app chuẩn bị một bản âm thanh tăng âm, giữ nguyên video và giọng gốc. Video dài cần chờ xử lý phần âm thanh này; cùng mức và cùng nguồn được dùng lại, giữ tối đa hai bản tăng âm cho mỗi nguồn khi có thể xóa tệp cũ. Giảm về 100% hoặc thấp hơn dùng trực tiếp giọng gốc. Khi đang nghe thử một câu, đổi mức sẽ dừng câu đó; bấm nghe câu lại để dùng mức mới. Bản xuất và WAV luôn áp dụng mức đang chọn trực tiếp.
- **Giảm nền / chỉ giữ lời nói…** mở bộ tách AI: nền 0% dùng trực tiếp phần giọng đã tách; mức cao hơn trộn lại một phần nền. Có lọc nhẹ tiếng ù/nhiễu, có thể làm giọng mỏng đi. Hãy nghe lượt thử 30 giây trước khi áp dụng toàn video. Đổi mức nền hoặc lọc dùng lại các đoạn AI đã hoàn tất. Cần cài riêng bằng CAI-GIAM-NHAC.cmd, hoặc CAI-GPU-GTX.cmd cho DirectML. Không có cam kết tách sạch mọi tiếng động.
- Edge TTS cần mạng, văn bản được gửi tới dịch vụ ngoài và có thể gặp lỗi/giới hạn. Voice dài nhiều giờ cần thời gian và dung lượng; WAV mono 24 kHz dùng khoảng 173 MB/giờ, chưa tính tệp từng câu.

Nếu nhật ký báo **HTTP 403**, app dừng hàng đợi và giữ MP3 đã tạo. Edge TTS 7.2.8 từng gặp lỗi này. Nhật ký ghi phiên bản thư viện khi tạo giọng để tiện đối chiếu. [Edge TTS #490](https://github.com/rany2/edge-tts/issues/490)

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


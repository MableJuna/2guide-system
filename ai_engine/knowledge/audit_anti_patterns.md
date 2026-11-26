# Báo Cáo Đối Chiếu & Anti-Patterns AI 2Guide Nhà Tù Hỏa Lò

- **Nguồn dữ liệu**: `Bao_cao_doi_chieu_danh_gia_AI_2Guide_Hoa_Lo.xlsx`
- **Tổng câu kiểm định**: 500 | **CSV tự chấm CORRECT**: 97.0%
- **Thực tế Đúng trọng tâm**: 2.2% | **Đúng phân khu (gồm chung chung)**: 60.0%
- **Tỷ lệ Bỏ & No-Data**: 14.8% | **Không dùng được**: 40.0% | **Độ trễ TB**: 61.10 ms

## 1. Thống kê Baseline theo 14 Phân Khu

| Zone ID | Phân khu | Tổng câu | Đúng trọng tâm | Đúng phân khu | Sai/Lạc đề | Từ chối sai | Safety Guard | Tỷ lệ Trúng | Nhận định |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Z01 | Cổng chính & Kiến trúc tổng thể | 36 | 2 | 25 | 7 | 2 | 0 | 5.6% | Khá ổn định phần giới thiệu 1896 nhưng Groq LLM bịa năm Di tích 1990 & từ chối sai câu mái ngói. |
| Z02 | Khu phòng giam tập thể | 38 | 2 | 14 | 15 | 3 | 4 | 5.3% | Bị xáo trộn sang Cachot, Cổng chính, Giá vé 50k; 3/4 ca Groq bị từ chối sai hoặc sai sử học. |
| Z03 | Ngục tối (Cachot) | 36 | 1 | 22 | 10 | 1 | 2 | 2.8% | Nhận diện phân khu tạm ổn (63.9%), nhưng HL-079/HL-103 lạc sang Máy chém; mất dữ kiện chi tiết. |
| Z04 | Khu D & Xà lim tử hình | 36 | 2 | 27 | 6 | 0 | 1 | 5.6% | Tỷ lệ phủ phân khu tốt (80.6%), có HL-118 khớp chính xác buồng 1 Hoàng Văn Thụ. |
| Z05 | Máy chém & Công cụ tra tấn | 40 | 1 | 31 | 3 | 0 | 5 | 2.5% | 80% ghép vào mẫu Máy chém, nhưng hầu như không trả lời các công cụ khác (gông, xiềng, roi, còng). |
| Z06 | Khu trại giam nữ & Tù nhi | 34 | 0 | 26 | 2 | 1 | 5 | 0.0% | 73.5% vào đúng mẫu Trại Nữ nhưng đều quá chung chung; bỏ qua Nguyễn Thị Quang Thái & Tù nhi. |
| Z07 | Cống ngầm & Vượt ngục | 36 | 0 | 28 | 7 | 0 | 1 | 0.0% | Lỗi sử học hệ thống ở cả 30/30 câu T07 ('16 tử tù thoát an toàn ra phố Thợ Nhuộm'). |
| Z08 | Sân trại giam & Cây bàng lịch sử | 30 | 3 | 26 | 0 | 1 | 0 | 10.0% | Phân khu tốt nhất (100% không lạc đề trừ 1 câu bị từ chối), trùng khớp 3 công dụng cây bàng. |
| Z09 | Trường học cách mạng & Báo chí trong tù | 36 | 0 | 16 | 10 | 0 | 10 | 0.0% | 27.8% rơi Safety Guard; T09 V1 chứa lỗi sử học 'báo viết bằng máu'; 10 câu lạc sang Cây bàng/Tour đêm. |
| Z10 | Kỷ vật chiến sĩ cách mạng | 40 | 0 | 0 | 24 | 4 | 12 | 0.0% | ĐIỂM MÙ TRI THỨC: 0% đạt, 40% bỏ/fallback và 60% ghép nhầm sang khu khác. |
| Z11 | Khu trưng bày phi công Mỹ (1964–1973) | 44 | 0 | 38 | 3 | 2 | 1 | 0.0% | 86.4% ghép vào cùng 4 mẫu Hanoi Hilton lặp đi lặp lại; 0% trả lời số liệu/phi công cụ thể. |
| Z12 | Đài tưởng niệm & Bức phù điêu | 30 | 0 | 26 | 2 | 0 | 2 | 0.0% | 86.7% nhắc đến Lê Liên/Tri ân nhưng trượt toàn bộ câu hỏi chất liệu đá, năm 2000, nghi thức dâng hoa. |
| Z13 | Khu chức năng nhà tù cũ | 30 | 0 | 0 | 19 | 1 | 10 | 0.0% | ĐIỂM MÙ TRI THỨC: 0% đạt (Bệnh xá, Bếp, Xưởng, Nhà xác hoàn toàn vắng bóng trong bộ nhớ). |
| Z14 | Đêm thiêng liêng & Bảo tồn hiện nay | 34 | 0 | 10 | 18 | 0 | 6 | 0.0% | Bị đụng từ khóa nặng: hỏi túi tote rơi vào Cây bàng, hỏi chống ẩm tủ kính rơi vào Khu D. |

## 2. Các Quy Luật Sai Sót Cần Chặn (Anti-Patterns P0/P1)

### [AP-01 - P0] Zones: Z07, Z04 (Ghi nhận: 37 lượt)
- **Lỗi ghi nhận**: Nói sai rằng 16 tử tù vượt ngục đêm Noel 1951 đều thoát hết ra phố Thợ Nhuộm.
- **Hướng dẫn chặn bắt buộc**: Khẳng định tổng cộng ~17 người chui qua cống ngầm góc sân nam ra gần khu Quán Sứ / Đấu xảo; do bị lộ nên chỉ 5 chiến sĩ thoát hẳn ra vùng tự do, số còn lại bị bắt lại.
- **Mẫu tiêu biểu**: HL-017, HL-022, HL-126, HL-221, HL-222, HL-223, HL-224, HL-225

### [AP-02 - P0] Zones: Z05 (Ghi nhận: 19 lượt)
- **Lỗi ghi nhận**: Nhầm chiều cao khung 4m thành hành trình rơi lưỡi dao, hoặc gây hiểu nhầm Nguyễn Thái Học bị chém ngay tại sân Hỏa Lò ('nơi đây').
- **Hướng dẫn chặn bắt buộc**: Phân biệt rõ: khung cao ~4 m, hành trình rơi lưỡi dao thép vát chéo 45° (nặng 40–50 kg) là ~2 m; máy chém được tháo rời chở tàu hỏa lên Yên Bái hành quyết Nguyễn Thái Học & 12 đồng chí ngày 17/6/1930.
- **Mẫu tiêu biểu**: HL-079, HL-148, HL-152, HL-156, HL-160, HL-123, HL-150, HL-154

### [AP-03 - P0] Zones: Z09 (Ghi nhận: 6 lượt)
- **Lỗi ghi nhận**: Nói tù nhân Hỏa Lò viết báo chí bí mật bằng máu.
- **Hướng dẫn chặn bắt buộc**: Khẳng định báo tù viết bằng mẩu bút chì kẹp ống sậy hoặc mực tự chế (nước cơm, thuốc đỏ, nước chanh, phẩm tím) trên giấy quyến / vỏ bao thuốc lá, KHÔNG viết bằng máu.
- **Mẫu tiêu biểu**: HL-065, HL-294, HL-306, HL-312, HL-321, HL-336

### [AP-04 - P0] Zones: Z01, Z02, Z14 (Ghi nhận: 11 lượt)
- **Lỗi ghi nhận**: Các lỗi Groq LLM bịa sử học (HL-025, HL-029, HL-044, HL-048, HL-068): bịa năm Di tích 1990, nói khe dưới cửa không đưa cơm, nói mô hình khẩu phần là cả 1 ngày, quở trách du khách về ảnh Xô Viết Nghệ Tĩnh.
- **Hướng dẫn chặn bắt buộc**: Xếp hạng Di tích Quốc gia ngày 18/6/1997 (QĐ 1543/QĐ-VH); khe dưới cửa sắt dùng đưa cơm nước; mô hình cơm/cá mắm là khẩu phần MỘT bữa (ngày 2 bữa); tôn trọng ngữ cảnh ảnh Xô Viết Nghệ Tĩnh 1930–1931 và không quở trách du khách.
- **Mẫu tiêu biểu**: HL-018, HL-019, HL-025, HL-029, HL-030, HL-042, HL-044, HL-047

### [AP-05 - P1] Zones: Z01, Z03, Z06, Z08, Z10, Z11, Z13 (Ghi nhận: 11 lượt)
- **Lỗi ghi nhận**: Từ chối nhầm (False Refusal) 15 câu hợp lệ về Phan Bội Châu, Lương Văn Can, Đông Kinh Nghĩa Thục, phi công Mỹ cắt tóc, bản vẽ Pháp, thủ tục sổ sách nhập trại, hiện vật gỗ bàng/khăn tay.
- **Hướng dẫn chặn bắt buộc**: Tuyệt đối KHÔNG từ chối bất kỳ câu hỏi nào nhắc đến nhân vật lịch sử, địa danh đày ải liên quan Hỏa Lò (Côn Đảo, Sơn La, ga Hàng Cỏ), tù binh Mỹ hay hiện vật trưng bày tại Di tích.
- **Mẫu tiêu biểu**: HL-034, HL-076, HL-215, HL-279, HL-343, HL-347, HL-349, HL-351

### [AP-06 - P1] Zones: Z01, Z02, Z03, Z04, Z05, Z06, Z07, Z08, Z09, Z10, Z11, Z12, Z13, Z14 (Ghi nhận: 73 lượt)
- **Lỗi ghi nhận**: Lệch dạng câu hỏi (73/230 câu nhánh Yes/No): mở đầu bằng 'Dạ đúng rồi quý khách!' trước câu hỏi mở ('bao nhiêu / tại sao / ai / lựa chọn A hay B').
- **Hướng dẫn chặn bắt buộc**: Với câu hỏi mở hoặc câu hỏi lựa chọn (A hay B), đi thẳng vào dữ kiện chi tiết ngay câu đầu tiên; cấm dùng tiền tố 'Dạ đúng rồi'.
- **Mẫu tiêu biểu**: HL-010, HL-012, HL-014, HL-021, HL-033, HL-037, HL-041, HL-049

## 3. 13 Ca Groq Cloud AI Thực Tế

- **HL-018 (Z01 — Đúng phân khu (Chung chung))**: [902 ms] Đúng hướng chính nhưng tự thêm hoặc thiếu dữ kiện nền (ví dụ '12 dãy/sân tập thể dục' hoặc bỏ qua lớp vữa cũ)
- **HL-019 (Z01 — Bỏ câu (Từ chối sai))**: [795 ms] Câu hỏi hợp lệ về hiện vật/lịch sử Hỏa Lò nhưng bị Guardrail/LLM từ chối
- **HL-025 (Z01 — Sai / Lạc đề / Lỗi sự kiện)**: [606 ms] Sai công năng ban đầu 1896, sai nhân vật (Lê Hồng Phong), không trả lời việc giam riêng/chung
- **HL-029 (Z01 — Sai / Lạc đề / Lỗi sự kiện)**: [655 ms] Sai năm xếp hạng Di tích Quốc gia: nói 1990 (thực tế 18/6/1997) & mở cửa 1993
- **HL-030 (Z01 — Đúng phân khu (Chung chung))**: [970 ms] Đúng hướng chính nhưng tự thêm hoặc thiếu dữ kiện nền (ví dụ '12 dãy/sân tập thể dục' hoặc bỏ qua lớp vữa cũ)
- **HL-035 (Z01 — Đúng trọng tâm)**: [406 ms] Groq AI giải thích chính xác, trực tiếp câu hỏi
- **HL-042 (Z02 — Bỏ câu (Từ chối sai))**: [546 ms] Câu hỏi hợp lệ về hiện vật/lịch sử Hỏa Lò nhưng bị Guardrail/LLM từ chối
- **HL-043 (Z02 — Đúng trọng tâm)**: [625 ms] Groq AI giải thích chính xác, trực tiếp câu hỏi
- **HL-044 (Z02 — Sai / Lạc đề / Lỗi sự kiện)**: [763 ms] Nói sai ngược công năng khe dưới cửa sắt ('không phải để đưa cơm nước')
- **HL-047 (Z02 — Bỏ câu (Từ chối sai))**: [757 ms] Câu hỏi hợp lệ về hiện vật/lịch sử Hỏa Lò nhưng bị Guardrail/LLM từ chối
- **HL-048 (Z02 — Sai / Lạc đề / Lỗi sự kiện)**: [1750 ms] Khẳng định mô hình cơm/cá mắm bé là khẩu phần 'cả một ngày' (sai định mức 2 bữa)
- **HL-051 (Z02 — Bỏ câu (Từ chối sai))**: [1718 ms] Câu hỏi hợp lệ về hiện vật/lịch sử Hỏa Lò nhưng bị Guardrail/LLM từ chối
- **HL-068 (Z02 — Sai / Lạc đề / Lỗi sự kiện)**: [1273 ms] Quở trách du khách 'nhầm lẫn', phủ nhận ảnh bắt tù Xô Viết Nghệ Tĩnh & gom 1930–1954 thành chống Pháp

## 4. 11 Ca Smart Guardrail Từ Chối Nhầm

- **HL-034 (Z01 | Bản vẽ thiết kế kiến trúc gốc của người Pháp)**: Bản vẽ mặt bằng kiến trúc của Nhà tù Hỏa Lò trưng bày trên vách kính này do kiến trúc sư người Pháp nào thiết kế và có giống các nhà tù ở Sài Gòn hay Côn Đảo thời đó không?
- **HL-076 (Z03 | Kích thước cực kỳ chật hẹp của một ô xà lim đơn)**: Khi nhìn qua cánh cửa vào một ô Cachot trước mắt, căn phòng này rộng chưa tới 2–3 mét vuông mà trần lại thấp như vậy—làm sao một người trưởng thành có thể duỗi thẳng chân tay?
- **HL-215 (Z06 | Cuộc chuyển trại của các nữ tù từ Hỏa Lò đi các nhà lao khác)**: Sau khi xử án tại Hà Nội, nhiều nữ tù chính trị bị giam ở đây sau đó có bị đày đi nhà tù Sơn La, Phú Thọ hay Khám Lớn Sài Gòn không?
- **HL-279 (Z08 | Những hộp khắc nhỏ từ gỗ bàng hoặc vỏ quả bàng)**: Ngoài quản bút và đũa, tôi nghe nói có chiến sĩ còn chạm khắc hình ngôi sao hoặc chữ kỷ niệm lên mảnh gỗ cành bàng khô tặng bạn tù trước ngày chuyển đi Côn Đảo phải không?
- **HL-343 (Z10 | Chiếc khăn tay thêu tên hoặc ngày tháng kỷ niệm khi rời trại)**: Trên chiếc khăn vải nhỏ có thêu dòng ngày tháng và vài chữ ký tên—đó có phải là món quà các bạn tù cùng thêu tặng nhau làm kỷ niệm trước khi một người bị đày đi Côn Đảo hoặc Sơn La?
- **HL-347 (Z10 | Những bức tượng bán thân hoặc ảnh chân dung các vị lãnh tụ từng bị giam)**: Trong lịch sử, cụ Phan Bội Châu—nhà chí sĩ yêu nước đầu thế kỷ XX—cũng từng bị thực dân Pháp giam giữ tại Nhà tù Hỏa Lò từ năm 1925 trước khi đưa về an trí ở Huế đúng không ạ?
- **HL-349 (Z10 | Cụ Lương Văn Can và các sĩ phu phong trào Đông Kinh Nghĩa Thục)**: Các sĩ phu yêu nước trong phong trào Đông Kinh Nghĩa Thục đầu thế kỷ XX như cụ Lương Văn Can, Nguyễn Quyền... trước khi bị đày Côn Đảo cũng đều từng bị giam qua Hỏa Lò phải không?
- **HL-351 (Z10 | Bức ảnh chụp cổng sau hoặc xe tù chuyển phạm nhân đi Côn Đảo, Sơn La)**: Trong ảnh tư liệu chụp đoàn tù nhân mang xiềng cổ nối tiếp nhau lên xe ra ga Hàng Cỏ—Hỏa Lò ngày ấy có vai trò là trạm trung chuyển tập trung tù chính trị cả miền Bắc để đi đày Côn Đảo, Sơn La phải không?
- **HL-373 (Z11 | Mảnh xác máy bay Mỹ (A-4E / F-4 / B-52) trưng bày minh họa)**: Mảnh hợp kim máy bay bị biến dạng có in số hiệu không quân Mỹ đặt trong gian này thuộc chiếc máy bay bị bắn rơi trong chiến dịch Sấm Rền hay chiến dịch Điện Biên Phủ trên không năm 1972?
- **HL-401 (Z11 | Cảnh các phi công Mỹ tắm giặt và cắt tóc tại sân trại)**: Trong ảnh các tù binh Mỹ cắt tóc cho nhau ngay dưới sân có ánh nắng—dụng cụ kéo tông-đơ cắt tóc được ban quản lý trại cấp định kỳ hay có thợ cắt tóc riêng?
- **HL-448 (Z13 | Hệ thống sổ sách lưu trữ hồ sơ phạm nhân bằng tiếng Pháp)**: Trên bàn làm việc có những cuốn sổ đăng ký phạm nhân dày cộp đánh số trang cẩn thận; mỗi tù nhân khi nhập trại Hỏa Lò phải trải qua những thủ tục ghi chép, khám xét gì?

## 5. 5 Khuyến Nghị Kiến Trúc Trọng Tâm

- **[P0 - Khẩn cấp] Thay bộ tự chấm từ khóa (Evaluation Illusion)**: Dùng LLM-as-a-Judge đối chiếu theo (Question, Reference Answer, AI Response) + luật bắt buộc: Refusal trên tập in-scope = INCORRECT; Safety Guard = NO_DATA. *(Mục tiêu: Đo đúng chất lượng thực, loại bỏ ảo giác 97%.)*
- **[P0 - Khẩn cấp] Chỉnh sửa gấp sai sót sử học trong Episodic Memory**: Hiệu đính toàn bộ tri thức gốc theo tài liệu chuẩn của BQL Di tích Nhà tù Hỏa Lò trước khi nạp lại vector/memory. *(Mục tiêu: 0% lỗi sử học trong tri thức nền (Golden Facts).)*
- **[P1 - Cao] Chuyển từ 13 đoạn văn cố định sang Hybrid RAG theo hiện vật**: Lập chỉ mục dữ liệu chi tiết cho tất cả 14 phân khu & 200+ hiện vật (câu hỏi-đáp án theo ID hiện vật hoặc Beacon/QR vị trí đứng của khách). *(Mục tiêu: Nâng Đúng trọng tâm từ 2.2% lên >75–85%.)*
- **[P1 - Cao] Gỡ lỗi kẹp Yes/No & Guardrail từ chối sai**: Tách rõ Query Intent Parser: chỉ dùng tiền tố khẳng định khi câu hỏi thực sự là Yes/No và nội dung xác nhận khớp; nới whitelist thực thể Hỏa Lò cho Guardrail. *(Mục tiêu: Giảm False Refusal từ 3.0% xuống <0.5%; 0% lỗi tiền tố.)*
- **[P2 - Trung bình] Hạ ngưỡng phụ thuộc Groq trần hoặc thêm Reranker + Context RAG**: Chỉ gọi LLM kèm top-k đoạn tài liệu tham chiếu chuẩn Hỏa Lò (Grounded Generation) và cấm trả lời ngoài ngữ cảnh truy xuất được. *(Mục tiêu: Tăng độ tin cậy câu trả lời động LLM từ 15% lên >85%.)*

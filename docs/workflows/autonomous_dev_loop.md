# Chu Trình Phát Triển Tự Động & Cải Tiến Liên Tục (Autonomous Development & Continuous Improvement Loop)

Tài liệu này đặc tả quy trình vận hành đóng kín giữa **Người dùng (Chỉ huy / Đặt yêu cầu)** và **AI Agent (Kỹ sư phần mềm tự trị)** cho dự án **BSCU**.

---

## 1. Sơ Đồ Chu Trình Vòng Lặp Đóng Kín (Closed-Loop Lifecycle)

```
        ┌──────────────────────────────────────────────────────────┐
        │  BƯỚC 1: TIẾP NHẬN YÊU CẦU TỪ NGƯỜI DÙNG                │
        │  (User prompt / Feature request / Bug report)            │
        └─────────────────────────────┬────────────────────────────┘
                                      │
                                      v
        ┌──────────────────────────────────────────────────────────┐
        │  BƯỚC 2: PHÂN TÍCH YÊU CẦU & TRA CỨU ĐỒ THỊ MÃ NGUỒN    │
        │  - Đọc docs/README.md & docs/concept/brainstorming.md    │
        │  - Dùng CodeGraph MCP kiểm tra phạm vi ảnh hưởng         │
        │  - Xác định tiêu chí nghiệm thu (Acceptance Criteria)    │
        └─────────────────────────────┬────────────────────────────┘
                                      │
                                      v
        ┌──────────────────────────────────────────────────────────┐
        │  BƯỚC 3: LẬP TRÌNH CHUYÊN NGHIỆP THEO QUY CHUẨN          │
        │  - File duy trì 300-500 dòng, nguyên tắc đơn nhiệm      │
        │  - Tách pure logic src/bscu/core/ (không import bpy)     │
        └─────────────────────────────┬────────────────────────────┘
                                      │
                                      v
 ┌─────────────────────────────────────────────────────────────────────────┐
 │ BƯỚC 4: VÒNG LẶP KIỂM THỬ - TỰ SỬA LỖI ĐẾN KHI ĐẠT (Self-Correction)   │
 │                                                                         │
 │   ┌───────────────────────────┐         ┌───────────────────────────┐   │
 │   │ Chạy: verify_all.py       │         │ Chạy lại verify_all.py    │   │
 │   │ (Rules -> Unit -> Blender)│         │ đến khi 100% PASS         │   │
 │   └─────────────┬─────────────┘         └─────────────▲─────────────┘   │
 │                 │                                     │                 │
 │            Có lỗi? (Exit != 0) ───> Đọc Stack Trace ──┘                 │
 │                 │                                                       │
 │            PASS 100% (Exit == 0)                                        │
 │                 │                                                       │
 │                 v                                                       │
 │   ┌─────────────────────────────────────────────────────────────┐       │
 │   │ Đo đạc thực tế qua MCP Socket (Cổng 9876):                 │       │
 │   │ - Gọi bpy.ops.bscu.reload() nạp code mới trong 0.05s       │       │
 │   │ - Kiểm định Bounding Box, Surface Area, Volume, Watertight  │       │
 │   └─────────────────────────────────────────────────────────────┘       │
 └────────────────────────────────────┬────────────────────────────────────┘
                                      │
                                      v
        ┌──────────────────────────────────────────────────────────┐
        │  BƯỚC 5: ĐÚC RÚT KINH NGHIỆM & CẢI TIẾN QUY TRÌNH        │
        │  - Cập nhật trực tiếp bài học vào tài liệu quy trình gốc │
        │  - TUYỆT ĐỐI KHÔNG TẠO FILE LESSON RIÊNG LẺ              │
        └─────────────────────────────┬────────────────────────────┘
                                      │
                                      v
        ┌──────────────────────────────────────────────────────────┐
        │  BƯỚC 6: BÀN GIAO KẾT QUẢ & CHỜ NGƯỜI DÙNG DUYỆT        │
        │  - Báo cáo số liệu đo đạc, zoom căn giữa 3D Viewport     │
        │  - Git commit mốc hoàn thiện                             │
        │  - Chờ Người dùng yêu cầu tiếp theo -> Quay lại Bước 1   │
        └──────────────────────────────────────────────────────────┘
```

---

## 2. Chi Tiết 6 Bước Thực Thi Chu Trình

### Bước 1: Tiếp Nhận Yêu Cầu (Requirements Intake)
- Người dùng đưa ra bài toán, tính năng mới hoặc yêu cầu chỉnh sửa thông số/giao diện.
- AI Agent tiếp nhận và không viết code vội vã.

### Bước 2: Phân Tích & Xác Lập Thước Đo Chân Lý (Analysis & Oracle)
- **Đọc ngữ cảnh:** Tra cứu `docs/README.md` và `docs/concept/brainstorming.md`.
- **Tra cứu đồ thị mã nguồn:** Dùng tool `codegraph_explore` hoặc lệnh `codegraph query <symbol>` để xác định các file, hàm, lớp bị ảnh hưởng (Blast Radius).
- **Thiết lập tiêu chuẩn nghiệm thu định lượng (Acceptance Criteria):**
  - Kích thước mong muốn (Dài, Rộng, Cao) kèm dung sai $\le 0.001\text{ mm}$.
  - Tính khép kín: $IsManifold == True$ và $NonManifoldEdges == 0$.
  - Socket của Node Group: Tên, loại socket và kiểu dữ liệu kết nối.

### Bước 3: Lập Trình Chuyên Nghiệp (Professional Coding)
- Mọi file `.py` tạo mới hoặc chỉnh sửa bắt buộc tuân thủ `docs/standards/coding_rules.md`:
  1. Giới hạn tiêu chuẩn: 300 - 500 dòng/file (tối đa không quá 500 dòng).
  2. Mỗi Operator/Node Group/Panel/Property nằm trên 1 file riêng biệt.
  3. Logic toán học thuần túy đưa vào `src/bscu/core/` (tuyệt đối không import `bpy`).
  4. Viết file test tương ứng trong `tests/unit/` hoặc `tests/integration/`.

### Bước 4: Vòng Lặp Tự Kiểm Thử - Tự Sửa Lỗi (Autonomous Self-Correction Loop)
AI Agent tự động thực hiện chu trình kiểm tra đóng kín mà không làm phiền người dùng:
1. **Kích hoạt Quality Gate tự động:**
   ```bash
   python scripts/verify_all.py
   ```
2. **Cơ chế Tự Sửa Lỗi (Self-Healing):**
   - Nếu Gate 1 (Line limit & Ruff) phát hiện lỗi: Đọc dòng vi phạm $\to$ Format/Refactor ngay.
   - Nếu Gate 2 (Unit tests) thất bại: Đọc assertion error $\to$ Chỉnh sửa logic toán học trong `core/`.
   - Nếu Gate 3 (Blender Headless tests) thất bại: Đọc stack trace Blender $\to$ Sửa socket/API call.
   - Chạy lại `python scripts/verify_all.py` cho đến khi toàn bộ 4 Gates đều **PASS 100% (Exit Code 0)**.
3. **Kiểm định Thực Tế trên Blender GUI (Live MCP Verification):**
   - Gửi lệnh Hot-Reload qua MCP: `bpy.ops.bscu.reload()` để nạp mã nguồn mới vào RAM Blender trong 0.05 giây.
   - Gọi các tool đo đạc: `validate_dimensions`, `measure_surface_area`, `measure_volume`.
   - Gọi lệnh tự động căn góc nhìn: `bpy.ops.view3d.view_selected()` để hiển thị vật thể rõ ràng trước mắt người dùng.

### Bước 5: Đúc Rút Kinh Nghiệm & Cập Nhật Quy Trình (Continuous Improvement)
- Trong quá trình sửa lỗi hoặc chạy thử, nếu phát hiện ra:
  - Một lỗi môi trường (Windows path, subprocess, socket timeout).
  - Một sự cố Blender API (socket type mismatch, depsgraph update).
  - Một kỹ thuật đo đạc/debug tối ưu hơn.
- **BẮT BUỘC:** Cập nhật trực tiếp nội dung bổ sung vào tài liệu quy trình gốc (`docs/debugging/blender_debug_workflow.md` hoặc `docs/standards/coding_rules.md`).
- **NGUYÊN TẮC BẤT DI BẤT DỊCH:** **Tuyệt đối không tạo file bài học (lesson) riêng lẻ** để bảo đảm tính duy nhất của thông tin (Single Source of Truth).

### Bước 6: Bàn Giao & Lưu Trữ (Deliver & Commit)
- Trình bày kết quả rõ ràng, súc tích cho người dùng:
  - Danh sách file đã tác động.
  - Số liệu đo đạc thực tế (kích thước, diện tích, thể tích, tính manifold).
  - Trạng thái các Quality Gates.
- Lưu mốc công việc vào Git:
  ```bash
  git add . && git commit -m "feat/fix: <nội dung hoàn thiện>"
  ```
- Chờ người dùng nghiệm thu và nhận yêu cầu tiếp theo để quay trở lại Bước 1.

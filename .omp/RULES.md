# BSCU PROJECT MASTER RULES (Oh My Pi Native Rulebook)

Dự án: **Hệ thống Điêu khắc CNC 2.5D Tham số hóa trên Blender (BSCU)**  
Nền tảng thực thi: **Oh My Pi (omp)**  
Loại rule: **Native Sticky Rule (`RULES.md`) — Tự động áp dụng (alwaysApply: true) trên toàn bộ phiên làm việc**

---

## 1. QUY TẮC TÀI LIỆU (DOCUMENTATION FIRST)
1. **Khởi đầu phiên làm việc:** Bất kỳ khi nào bắt đầu hoặc cần tra cứu kiến trúc, ngữ cảnh dự án, Agent **BẮT BUỘC ĐỌC `docs/README.md` ĐẦU TIÊN**.
2. **Nguyên tắc Đơn nguồn Sự thật (Single Source of Truth):**
   - Một thông tin/kiến thức **CHỈ TỒN TẠI TẠI 1 NƠI DUY NHẤT**, tuyệt đối không sao chép trùng lặp.
   - Khi có thông tin mới: Kiểm tra folder domain tương ứng trong `docs/` để cập nhật file cũ; chỉ tạo file mới khi chủ đề hoàn toàn chưa có.
   - Bất kỳ file `.md` mới nào trong `docs/` đều phải được index vào bảng **Document Index** trong `docs/README.md`.
3. **Cải tiến Quy trình Liên tục & Không Trùng lặp (Continuous Process Improvement):**
   - Khi phát hiện lỗi, khó khăn hoặc giải pháp kỹ thuật mới trong quá trình thực thi, **BẮT BUỘC cập nhật và cải tiến trực tiếp vào tài liệu quy trình tương ứng** (workflow docs) để đảm bảo các lần thực hiện sau luôn diễn ra trơn tru.
   - **TUYỆT ĐỐI KHÔNG TẠO FILE BÀI HỌC/LESSON RIÊNG LẺ** gây phân mảnh và trùng lặp nội dung. Toàn bộ kinh nghiệm đúc kết phải được hợp nhất thành các bước hành động cụ thể trong chính quy trình làm việc.

---

## 2. TRIẾT LÝ KIẾN TRÚC & HÌNH HỌC (INVARIANTS)
1. **Quy tắc Bất khả xâm phạm của Vector 2D (Immutable Vectors):**
   - Bản vẽ Vector 2D phẳng là bất biến. Tuyệt đối không dùng Modifier làm biến dạng đường Curve 2D gốc.
2. **Kiến trúc 3 Tầng Dữ liệu (Three-Tier Pipeline):**
   - **Tầng 1 (2D Canvas):** Nhận Curve 2D + Siêu dữ liệu (`Custom Properties`).
   - **Tầng 2 (Procedural Geometry Engine):** Geometry Nodes đo khoảng cách SDF (`Geometry Proximity`) $\to$ Bevel slope $\to$ Height clamp $\to$ Profile Float Curve $\to$ Xuất độ cao ảo `$Z_Height_Virtual`.
   - **Tầng 3 (3D Projection & Displacement):** Chiếu qua UV bằng `Sample UV Surface` và đẩy đỉnh theo Normal (`Set Position`), xuất file STL Watertight kín chuẩn gia công CNC.

---

## 3. QUY CHUẨN LẬP TRÌNH BẮT BUỘC (MANDATORY CODING RULES)

### 3.1. Giới hạn Kích thước File (File Length Limit)
- **Quy tắc chuẩn:** Mỗi file `.py` được duy trì trong khoảng **300 - 500 DÒNG** (phù hợp với Context Window lớn của AI Agent).
- File vượt quá mốc **500 dòng** bắt buộc phải chủ động phân rã thành các sub-module hoặc helper riêng biệt.
- Tuyệt đối cấm viết code dồn cục (Monolithic file).

### 3.2. Cấu trúc Module Chuẩn hóa (`src/bscu/`)
Mọi mã nguồn phải tuân thủ phân lớp nghiêm ngặt:
- **`src/bscu/core/` (Pure Logic):**
  - Chứa toàn bộ công thức toán học hình thái SDF, góc vát, lượng giác, xử lý vector/ma trận, Enum và Dataclass.
  - **ĐIỀU CẤM KỴ:** Module `core/` **TUYỆT ĐỐI KHÔNG IMPORT `bpy`**.
- **`src/bscu/properties/` (Metadata):**
  - Quản lý Custom Properties (`curve_properties.py` cho Curve, `mesh_properties.py` cho Phôi 3D).
- **`src/bscu/nodes/` (Geometry Nodes Builders):**
  - 1 file chịu trách nhiệm xây dựng đúng 1 cụm Node Group (ví dụ: `sdf_proximity.py`, `height_clamp.py`, `profile_shaper.py`).
- **`src/bscu/projection/` (UV & 3D Displacement):**
  - Xử lý chiếu UV và đẩy đỉnh phôi (`uv_relax.py`, `surface_displace.py`).
- **`src/bscu/operators/` (User Actions):**
  - Mỗi Operator nằm trên 1 file riêng biệt (`op_init_canvas.py`, `op_relax_uv.py`, `op_export_stl.py`).
- **`src/bscu/ui/` (Interface):**
  - Mỗi Panel N-Toolbar nằm trên 1 file riêng (`panel_parameters.py`, `panel_actions.py`).
- **`src/bscu/__init__.py`:**
  - File entry point đăng ký Add-on, chỉ làm nhiệm vụ điều phối import và lặp qua danh mục đăng ký (< 50 dòng).

### 3.3. Cơ chế Đăng ký Module Phân tán (Clean Registration)
- Không gom danh sách hàng chục class vào `__init__.py`.
- Mỗi module con tự công bố danh sách `CLASSES = (...)` hoặc hai hàm `register()` và `unregister()` nội bộ.

### 3.4. Kiểm thử Tự động Bắt buộc (Automated Verification)
- Không bao giờ bàn giao code khi chưa có kết quả chạy kiểm thử thực tế (Smoke run):
  1. **Unit Test (`tests/unit/`):** Test toán thuần Python chạy bằng `python -m unittest` hoặc `pytest` trong < 1 giây.
  2. **Headless Integration Test (`tests/integration/`):** Khởi chạy kiểm tra trực tiếp với engine Blender không giao diện:
     ```bash
     ./blender/blender.exe -b --python tests/run_tests.py
     ```

### 3.5. Đồng bộ & Tra cứu Đồ thị CodeGraph
- **Trước khi sửa code:** Sử dụng `codegraph_explore` hoặc lệnh `codegraph query <symbol>` để kiểm tra phạm vi ảnh hưởng (Blast Radius).
- **Sau khi sửa/thêm code:** Bắt buộc chạy `codegraph sync` để cập nhật đồ thị tri thức mã nguồn.

---

## 4. CHU TRÌNH PHÁT TRIỂN TỰ ĐỘNG & TỰ SỬA LỖI (AUTONOMOUS DEV & SELF-HEALING LOOP)
Mọi tác vụ nhận từ người dùng phải vận hành theo đúng 6 bước trong **`docs/workflows/autonomous_dev_loop.md`**:
1. **Nhận yêu cầu:** Xác lập phạm vi và không code vội vã.
2. **Phân tích & Thước đo:** Dùng CodeGraph MCP kiểm tra blast radius; thiết lập tiêu chuẩn nghiệm thu định lượng.
3. **Lập trình chuẩn mực:** File $\le 200$ dòng, tách biệt pure logic `src/bscu/core/` (không import `bpy`).
4. **Vòng lặp tự kiểm thử & tự sửa lỗi:**
   - Chạy `python scripts/verify_all.py`. Nếu gặp lỗi, tự đọc stack trace và tự sửa file cho tới khi **PASS 100% (Exit 0)**.
   - Kiểm định thực tế qua MCP Socket (port 9876): Hot-reload `bpy.ops.bscu.reload()`, đo đạc kích thước và kiểm tra manifold.
5. **Cải tiến quy trình:** Cập nhật ngay kinh nghiệm mới vào tài liệu quy trình tương ứng (không tạo file lesson riêng lẻ).
6. **Bàn giao & Commit:** Báo cáo số liệu đo đạc, căn góc nhìn 3D Viewport cho người dùng, lưu Git commit và sẵn sàng cho vòng lặp tiếp theo.

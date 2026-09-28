# Quy Chuẩn Lập Trình & Thiết Kế Module (Coding Rules & Architecture Standards)

Tài liệu này định nghĩa các quy tắc bắt buộc áp dụng khi viết mã nguồn trong dự án **BSCU**. Mọi lập trình viên và **AI Agent** khi tạo mới hoặc sửa đổi code đều phải tuân thủ nghiêm ngặt các quy tắc này.

---

## 1. Giới hạn Kích thước File (File Length Limit)
- **Quy tắc chuẩn:** Mỗi file mã nguồn `.py` được duy trì trong khoảng **300 - 500 DÒNG**.
- **Mục tiêu:**
  - Tận dụng tối đa Context Window lớn của AI Agent hiện đại, giúp Agent nắm trọn vẹn ngữ cảnh của cả một module logic mà không bị phân mảnh quá mức.
  - Vẫn giữ code trong phạm vi tập trung cao độ, hạn chế lỗi diff conflict khi sửa code.
- **Xử lý khi vượt ngưỡng:** Nếu file dài quá **500 dòng**, bắt buộc phải phân rã thành các sub-module hoặc hàm helper riêng biệt.

---

## 2. Nguyên tắc Đơn nhiệm (Single Responsibility Principle)
Mỗi file chỉ chịu trách nhiệm cho đúng một vai trò duy nhất:
- **Operators:** Mỗi file chứa duy nhất 1 Operator (ví dụ: `op_init_canvas.py`, `op_relax_uv.py`).
- **Geometry Nodes:** Mỗi file phụ trách dựng 1 cụm Node Group chuyên biệt (ví dụ: `sdf_proximity.py`, `height_clamp.py`, `profile_shaper.py`).
- **UI Panels:** Mỗi file phụ trách 1 panel độc lập (ví dụ: `panel_parameters.py`, `panel_actions.py`).
- **Properties:** Tách biệt thuộc tính Curve (`curve_properties.py`) và thuộc tính Phôi Mesh (`mesh_properties.py`).

---

## 3. Tách biệt Logic Thuần (Pure Logic) khỏi Blender API (`bpy`)
- Toàn bộ công thức toán học (SDF, bevel slope, lượng giác, vector math, ma trận biến đổi) và định nghĩa cấu trúc dữ liệu thuần phải nằm trong thư mục `src/bscu/core/`.
- Module `src/bscu/core/` **tuyệt đối không import `bpy`**.
- **Lợi ích:** Có thể chạy Unit Test siêu tốc bằng Python độc lập (`pytest`) mà không cần tốn thời gian khởi động Blender.

---

## 4. Cấu trúc Module Chuẩn hóa (`src/bscu/`)
Toàn bộ mã nguồn add-on phải được tổ chức theo cấu trúc sau:

```text
src/bscu/
├── __init__.py                 # Dispatcher đăng ký / hủy đăng ký add-on (< 50 dòng)
├── blender_manifest.toml       # Metadata Extension chuẩn Blender 4.2+ / 5.x
├── core/                       # [Pure Logic] Toán học, Enums, Constants, Data Classes
├── properties/                 # [Metadata] Custom Properties gán vào Curve & Mesh
├── nodes/                      # [Procedural Engine] Code-gen các cụm Geometry Nodes
├── projection/                 # [3D Projection] Điều khiển UV Unwrap, Relax & Displace
├── operators/                  # [Actions] Các bpy Operator xử lý tác vụ người dùng
└── ui/                         # [Interface] N-Panel Toolbar hiển thị giao diện
```

---

## 5. Cơ chế Đăng ký Module Tự động (Modular Registration)
- Không viết danh sách đăng ký class dài dòng trong `__init__.py`.
- Mỗi module con (`operators/`, `properties/`, `ui/`) phải cung cấp danh sách `CLASSES = (...)` hoặc hai hàm `register()` và `unregister()` nội bộ.
- File `src/bscu/__init__.py` chỉ làm nhiệm vụ import các module con và gọi vòng lặp đăng ký.

---

## 6. Kiểm thử Tự động Bắt buộc (Automated Testing)
Mọi chức năng mới hoặc thay đổi logic đều phải được nghiệm thu bằng test:
1. **Unit Test (`tests/unit/`):** Kiểm thử logic toán học thuần Python, chạy trong < 1 giây.
2. **Headless Integration Test (`tests/integration/`):** Chạy kiểm thử tự động với Blender chế độ nền:
   ```bash
   ./blender/blender.exe -b --python tests/run_tests.py
   ```
   Kiểm tra socket của Geometry Nodes, Custom Properties và pipeline chạy thông suốt mà không crash.

---

## 7. Đồng bộ Đồ thị Mã nguồn (CodeGraph Sync)
- Sau khi hoàn thành một lượt code hoặc tạo mới module, Agent/Developer nên chạy `codegraph sync` để cập nhật knowledge graph, bảo đảm đồ thị quan hệ luôn khớp với mã nguồn thực tế.

---

## 8. Cải Tiến Quy Trình & Tính Duy Nhất của Thông Tin (Continuous Process Improvement)
- Bất kỳ khi nào gặp lỗi, khó khăn hoặc tìm ra giải pháp kỹ thuật tối ưu hơn, Agent/Developer **bắt buộc cập nhật trực tiếp vào văn bản quy trình tương ứng** (ví dụ: `docs/debugging/blender_debug_workflow.md`).
- **Tuyệt đối không tạo file bài học (lesson) riêng lẻ** gây phân mảnh và trùng lặp dữ liệu. Mọi kinh nghiệm đúc rút phải trở thành bước hành động cụ thể trong chính quy trình làm việc chuẩn.

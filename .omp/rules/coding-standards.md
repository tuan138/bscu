---
description: "Quy chuẩn lập trình bắt buộc cho Blender Add-on và Python: file <= 200 dòng, đơn nhiệm, tách Pure Logic khỏi bpy, test tự động"
globs: ["src/**/*.py", "tests/**/*.py"]
alwaysApply: true
---

# Quy Chuẩn Lập Trình Dự Án BSCU (Coding Standards)

Mọi thao tác code trên các file nguồn (`src/**/*.py`) và file test (`tests/**/*.py`) phải tuân thủ nghiêm ngặt các quy định sau:

1. **Giới hạn 150 - 200 dòng/file:**
   - Tuyệt đối không viết file dài vượt quá 200 dòng.
   - Nếu logic dài, tách ngay thành các sub-module hoặc helper files.

2. **Nguyên tắc Đơn nhiệm (Single Responsibility):**
   - Mỗi Operator 1 file: `src/bscu/operators/op_<action>.py`.
   - Mỗi cụm Node Group 1 file: `src/bscu/nodes/<node_group_name>.py`.
   - Mỗi UI Panel 1 file: `src/bscu/ui/panel_<name>.py`.
   - Thuộc tính Custom Properties tách biệt giữa Curve và Mesh: `src/bscu/properties/`.

3. **Tách biệt Logic Thuần (Pure Logic) khỏi `bpy`:**
   - Toàn bộ toán học hình thái SDF, góc vát, lượng giác, xử lý ma trận nằm trong `src/bscu/core/`.
   - Thư mục `src/bscu/core/` tuyệt đối KHÔNG import `bpy`.

4. **Kiểm thử Bắt buộc trước khi nghiệm thu:**
   - Logic toán kiểm thử bằng Unit Test thuần Python (`tests/unit/`).
   - Cụm Node và Operator kiểm thử qua Blender Headless (`tests/integration/`):
     `./blender/blender.exe -b --python tests/run_tests.py`.

5. **Đăng ký Module phân tán (Modular Registration):**
   - Các module con cung cấp danh mục `CLASSES = (...)` hoặc `register()` / `unregister()`.
   - File `src/bscu/__init__.py` chỉ làm nhiệm vụ import và gọi vòng lặp đăng ký.

6. **Đồng bộ CodeGraph:**
   - Chạy `codegraph sync` sau khi tạo mới hoặc sửa đổi các module code.

Chi tiết xem tại: `docs/standards/coding_rules.md`.

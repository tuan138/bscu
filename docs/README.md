# Hệ thống Tài liệu Dự án (Documentation Hub)

Thư mục `docs/` là nơi lưu trữ toàn bộ thông tin kiến trúc, kỹ thuật, mô hình dữ liệu và các bài học kinh nghiệm (lessons learned) được đúc kết trong quá trình nghiên cứu & triển khai dự án **Parametric 2.5D CNC Sculpting Workflow in Blender (BSCU)**.

---

## 1. Nguyên tắc Quản lý & Tổ chức Tài liệu

1. **Đọc `docs/README.md` đầu tiên:** Mọi Agent/Developer khi tra cứu thông tin trong `docs/` đều phải đọc file này trước để nắm danh mục và cấu trúc tài liệu.
2. **Tổ chức theo từng mảng (Domain Folders):** Mỗi mảng kiến thức/kỹ thuật được gom thành 1 thư mục riêng (ví dụ: `concept/`, `standards/`, `debugging/`, `workflows/`, `tooling/`).
3. **Quy ước đặt tên file `.md`:** Tên file ngắn gọn, phản ánh rõ ràng nội dung bên trong (dùng `snake_case` hoặc `kebab-case`).
4. **Nguyên tắc Duy nhất (Single Source of Truth):**
   - Một nội dung/kiến thức **CHỈ TỒN TẠI TẠI 1 NƠI DUY NHẤT**, tuyệt đối không sao chép trùng lặp qua nhiều file.
   - **Quy trình thêm/sửa tài liệu:** Trước khi tạo file `.md` mới, bắt buộc phải kiểm tra xem chủ đề đó đã có trong các folder chưa:
     - *Nếu đã có:* Cập nhật/bổ sung vào file hiện có.
     - *Nếu chưa có:* Phân loại vào folder phù hợp (hoặc tạo folder mới theo mảng), tạo file `.md` mới và **bắt buộc cập nhật mục lục Index bên dưới**.
5. **Cải tiến Quy trình Liên tục & Không Trùng lặp (Continuous Process Improvement):**
   - Khi phát hiện lỗi, khó khăn hoặc giải pháp kỹ thuật mới trong quá trình thực thi, **BẮT BUỘC cập nhật và cải tiến trực tiếp vào tài liệu quy trình tương ứng** (workflow document) để đảm bảo các lần thực hiện sau luôn diễn ra trơn tru.
   - **Tuyệt đối không tạo file bài học/lesson riêng lẻ** gây phân mảnh và trùng lặp nội dung. Toàn bộ kinh nghiệm đúc kết phải được hợp nhất thành các bước hành động cụ thể trong chính quy trình làm việc.

---

## 2. Mục lục Tài liệu (Document Index)

| Tên file | Nơi lưu trữ | Tóm tắt nội dung |
| :--- | :--- | :--- |
| `brainstorming.md` | `docs/concept/brainstorming.md` | TDD v1.1.0 đặc tả kiến trúc Studio 2D CAD (3-Pane Hybrid), thuật toán Lưới lấy mẫu SDF đồng nhất, điều khiển Profile dốc 2 cấp và lộ trình triển khai. |
| `agent_setup.md` | `docs/tooling/agent_setup.md` | Hướng dẫn cấu hình CodeGraph MCP Server và bộ kỹ năng Superpowers cho AI coding agent. |
| `coding_rules.md` | `docs/standards/coding_rules.md` | Quy chuẩn lập trình bắt buộc: file 300-500 dòng, đơn nhiệm, tách Pure Logic khỏi bpy, test tự động. |
| `blender_debug_workflow.md` | `docs/debugging/blender_debug_workflow.md` | Quy trình debug 4 cấp độ: Unit test pure logic, Headless Blender, MCP Live Control (mcp-blender) và DAP Remote Debug. |
| `autonomous_dev_loop.md` | `docs/workflows/autonomous_dev_loop.md` | Chu trình phát triển tự động 6 bước: Nhận yêu cầu -> Phân tích -> Tự code -> Tự test/sửa -> Bàn giao -> Cải tiến quy trình. |

*(Bảng này sẽ được cập nhật liên tục mỗi khi có tài liệu mới được tạo ra).*

---

## 3. Tổng quan Dự án (Project Summary)

- **Mục tiêu:** Phát triển quy trình/Add-on trên Blender hỗ trợ điêu khắc phù điêu CNC 2.5D tham số hóa (Parametric), phi phá hủy (Non-destructive) bằng Signed Distance Field (SDF) và chiếu UV bảo toàn tỷ lệ không biến dạng.
- **Tech Stack:** Blender 4.x/5.x, Python 3.11+/3.13 (`bpy`), Blender Geometry Nodes (SDF, Geometry Proximity, Float Curves, Sample UV Surface), Conformal & ARAP UV Minimizing Stretch, Watertight STL Mesh Export.
- **Kiến trúc 3 tầng:**
  1. **Tầng 1 (2D Canvas):** Vector 2D bất biến (Immutable Curve) mang siêu dữ liệu (Custom Properties).
  2. **Tầng 2 (Procedural Geometry Engine):** Geometry Nodes tính toán trường khoảng cách SDF và xuất độ cao ảo `$Z_Height_Virtual`.
  3. **Tầng 3 (3D Projection):** Chiếu độ cao lên phôi 3D qua UV và đẩy lưới theo Normal (`Set Position`), xuất file STL phục vụ gia công CNC.

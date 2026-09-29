# AGENTS.md

## 1. Project Overview
- **Project Name:** Parametric 2.5D CNC Sculpting Workflow in Blender (BSCU)
- **Goal:** Non-destructive, parametric, vector-based 2.5D relief and CNC sculpting add-on/pipeline for Blender using Procedural SDF (Signed Distance Fields) and distortion-free UV surface projection.

---

## 2. Tech Stack
- **DCC Platform:** Blender 4.x / 5.x (`bpy` API)
- **Backend / Scripting:** Python 3.11+ / 3.13 (UI Panels, Operators, Custom Properties, Drivers)
- **Procedural Geometry Engine:** Blender Geometry Nodes (SDF generation, `Geometry Proximity`, `Sample UV Surface`, `Set Position` along Normals, Float Curves)
- **Surface & UV Geometry:** Conformal Unwrapping, ARAP Mesh Relaxation (`bpy.ops.uv.minimize_stretch`)
- **Input / Output:** Vector Curves (Bezier), SVG, Watertight STL mesh output

---

## 3. Documentation & Context Loading
> **BẮT BUỘC:** Khi bắt đầu hoặc cần tra cứu ngữ cảnh, kiến trúc, quy tắc quản lý docs và danh mục tài liệu, agent **PHẢI ĐỌC `docs/README.md` ĐẦU TIÊN**.
> Toàn bộ quy tắc tổ chức folder, quy ước đặt tên, nguyên tắc Single Source of Truth và Index tài liệu được quản lý tập trung tại `docs/README.md`.
> **Cải tiến quy trình & Tính duy nhất:** Mọi bài học/kinh nghiệm khi fix bug phải được cập nhật trực tiếp vào tài liệu quy trình tương ứng (workflow docs). Tuyệt đối không tạo file bài học (lesson) riêng lẻ gây trùng lặp thông tin.
---

## 4. Architecture Summary
1. **Tier 1 (2D Canvas):** 2D Immutable Bezier Curves with metadata (`Custom Properties`).
2. **Tier 2 (Geometry Engine):** Geometry Nodes-based SDF height calculation (`$Z_Height_Virtual`).
3. **Tier 3 (3D Projection):** Projection via UV space onto subdivided 3D base mesh (`Normal Displacement`) and Watertight STL export.

---

## 5. Development Conventions & Mandatory Rules
> **BẮT BUỘC:** Mọi thao tác lập trình của AI Agent phải tuân thủ nghiêm ngặt quy chuẩn tại **`docs/standards/coding_rules.md`**:
1. **Giới hạn kích thước file:** Mỗi file `.py` duy trì trong khoảng **300 - 500 DÒNG** (tận dụng context window lớn của AI). Vượt quá 500 dòng phải phân rã thành sub-module hoặc helper.
2. **Nguyên tắc Đơn nhiệm:** 1 Operator / 1 Node group / 1 UI Panel / 1 Property group trên 1 file riêng biệt.
3. **Tách biệt Pure Logic:** Toàn bộ công thức toán và kiểu dữ liệu thuần để trong `src/bscu/core/` (tuyệt đối không import `bpy`).
4. **Kiểm thử tự động (Smoke & Unit Tests):** Mọi thay đổi phải có test kiểm chứng (chạy Unit Test hoặc Headless `./blender/blender.exe -b --python tests/run_tests.py`).
5. **Đăng ký module sạch:** Không khai báo class thủ công hàng loạt trong `__init__.py`; sử dụng danh mục đăng ký theo từng module con.
6. **Đồng bộ CodeGraph:** Chạy `codegraph sync` sau khi cập nhật mã nguồn để giữ vững đồ thị quan hệ codebase.

---

## 6. Superpowers Skills (BẮT BUỘC)
> **BẮT BUỘC:** Agent **PHẢI sử dụng superpower skill** (`skill://<name>`) trong toàn bộ quá trình phát triển.
1. **Đọc skill trước khi hành động:** Khi task khớp với một skill, agent **MUST** đọc `skill://<tên-skill>` trước khi thực hiện bất kỳ thao tác code nào.
2. **Các skill tối thiểu áp dụng theo giai đoạn:**
   - `using-superpowers` — mở đầu mọi phiên làm việc, trước mọi phản hồi khác.
   - `brainstorming` — trước khi bắt đầu công việc sáng tạo (tính năng, component, chức năng mới).
   - `writing-plans` — khi có đặc tả/spec cho tác vụ nhiều bước, trước khi chạm vào code.
   - `test-driven-development` — trước khi viết implementation, không phải sau.
   - `systematic-debugging` — khi gặp bug, test fail hoặc hành vi lạ, trước khi đề xuất fix.
   - `verification-before-completion` — trước khi tuyên bố hoàn thành, commit hoặc tạo PR.
   - `requesting-code-review` / `receiving-code-review` — khi hoàn tất task lớn hoặc khi nhận review.
   - `using-git-worktrees` — khi cần workspace cách ly cho feature work.
   - `dispatching-parallel-agents` / `subagent-driven-development` — khi có 2+ task độc lập.
3. **Các skill khác** (`writing-skills`, `finishing-a-development-branch`, `diagnosing-superpowers`) áp dụng theo ngữ cảnh tương ứng.
4. **Ưu tiên:** Skill đọc được **luôn thắng** hướng dẫn mặc định khi có xung đột.

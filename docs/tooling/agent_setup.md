# Thiết lập Công cụ Trợ lý & MCP (Agent Tooling & MCP Setup)

Tài liệu này ghi nhận cấu hình và cách hoạt động của các công cụ hỗ trợ AI Agent được tích hợp trong dự án **BSCU**.

---

## 1. CodeGraph MCP Server
- **Package:** `@colbymchenry/codegraph` (v1.6.0)
- **Mục đích:** Xây dựng bản đồ tri thức (Knowledge / Symbol Graph) cho toàn bộ codebase bằng Tree-sitter và SQLite cục bộ (WAL mode), giúp Agent truy vấn cấu trúc hàm, lớp, biến, tham chiếu mà không cần duyệt file thủ công.
- **Cấu hình MCP:**
  - File cấu hình dự án: `.mcp.json`
  - Lệnh khởi chạy MCP: `codegraph serve --mcp`
  - Đã liên kết hỗ trợ: Claude Code (`.claude/settings.json`), Cursor (`.cursor/mcp.json`), Antigravity IDE (`~/.gemini/antigravity/mcp_config.json`).
- **Cấu hình Loại trừ (Exclude Filter):**
  - File: `codegraph.json` và `.gitignore`.
  - Loại trừ toàn bộ bản dựng Blender di động (`blender/**`, `blender.shared/**`, `blender.crt/**`) và các file ẩn/cấu hình agent (`.*/**`).
  - Database tinh gọn: Chỉ lưu trữ source code thực của dự án (dung lượng chỉ ~1.2 MB thay vì >330 MB do quét nhầm Blender bundle).
- **Các lệnh CLI thường dùng:**
  - `codegraph status`: Kiểm tra số lượng file, node, edge và trạng thái database.
  - `codegraph sync`: Cập nhật index khi có thay đổi code.
  - `codegraph query <symbol>`: Tìm kiếm symbol trong đồ thị code.

---

## 2. Superpowers Skills Suite
- **Nguồn:** `obra/superpowers` (cài đặt qua `npx skills`)
- **Vị trí lưu trữ:** `.agents/skills/`, `.claude/skills/`
- **Mục đích:** Cung cấp bộ 15 kỹ năng chuẩn hóa quy trình kỹ nghệ phần mềm cho AI coding agent:
  1. `brainstorming`: Khám phá yêu cầu, thiết kế và chốt giải pháp trước khi code.
  2. `writing-plans`: Lập kế hoạch triển khai chi tiết từng bước.
  3. `executing-plans`: Thực thi kế hoạch theo từng đầu việc cụ thể.
  4. `test-driven-development` (TDD): Chu trình Red-Green-Refactor bắt buộc có kiểm thử.
  5. `systematic-debugging`: Điều tra nguyên nhân gốc rễ trước khi sửa lỗi.
  6. `subagent-driven-development` & `dispatching-parallel-agents`: Phân rã và điều phối subagent độc lập.
  7. `requesting-code-review` & `receiving-code-review`: Quy trình kiểm tra chất lượng code 2 lớp.
  8. `verification-before-completion`: Nghiệm thu thực tế trước khi bàn giao.
  9. `using-git-worktrees` & `finishing-a-development-branch`: Quản lý nhánh và dọn dẹp worktree.
  10. `using-superpowers`, `diagnosing-superpowers`, `writing-skills`: Điều phối và quản trị kỹ năng.

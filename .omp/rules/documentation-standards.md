---
description: "Quy chuẩn quản lý tài liệu docs/: Single Source of Truth, cập nhật index docs/README.md"
globs: ["docs/**/*.md", "*.md"]
alwaysApply: false
---

# Quy Chuẩn Quản Lý Tài Liệu (Documentation Standards)

Mọi thao tác liên quan đến tạo mới, cập nhật tài liệu `.md` trong dự án phải tuân thủ:

1. **Đọc `docs/README.md` đầu tiên:** Nắm danh mục toàn bộ tài liệu dự án trước khi tra cứu.
2. **Nguyên tắc Single Source of Truth:**
   - Một nội dung chỉ tồn tại ở 1 file duy nhất, không trùng lặp.
   - Trước khi tạo file mới, kiểm tra xem nội dung đã có chưa để cập nhật vào file cũ.
3. **Phân loại theo Domain Folder:**
   - Mỗi mảng kiến thức nằm trong 1 thư mục con: `docs/concept/`, `docs/standards/`, `docs/tooling/`, `docs/lessons_learned/`, v.v.
4. **Bắt buộc cập nhật Document Index:**
   - Bất kỳ khi nào tạo file `.md` mới trong `docs/`, phải thêm 1 dòng vào bảng Index trong `docs/README.md` (Tên file, Nơi lưu trữ, Tóm tắt 1 dòng).

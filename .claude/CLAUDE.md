<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->

## BSCU Project Rules
- **Bắt buộc đọc `docs/README.md` đầu tiên** khi cần tra cứu thông tin dự án.
- **Single Source of Truth:** Nội dung chỉ tồn tại 1 nơi, luôn cập nhật index trong `docs/README.md`.
- **Giới hạn file:** Mỗi file `.py` 300 - 500 dòng (theo `docs/standards/coding_rules.md`).
- **Single Responsibility:** 1 file = 1 Operator / 1 Node builder / 1 Panel / 1 Property group.
- **Tách Pure Logic:** `src/bscu/core/` thuần Python, không import `bpy`.
- **Kiểm thử tự động:** Unit test thuần Python hoặc `./blender/blender.exe -b --python tests/run_tests.py`.
- **Đồng bộ CodeGraph:** Chạy `codegraph sync` sau khi sửa đổi mã nguồn.

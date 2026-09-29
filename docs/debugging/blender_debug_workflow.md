# Quy Trình Debug & Kiểm Soát Trực Tiếp Blender (Blender Debugging & Live Inspection Workflow)

Tài liệu này đặc tả quy trình chẩn đoán lỗi, thu thập dữ liệu, điều khiển trực tiếp Blender và các nguyên tắc kỹ thuật cốt lõi được đúc kết trong quá trình triển khai dự án **BSCU**.

---

## 1. Bốn Cấp Độ Debug (Four-Tier Debugging Architecture)

```
┌──────────────────────────────────────────────────────────────────┐
│ CẤP ĐỘ 1: Pure Logic Unit Test (Toán hình thái SDF, Types)       │
│ - Chạy độc lập bằng Python thường, không cần Blender (< 0.1s)   │
└─────────────────────────────────┬────────────────────────────────┘
                                  │
                                  v
┌──────────────────────────────────────────────────────────────────┐
│ CẤP ĐỘ 2: Headless Automated Test (Blender API & Node Sockets)  │
│ - Chạy ngầm qua CLI: ./blender/blender.exe -b --python ...       │
│ - Bắt mã lỗi, stack trace, kiểm tra socket của Geometry Nodes    │
└─────────────────────────────────┬────────────────────────────────┘
                                  │
                                  v
┌──────────────────────────────────────────────────────────────────┐
│ CẤP ĐỘ 3: Live Control & Inspection qua MCP (mcp-blender)        │
│ - AI Agent trực tiếp gọi 218 Blender tools qua JSON-RPC stdio    │
│ - Truy vấn Scene, lấy thông số Object, inspect cụm Geometry Nodes│
└─────────────────────────────────┬────────────────────────────────┘
                                  │
                                  v
┌──────────────────────────────────────────────────────────────────┐
│ CẤP ĐỘ 4: Deep Runtime Debugging (DAP / debugpy / Verbose Logs)  │
│ - Gắn VS Code / DAP Debugger vào tiến trình qua port 5678        │
│ - Đặt Breakpoint, Step-over trong khi Operator đang chạy         │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Chi Tiết Thực Hiện Từng Cấp Độ

### Cấp độ 1: Kiểm thử Logic Thuần (Pure Logic Unit Test)
- **Áp dụng cho:** Các module trong `src/bscu/core/` (toán SDF, lượng giác góc vát bevel, công thức clamp chiều cao, chuyển đổi enum/metadata).
- **Lệnh thực thi:**
  ```bash
  python -m unittest discover tests/unit
  ```
- **Nguyên tắc:** Module `core/` **tuyệt đối không import `bpy`**, đảm bảo phản hồi tức thì (< 0.1s) mà không tiêu tốn RAM hay khởi động Blender.

### Cấp độ 2: Kiểm thử Tự động Chế độ Nền (Headless Blender Integration)
- **Áp dụng cho:** Kiểm tra việc tạo node group trong `src/bscu/nodes/`, liên kết socket, gán Custom Properties và áp dụng Modifier.
- **Lệnh thực thi:**
  ```bash
   ./blender/blender.exe -b --python tests/run_tests.py
  ```
- **Kỹ thuật trích xuất dữ liệu:**
  - Dùng `bpy.context.evaluated_depsgraph_get()` để lấy dữ liệu thực tế sau khi tính toán Modifier / Geometry Nodes.
  - Kiểm tra số lượng đỉnh (vertices), độ cao Z tối đa, kiểm tra tính khép kín của lưới (Watertight manifold).

### Cấp độ 3: Điều khiển Trực tiếp qua MCP (`RFingAdam/mcp-blender`)
Hệ thống tích hợp MCP Server cho phép AI Agent và Developer tương tác trực tiếp với phiên Blender đang mở:
1. **Khởi chạy socket server trong Blender:**
   - *Chế độ nền (Headless Background Service):*
     Sử dụng `scripts/run_blender_mcp_server.py`. Script này duy trì vòng lặp chủ động gọi `server._tick()` để xử lý socket I/O vì Blender headless không chạy Window Manager loop:
     ```bash
     ./blender/blender.exe -b --python scripts/run_blender_mcp_server.py
     ```
   - *Chế độ đồ họa (Live GUI):*
     Sử dụng `scripts/start_gui_mcp.py` để mở cửa sổ Blender trực tiếp trên màn hình, gọi `bpy.ops.mcp.start_server()` và để vòng lặp sự kiện tự nhiên của Blender điều phối `bpy.app.timers`:
     ```bash
     ./blender/blender.exe --python scripts/start_gui_mcp.py
     ```
2. **Cấu hình MCP Client chuẩn hóa trên Windows (`.mcp.json`):**
   Trên Windows, các lệnh CLI cài qua npm thực chất là file batch `.cmd`. Do đó luôn bọc qua `cmd.exe /c` để tránh lỗi `FileNotFoundError (WinError 2)`:
   ```json
   {
     "mcpServers": {
       "codegraph": {
         "type": "stdio",
         "command": "cmd.exe",
         "args": ["/c", "codegraph", "serve", "--mcp"]
       },
       "blender": {
         "type": "stdio",
         "command": "mcp-blender",
         "args": ["--host", "127.0.0.1", "--port", "9876"]
       }
     }
   }
   ```
3. **Các công cụ tra cứu & thu thập dữ liệu chính:**
   - `blender_scene_info`: Đọc thông tin Scene, số lượng đối tượng, frame rate, engine render.
   - `blender_object_list` & `blender_object_get`: Liệt kê và trích xuất thuộc tính hình học chi tiết của Object.
   - `validate_dimensions`: Kiểm tra bounding box theo 3 trục (X, Y, Z) so với kích thước mong muốn kèm tolerance.
   - `measure_surface_area` & `measure_volume`: Đo diện tích toàn phần, thể tích và kiểm tra tính khép kín `is_manifold`.
   - `geonode_inspect`: Kiểm tra chi tiết cấu trúc cụm Geometry Nodes và các socket kết nối.
   - `render_viewport`: Chụp ảnh khung nhìn 3D phục vụ kiểm tra trực quan hình thái bề mặt đắp nổi.

### Cấp độ 4: Debug Từng Bước với DAP (`debugpy`)
- Khi cần theo dõi biến nội bộ hoặc lỗi logic ngầm trong Operator:
  1. Thêm đoạn code kích hoạt debug vào script/addon:
     ```python
     import debugpy
     debugpy.listen(("127.0.0.1", 5678))
     print("Waiting for debugger to attach...")
     debugpy.wait_for_client()
     ```
  2. Bật cờ log chi tiết từ Blender CLI:
     ```bash
     ./blender/blender.exe --debug --debug-python
     ```

---

## 3. Quy Chuẩn Kỹ Thuật Đã Đúc Rút (Engineering Best Practices)

1. **Chuẩn hóa Hệ Đơn vị CNC (Millimeters vs Meters):**
   - Mặc định của Blender là hệ mét ($1\text{ unit} = 1.0\text{ m}$). Trong ngành gia công phù điêu CNC 2.5D, đơn vị thiết kế luôn là **Milimet (mm)**.
   - Luôn thiết lập hệ đơn vị ngay khi khởi tạo Canvas hoặc mở phôi:
     ```python
     scene.unit_settings.system = 'METRIC'
     scene.unit_settings.length_unit = 'MILLIMETERS'
     scene.unit_settings.scale_length = 0.001
     ```
   - Mọi hàm trong `src/bscu/core/math_utils.py` lấy $mm$ làm đơn vị chuẩn và tính toán chuyển đổi thống nhất sang Blender World Coordinates.

2. **Kiểm soát Phạm vi Index của CodeGraph (Tránh phình to Database):**
   - Luôn cấu hình `.gitignore` và `codegraph.json` loại trừ các bản build Blender di động (`blender/**`, `blender.shared/**`, `blender.crt/**`) và các file ẩn (`.*/**`).
   - Giữ cho database CodeGraph luôn tinh gọn (< 10 MB) và thời gian index < 1s, phản ánh đúng mã nguồn thực của dự án.

3. **Tự động Căn chỉnh Khung nhìn (Auto Frame Viewport) khi Tạo Đối tượng trên GUI:**
   - Khi Agent tạo hoặc sửa hình học trên Blender GUI qua MCP, đối tượng có thể bị lệch khỏi tầm nhìn người dùng.
   - Sau khi sinh đối tượng, tự động gọi:
     ```python
     bpy.ops.view3d.view_selected(use_all_regions=False)
     ```
     giúp đối tượng lập tức được zoom vào trung tâm màn hình, mang lại phản hồi thị giác tức thì cho người dùng.

4. **Cơ Chế Hot-Reload Add-on Thời Gian Thực (In-Memory Hot Reload):**
   - Khi chỉnh sửa code trong `src/bscu/`, không cần tắt/mở lại Blender.
   - Kích hoạt lệnh hot-reload trực tiếp trong Blender hoặc gửi qua MCP:
     ```python
     bpy.ops.bscu.reload()
     ```
   - Module `src/bscu/core/reloader.py` tự động quét cây `sys.modules` và reload lại toàn bộ 8+ module con của BSCU trong **0.05 giây**.

5. **Bộ Thẩm Định Chất Lượng Đóng Kín "1-Lệnh" (One-Command Quality Gate):**
   - Lệnh tự động duy nhất để AI Agent tự kiểm tra và tự sửa:
     ```bash
     python scripts/verify_all.py
     ```
   - Tự động chạy qua 4 chốt chặn (Gates) trong < 5 giây:
     1. Gate 1: Tuân thủ giới hạn file 300–500 dòng & Ruff linter.
     2. Gate 2: 100% Unit test toán thuần (`pytest tests/unit/`).
     3. Gate 3: Headless Blender integration test (`tests/run_tests.py`).
     4. Gate 4: Đồng bộ CodeGraph (`codegraph sync`).
   - Trả về exit code 0 khi tất cả đạt; exit code 1 kèm stack trace chi tiết khi có lỗi.

6. **Đóng Gói Extension Chuẩn Blender 4.2+ & 5.x (`scripts/package_extension.py`):**
   - Tự động thẩm định `blender_manifest.toml` và đóng gói thành `dist/bscu-{version}.zip`:
     ```bash
     python scripts/package_extension.py
     ```
   - **Bố cục zip bắt buộc:** thư mục gốc `bscu/` chứa `blender_manifest.toml` và `bscu/__init__.py`. Lệnh `blender --command extension build` của Blender 5.2 tạo zip phẳng và chính installer của Blender cũng từ chối với lỗi `__init__.py should be in a directory, not at top-level`. Vì vậy `package_extension.py` tự ghi zip và tự kiểm tra bố cục.
   - **Kiểm chứng bằng test, không bằng mắt:** `tests/integration/test_extension_install.py` cài zip vào Blender thật rồi bật/tắt add-on. Đây là chỗ duy nhất bắt được hồi quy đóng gói.
   - Module đã cài nằm ở `scripts/addons/bscu`, tên module là `bscu` (không phải `bl_ext.user_default.bscu`).

7. **`scale_length` Quyết Định Kích Thước Vật Lý — Kiểm Tra Bằng Số Đo:**
   - Với `scale_length = 0.001` (thiết lập mm chuẩn của Blender), **1 Blender unit = 1 mm**. Tạo hình cầu bán kính `0.06` tạo ra vật thể rộng **0.12 mm**, không phải 120 mm.
   - Mọi chỉ số mật độ $\rho_f$ (UV/mm) sẽ lệch đúng hệ số 1000 nếu dựng hình sai đơn vị. Khi số đo trên GUI lệch đúng một hệ số tròn, nghi ngờ `scale_length` trước khi nghi ngờ code.
   - Kiểm tra chéo bắt buộc: đối chiếu kết quả GUI với công thức lý thuyết. Ví dụ hình cầu $r = 60$ mm có $\rho^* \approx \sqrt{A_{uv} / 4\pi r^2}$; kết quả đo được 0.003477 UV/mm so với 0.003341 lý thuyết là khớp trong 4%.

8. **Tách Bề Mặt Đo Đo Khỏi Bề Mặt Gốc Khi Có Seam:**
   - Blender lưu UV **theo loop**, không theo đỉnh. Một đỉnh của cube thuộc 3 mặt, mỗi mặt cho một UV khác nhau. Đọc "một UV mỗi đỉnh" sẽ trộn 3 chart và báo nhầm mặt bị lật.
   - `bridge/snapshot.py` tách đỉnh theo cặp `(vertex, uv)` trước khi đo, và trả về cả `source_faces` (mesh gốc) cho kiểm tra topology. Bề mặt đã tách **luôn hở** ở mọi nơi bị cắt, nên kiểm tra "mesh có mappable được không" phải dùng `source_*`, không dùng bề mặt đã tách.

9. **Cô lập Suite Kiểm Thử Khi Cài Add-on Thật:**
   - Suite cài extension giữ lại bản đã cài trong `sys.modules`, khiến suite sau âm thầm chạy code cũ. `tests/run_tests.py` phải xoá cache module `bscu*` trước mỗi suite.

---

## 4. Quy Trình Thu Thập Dữ Liệu Khi Gặp Bug (Data Gathering Protocol)

Khi phát hiện lỗi hoặc sai lệch hình học (mesh bị rách, độ cao không đổi, node group lỗi socket):
1. **Trích xuất Log:** Thu thập toàn bộ stack trace từ terminal stdout/stderr.
2. **Kiểm tra Socket Node:** Duyệt danh sách socket của Node Tree:
   ```python
   for inp in node_group.interface.items_tree:
       print(inp.name, inp.in_out, inp.socket_type)
   ```
3. **Đo đạc Dữ liệu Đỉnh (Mesh Vertices Analysis):**
   - Đọc giá trị tọa độ Z của các đỉnh sau khi qua Geometry Nodes:
     $Z_{min}$, $Z_{max}$, và so sánh với thông số `cnc_base_height`.
4. **Kiểm tra tính khép kín Watertight:**
   - Dùng tool `measure_volume` kiểm tra `is_manifold == True` và `non_manifold_edge_count == 0` trước khi xuất STL.

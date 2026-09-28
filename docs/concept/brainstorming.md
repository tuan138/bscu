# TÀI LIỆU THIẾT KẾ KỸ THUẬT (TECHNICAL DESIGN DOCUMENT - TDD)
**Dự án:** Hệ thống Điêu khắc CNC 2.5D Tham số hóa trên Blender
*(Parametric 2.5D CNC Sculpting Workflow in Blender)*
**Phiên bản:** 1.0.0 | **Loại tài liệu:** Đặc tả Kiến trúc & Thuật toán

---

## MỤC LỤC
1. [TỔNG QUAN DỰ ÁN](#1-tổng-quan-dự-án)
2. [TRIẾT LÝ KIẾN TRÚC LÕI (CORE ARCHITECTURE)](#2-triết-lý-kiến-trúc-lõi)
3. [KIẾN TRÚC HỆ THỐNG 3 TẦNG (THREE-TIER ARCHITECTURE)](#3-kiến-trúc-hệ-thống-3-tầng)
4. [MÔ HÌNH DỮ LIỆU (DATA MODEL & METADATA)](#4-mô-hình-dữ-liệu-data-model)
5. [ĐẶC TẢ THUẬT TOÁN (ALGORITHMS & DATA FLOW)](#5-đặc-tả-thuật-toán)
6. [LUỒNG TRẢI NGHIỆM NGƯỜI DÙNG (USER WORKFLOW)](#6-luồng-trải-nghiệm-người-dùng)
7. [LỘ TRÌNH TRIỂN KHAI (IMPLEMENTATION ROADMAP)](#7-lộ-trình-triển-khai)

---

<h2 id="1-tổng-quan-dự-án">1. TỔNG QUAN DỰ ÁN</h2>

**1.1. Bối cảnh & Vấn đề (Pain-points)**
Các phần mềm CAM 2.5D truyền thống (ArtCAM, JDPaint) tồn tại các điểm nghẽn vật lý:
- Phụ thuộc vào Pixel (Height map Grayscale): Bị vỡ hạt răng cưa khi gia công khổ lớn hoặc cắt vát sâu.
- Quy trình Phá hủy (Destructive): Sửa chiều cao hoặc biên dạng khối bắt buộc phải làm lại từ đầu.
- Hạn chế bề mặt: Rất khó áp hoa văn phẳng lên phôi 3D cong lồi lõm phức tạp mà không làm méo tỷ lệ thiết kế.

**1.2. Giải pháp Cốt lõi (USPs)**
Hệ thống này chuyển đổi hoàn toàn sang **Toán học Hình thái (Procedural SDF)** và **Tham số hóa (Parametric)**:
- Độ nét vô cực (Infinite Resolution): Tính độ cao khối bằng trường khoảng cách toán học.
- Real-time: Đổi thông số (Ví dụ: 10mm thành 5mm) -> Khối xẹp xuống ngay lập tức trong 0.1s.
- Smart UV Mapping: Lưới tọa độ tự bù trừ độ cong, Vector vĩnh viễn không bị bóp méo.

---

<h2 id="2-triết-lý-kiến-trúc-lõi">2. TRIẾT LÝ KIẾN TRÚC LÕI</h2>

Hệ thống hoạt động dựa trên nguyên lý thiết kế đồ họa đỉnh cao: **"Tờ giấy tĩnh (2D) - Lớp màng động (3D)"**.

### Quy tắc 1: Sự Bất khả xâm phạm của Vector 2D (Immutable Vectors)
- **Vấn đề:** Các thuật toán cũ bóp méo Vector 2D để bù trừ độ cong của phôi 3D, làm hỏng file thiết kế gốc.
- **Quy tắc:** Bản vẽ Vector phẳng là **BẤT KHẢ XÂM PHẠM**. Không dùng Modifier Deform lên đường nét 2D. Một họa tiết hình tròn trên thiết kế phẳng vĩnh viễn là hình tròn tỷ lệ 1:1.

### Quy tắc 2: Dùng Map Caro làm Thước đo Biến dạng (Uniform UV Standard)
- **Quy tắc:** Sử dụng lưới UV (Caro Checker Map) làm vật chịu sự biến dạng. Máy tính liên tục giải phương trình lực căng để ép các ô Caro trên bề mặt cong 3D thành **hình vuông hoàn hảo nhất có thể**.
- **Hệ quả logic:** Khi ô Caro trên 3D vuông 1:1, Vector 2D (cũng đặt trên Caro vuông) sẽ chiếu lên 3D chuẩn xác tỷ lệ gốc, không bị kéo sọc, không vỡ nét. Sự biến dạng (Distortion) sẽ bị đẩy hết ra phần viền (Seam) của bản rập 2D.

---

<h2 id="3-kiến-trúc-hệ-thống-3-tầng">3. KIẾN TRÚC HỆ THỐNG 3 TẦNG (THREE-TIER ARCHITECTURE)</h2>

Kiến trúc luồng dữ liệu (Data Pipeline) chảy một chiều qua 3 tầng:

### TẦNG 1: Môi trường Vẽ 2D Tham số (2D Canvas & Data Input)
*Giao diện mô phỏng AutoCAD, nơi User thao tác và nạp siêu dữ liệu.*
- **Workspace:** Khóa góc nhìn Top Orthographic (Phím 7). Z-Lock kích hoạt. Bật Absolute Grid Snap.
- **Bản rập UV (Live Canvas):** Khung giới hạn (Bounding Box) do phôi 3D trải bẹp ra. User sắp xếp Vector lọt lòng vào đây.
- **Tích hợp Tham số:** Các đường Vector 2D mỏng dính nhưng mang "siêu dữ liệu" (Metadata) do User nhập từ UI Panel.

### TẦNG 2: Động cơ Hình học Ảo (Procedural Geometry Engine)
*Trái tim Toán học (Geometry Nodes) dịch siêu dữ liệu thành độ cao.*
- Thu thập Vector kín từ Tầng 1, biến thành mặt phẳng (N-gons).
- Chạy thuật toán đo khoảng cách (SDF).
- Trả về kết quả là một **Bản đồ Độ cao Ảo (Virtual Height Map)** tồn tại dưới dạng Data Float trên RAM (Chưa phải Mesh vật lý).

### TẦNG 3: Bơm Khối & Tương tác 3D (3D Projection & Displacement)
*Cầu nối ốp bản đồ độ cao lên phôi thật.*
- Động cơ UV nội bộ liên tục chạy ngầm API làm mịn lưới (Relax).
- Chiếu dữ liệu Z-Height ảo từ Tầng 2 sang hệ tọa độ U,V của phôi Tầng 3.
- Dùng lệnh đẩy lưới (`Displacement/Set Position`) dọc theo vector pháp tuyến (`Normal`) để tạo ra bề mặt điêu khắc lồi lõm thực sự.

---

<h2 id="4-mô-hình-dữ-liệu-data-model">4. MÔ HÌNH DỮ LIỆU & SIÊU DỮ LIỆU (DATA MODEL)</h2>

Đặc tả các biến lưu trữ trong thuộc tính `Custom Properties` của các Object.

**4.1. Đối tượng Nét hở (Open Curve) - Đục rãnh, V-Carve**
- **Type:** Bezier Curve (U_Cyclic = False)
- **Point Data:** `Radius` (Lực nhấn / Độ rộng rãnh), `Tilt` (Góc nghiêng rãnh).
- **Object Metadata:**
  - `Float: cnc_tool_radius` (Kích thước dao cắt tổng - mm)
  - `Enum: cnc_tool_profile` (0: V-Bit, 1: Ball-nose, 2: End-mill)

**4.2. Đối tượng Mặt kín (Closed Curve) - Phù điêu đắp dương / Khoét âm**
- **Type:** Bezier Curve (U_Cyclic = True)
- **Object Metadata (Thông qua UI Panel):**
  - `Float: cnc_base_height` (Độ cao đôn nền cơ sở, khoảng cách từ phôi lên mặt phẳng đáy khối - mm)
  - `Float: cnc_bevel_angle` (Góc vát viền, 0-90 độ)
  - `Float: cnc_bevel_depth` (Chiều dài cạnh vát tối đa - mm)
  - `Enum: cnc_profile_shape` (0: Phẳng/Flat, 1: Vòm/Dome, 2: Chóp/Pyramid)
  - `Enum: cnc_blend_mode` (1: Add/Đắp dương, -1: Subtract/Khoét lõm)

**4.3. Đối tượng Phôi 3D (Base Mesh)**
- **Type:** Polygon Mesh (Khuyến nghị: Quads)
- **Modifiers:**
  1. `Subdivision Surface` (Level 3-5, cung cấp lưới đủ dày để đẩy đỉnh)
  2. `Geometry Nodes` (Nhận tín hiệu từ Tầng 2 để Displace)
- **Data:** `UVMap` chính, Cạnh đánh dấu `Seam`.

---

<h2 id="5-đặc-tả-thuật-toán">5. ĐẶC TẢ THUẬT TOÁN (ALGORITHMS)</h2>

### 5.1. Thuật toán SDF (Signed Distance Field) - Tạo khối độ nét vô cực
Logic cụm Node bên trong Tầng 2:
1. **Input:** Nhận Curve Kín -> Dùng `Fill Curve` bít mặt lại thành lưới N-gons.
2. **Lấy Viền (Boundary):** Dùng `Mesh to Curve` (Chỉ lấy viền) -> Ra sợi dây chu vi.
3. **Đo Khoảng cách (Proximity):** Dùng `Geometry Proximity`. Đo khoảng cách ngắn nhất từ mỗi điểm ảnh (Point) bên trong mặt lưới đập ra sợi dây chu vi.
4. **Gán biến:** Lưu khoảng cách này thành thuộc tính `$Dist`. ($Dist = 0 ở viền, lớn dần khi vào tâm).
5. **Dựng Khối (Beveling Math):**
   - Dùng `Math: Multiply` -> Lấy `$Dist` nhân với $Tan(cnc\_bevel\_angle)$.
   - Dùng `Math: Minimum` -> Khống chế chiều cao trần không được vượt quá `cnc_base_height` (chống lỗi đâm thủng khối ở các góc nhọn).
6. **Định hình (Profile):** Đưa kết quả qua đồ thị `Float Curve`. Đồ thị tuyến tính = Vát chóp; Đồ thị vòng cung = Khối vòm.
7. **Output:** Lưu thành thuộc tính `$Z_Height_Virtual`.

### 5.2. Thuật toán Dàn đều Lưới (UV Relax / ARAP Engine)
Để giải quyết bài toán chống méo (Distortion):
1. Khi User rạch phôi (Mark Seam) và bấm nút trải, hệ thống gọi API: `bpy.ops.uv.unwrap(method='CONFORMAL')` để bảo toàn góc 90 độ của ô Caro.
2. Sau đó, tự động gọi API: `bpy.ops.uv.minimize_stretch(iterations=100)`. Thuật toán hệ lò xo (As-Rigid-As-Possible) sẽ tự động trượt các đỉnh trên 2D để dàn đều lực căng, giúp Caro ở mọi vị trí trên phôi to bằng nhau.

---

<h2 id="6-luồng-trải-nghiệm-người-dùng">6. LUỒNG TRẢI NGHIỆM NGƯỜI DÙNG (USER WORKFLOW)</h2>
*(Tối giản "Idiot-proof" cho người không rành 3D)*

1. **Chuẩn bị Phôi (Môi trường 3D):**
   - Mở Tượng/Phôi 3D.
   - Vạch đường rạch cắt (Seam) tại nách, gầm, sống lưng.
   - Bấm nút `[Khởi tạo Phôi]`. Giao diện tự chia 2 màn hình, Caro dàn đều tăm tắp.
2. **Vẽ / Nhập Hoa văn (Môi trường 2D):**
   - Thả file SVG họa tiết lọt vào bên trong phần màng bọc UV vừa được trải ra ở màn hình 2D. (Khu vực nét đứt).
3. **Tham số hóa Khối:**
   - Chọn bông hoa. Mở bảng bên phải (N-Panel), nhập số liệu: `Cao = 10mm`, `Vát = 45 độ`, `Dạng = Vòm`.
   - Phù điêu bông hoa nổi lên trên Tượng ở màn hình bên cạnh ngay lập tức.
4. **Hiệu chỉnh Tương tác (Gizmo Control):**
   - *Dời vị trí:* Nắm vòng tròn điều khiển (Gizmo) trên lưng tượng kéo xuống bụng. Hoa văn trượt mượt mà bám theo độ cong của bụng.
   - *Chống méo Caro:* Hoa văn vắt qua vai bị méo? Nắm Tay cầm phụ ở vai, vặn lệnh `Relax`. Caro co lại vuông vức, nét sắc lại.
   - *Chỉnh sửa theo ý khách:* Khách chê hoa nổi quá, gõ số từ 10mm xuống 5mm. Khối lập tức xẹp xuống.
5. **Xuất xưởng:**
   - Nhấn `[Bake & Export STL]`.
   - Hệ thống tự Apply Modifier, dọn rác, xuất ra file Mesh kín (Watertight) đưa vào máy lập trình dao CNC.

---

<h2 id="7-lộ-trình-triển-khai">7. LỘ TRÌNH TRIỂN KHAI (IMPLEMENTATION ROADMAP)</h2>

**Phase 1: Lõi Toán học SDF (Geometry Nodes)**
- [ ] Dựng cụm Node bít mặt Curve kín.
- [ ] Viết logic `Geometry Proximity` đo khoảng cách `$Dist`.
- [ ] Lập trình giải phương trình chặn trần (Clamp Height) chống xuyên lưới.
- [ ] Xây dựng Node Group `Float Curve` điều khiển profile (Flat/Dome/Pyramid).

**Phase 2: Hệ thống Phép chiếu (Projection) & Bơm khối**
- [ ] Đọc tín hiệu Z ảo từ Phase 1 sang Không gian 3D.
- [ ] Sử dụng `Sample UV Surface` đồng bộ tọa độ (X,Y) = (U,V).
- [ ] Cắm `$Z_Height_Virtual` vào lệnh đẩy Normal (`Set Position`).
- [ ] Test độ mượt mà khi di chuyển UV.

**Phase 3: Backend Python Scripting (UI & Data)**
- [ ] Viết Add-on sinh N-Panel Toolbar.
- [ ] Khai báo tự động các Custom Properties (Biến Metadata) khi khởi tạo Curve.
- [ ] Dùng `Drivers` kết nối các thanh trượt UI vào Input của Geometry Nodes.

**Phase 4: Frontend UX, Gizmos & Xuất file**
- [ ] Lập trình `Empty Objects` làm Gizmo trên bề mặt phôi 3D, liên kết tọa độ vào UV Mapping Node.
- [ ] Gói API `bpy.ops.uv.minimize_stretch` thành nút bấm 1-Click trên giao diện 3D.
- [ ] Viết Macro dọn dẹp hệ thống và lệnh `Export STL` chuẩn Watertight.
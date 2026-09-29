# TÀI LIỆU THIẾT KẾ KỸ THUẬT (TECHNICAL DESIGN DOCUMENT - TDD)
**Dự án:** Hệ thống Điêu khắc CNC 2.5D Tham số hóa trên Blender
*(Parametric 2.5D CNC Sculpting Workflow in Blender)*
**Phiên bản:** 1.1.0 | **Loại tài liệu:** Đặc tả Kiến trúc & Thuật toán

---

## MỤC LỤC
1. [TỔNG QUAN DỰ ÁN](#1-tổng-quan-dự-án)
2. [TRIẾT LÝ KIẾN TRÚC LÕI (CORE ARCHITECTURE)](#2-triết-lý-kiến-trúc-lõi)
3. [KIẾN TRÚC HỆ THỐNG 3 TẦNG (THREE-TIER ARCHITECTURE)](#3-kiến-trúc-hệ-thống-3-tầng)
4. [MÔ HÌNH DỮ LIỆU (DATA MODEL & METADATA)](#4-mô-hình-dữ-liệu-data-model)
5. [KIẾN TRÚC STUDIO 2D CAD & GIAO DIỆN (HYBRID VIEWPORT)](#5-kiến-trúc-studio-2d-cad--giao-diện)
6. [ĐẶC TẢ THUẬT TOÁN (ALGORITHMS & DATA FLOW)](#6-đặc-tả-thuật-toán)
7. [LUỒNG TRẢI NGHIỆM NGƯỜI DÙNG (USER WORKFLOW)](#7-luồng-trải-nghiệm-người-dùng)
8. [LỘ TRÌNH TRIỂN KHAI (IMPLEMENTATION ROADMAP)](#8-lộ-trình-triển-khai)
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

<h2 id="5-kiến-trúc-studio-2d-cad--giao-diện">5. KIẾN TRÚC STUDIO 2D CAD & GIAO DIỆN (HYBRID VIEWPORT - PHƯƠNG ÁN B)</h2>

Hệ thống giao diện 2D Canvas được thiết kế chuyên biệt theo mô hình **3 Cột tương tác (3-Pane Studio)**, phối hợp giữa UI Panels chuẩn của Blender và GPU Shading Engine thời gian thực:

```
+--------------------+------------------------------------------+-----------------------+
|  LEFTBAR (Layers)  |         CENTERBAR (2D CAD Canvas)        |  RIGHTBAR (Inspector) |
+--------------------+------------------------------------------+-----------------------+
| [Eye] [Lock] [Add] | - Navigation: Pan (MMB), Zoom (Scroll)   | [Context: Line/Region]|
|                    | - Snap: End, Mid, Nearest, Intersect     | - Height: 10.0mm      |
| [>] Group 1        | - Draw: Line, Arc 3-pt, Spline           | - Blend: Add / Sub    |
|   [*] Layer Nét vẽ | - Edit: Fillet, Chamfer, Trim, Extend    |                       |
|   [o] Layer Màu sắc| - Associativity: Sửa nét -> Vùng tự nhảy | [Biểu đồ Spline dốc]  |
|   [#] Layer Vùng   | - Region Manipulator: Mạng lưới đường    |   /‾‾\____  (Dot sel) |
|                    |   sinh dốc (UV Grid) & Dot kéo thả       |                       |
| (Drag-drop z-order)|   trực tiếp trên Viewport 2D             | [Biểu đồ Cắt vuông góc|
+--------------------+------------------------------------------+-----------------------+
```

### 5.1. Leftbar — Quản lý Layer phân tầng (Photoshop Style)
- **Công cụ trên Header:** Bật/tắt ẩn hiện Layer được chọn, nút Tạo mới Layer, nút Tạo Nhóm Layer (Layer Group).
- **Tương tác danh sách:**
  - Hỗ trợ Kéo thả (Drag & Drop) để sắp xếp thứ tự hiển thị ($Z$-Order: Layer nằm trên sẽ đè và hiển thị phía trên trong Centerbar).
  - Đầu mỗi Layer có icon Mắt (`Eye`) để ẩn/hiện và icon Khóa (`Lock`) để chống chỉnh sửa vô ý.
- **3 Kiểu Layer chuyên dụng (Thiết lập qua chuột phải):**
  1. **Layer Nét vẽ (Carving Stroke):** Chứa các đường vector dẫn đường. Thuật toán điêu khắc sẽ lấy các đường trong layer này để tính toán rãnh vát, chạm khắc dọc đường nét.
  2. **Layer Màu sắc (Color Tint):** Dùng để xác định vùng hoặc đường (có độ dày) để tô màu sắc và phân định vật liệu bề mặt.
  3. **Layer Vùng (Bounded Region):** Nơi chứa các vùng khép kín tự động sinh ra từ các nét kín của *Layer Nét vẽ*.

### 5.2. Centerbar — Môi trường tương tác 2D CAD & Lưới nắn dốc (CAD Workspace)
- **Thao tác khung nhìn:** Zoom bằng cuộn chuột giữa (Scroll), Pan bằng giữ chuột giữa (MMB Drag), Quét chọn vùng (Marquee / Box Select).
- **Bắt điểm thông minh (Smart Snapping):** Bắt điểm đầu/cuối (Endpoints), trung điểm (Midpoints), điểm nằm trên đường (On-Curve), và giao điểm các đường (Intersections).
- **Bộ công cụ vẽ & biến đổi hình học:**
  - Vẽ đoạn thẳng (Line), vẽ cung tròn qua 3 điểm (Arc 3-point), vẽ đường cong Spline.
  - Khi chọn đường Spline hoặc đoạn thẳng: Lập tức hiển thị các điểm neo (Anchor points & Tangent handles) để co kéo trực quan.
  - Công cụ CAD hình thái: Bo góc (Fillet), Vát góc (Chamfer), Kéo dài (Extend), Cắt tỉa đoạn thừa (Trim), Di chuyển (Move).
- **Tính liên đới hình học (Topological Associativity):**
  - Nét vẽ và Vùng kín duy trì quan hệ đồ thị phẳng (Planar Graph).
  - Khi thay đổi bất kỳ đường nét nào cấu thành nên một Vùng kín, Vùng đó sẽ tự động cập nhật lại diện tích và biên dạng tức thì.
- **Bộ nắn đường sinh dốc (Region Slope Grid Manipulator):**
  - Khi một Vùng được chọn, trên mặt phẳng 2D hiển thị mạng lưới các đường sinh dốc ngang/dọc (Patch Flow Lines).
  - Các giao điểm của lưới là các điểm điều khiển (Dots). Người dùng có thể kéo thả các Dot này để tinh chỉnh cao độ và độ dốc cục bộ của mặt phù điêu.

### 5.3. Rightbar — Bảng thuộc tính ngữ cảnh & Biểu đồ dốc 2 cấp (Inspector)
- **Tự động đổi ngữ cảnh theo Selection:**
  - Chọn Đường $\to$ Hiển thị công cụ biên tập đường, độ sâu đục rãnh, profile dao cắt.
  - Chọn Vùng $\to$ Hiển thị công cụ biên tập diện tích, độ cao đắp ($Add$) / khoét lõm ($Subtract$).
- **Hệ thống Biểu đồ Đôi (Dual-Spline Profile Editor):**
  - *Spline 1 (Biểu đồ chính):* Đường cong thể hiện sự biến thiên độ dốc/chiều cao theo biên dạng (tương tự đồ thị Curve trong 3ds Max). Trên đường cong có các điểm neo (Dots) để thay đổi vị trí.
  - *Spline 2 (Biểu đồ cắt vuông góc):* Khi click chọn 1 Dot trên Spline 1, một biểu đồ thứ hai xuất hiện để hiệu chỉnh riêng cho Dot này:
    - *Đối với Vùng:* Định nghĩa độ dốc của phương vuông góc với điểm đó.
    - *Đối với Đường:* Định nghĩa cao độ hoặc độ sâu tại vị trí lát cắt.

---

<h2 id="6-đặc-tả-thuật-toán">6. ĐẶC TẢ THUẬT TOÁN (ALGORITHMS & DATA FLOW)</h2>

### 6.1. Thuật toán Lõi SDF — Lưới lấy mẫu chuẩn hóa (Uniform Sampling Grid Engine)
*Khắc phục triệt để hạn chế của nút `Fill Curve` (vốn chỉ nối tam giác ở biên mà không có đỉnh nội suy ở tâm).*
1. **Sinh lưới chuẩn (Grid Generation):** Tầng 2 tạo lưới phẳng Quad đồng nhất (`Grid` primitive) bao trùm Canvas với độ phân giải bước lưới tham số hóa (ví dụ: `step = 0.2mm - 0.5mm`).
2. **Mặt nạ trong/ngoài (Raycast In-Out Masking):** 
   - Bít kín các đường Curve của *Layer Vùng* thành mặt phẳng tạm.
   - Dùng tia chiếu `Raycast` từ trên trục $Z$ xuống: Các đỉnh của Grid đâm trúng mặt phẳng $\to$ Gán thuộc tính `$Inside = 1.0$; các đỉnh nằm ngoài gán `$Inside = 0.0$.
3. **Đo khoảng cách (Geometry Proximity):**
   - Với các đỉnh có `$Inside = 1.0$`, dùng `Geometry Proximity` (Target: Viền Curve khép kín) để đo khoảng cách ngắn nhất $Dist$ từ đỉnh lưới ra chu vi.
4. **Dựng độ dốc vát & Chặn trần (Bevel Slope & Clamp):**
   - $Height_{raw} = Dist \times \tan(cnc\_bevel\_angle)$.
   - $Height_{clamped} = \min(Height_{raw}, cnc\_base\_height)$.
5. **Định hình Profile đa cấp:** 
   - Đưa giá trị qua đồ thị `Float Curve` (Spline 1 & Spline 2 do Rightbar nạp vào qua Geometry Node inputs) để sinh ra khối Vòm cong hoặc Chóp nhọn.
6. **Output:** Xuất thuộc tính độ cao ảo `$Z_Height_Virtual` trên toàn bộ đỉnh của lưới.

### 6.2. Thuật toán Dàn đều Lưới (UV Relax / ARAP Engine)
Để giải quyết bài toán chống méo (Distortion):
1. Khi User rạch phôi (Mark Seam) và bấm nút trải, hệ thống gọi API: `bpy.ops.uv.unwrap(method='CONFORMAL')` để bảo toàn góc 90 độ của ô Caro.
2. Sau đó, tự động gọi API: `bpy.ops.uv.minimize_stretch(iterations=100)`. Thuật toán hệ lò xo (As-Rigid-As-Possible) sẽ tự động trượt các đỉnh trên 2D để dàn đều lực căng, giúp Caro ở mọi vị trí trên phôi to bằng nhau.

---

<h2 id="7-luồng-trải-nghiệm-người-dùng">7. LUỒNG TRẢI NGHIỆM NGƯỜI DÙNG (USER WORKFLOW)</h2>

1. **Khởi tạo Studio & Chuẩn bị Phôi:**
   - Bấm `[Khởi tạo Studio 2.5D]`. Màn hình chia bố cục 3 cột: Leftbar (Layers), Centerbar (2D CAD Canvas) và Rightbar (Inspector).
   - Bên cạnh mở song song cửa sổ 3D Viewport hiển thị Phôi với lưới Caro đồng đều.
2. **Thao tác Vẽ & Phân tầng Vector (Leftbar & Centerbar):**
   - Tạo các Layer: Nét vẽ, Vùng kín, Màu sắc.
   - Dùng các công cụ CAD (Line, Arc 3-pt, Spline, Trim, Fillet) với chế độ bắt điểm thông minh để hoàn thiện hoa văn.
   - Các vùng kín tự động được nhận diện và liên kết với Layer Vùng.
3. **Nắn chỉnh Độ dốc & Cao độ Phù điêu (Rightbar & Centerbar):**
   - Click chọn một Vùng: Kéo thả các Dot trên mạng lưới đường sinh dốc ở Centerbar.
   - Nhìn sang Rightbar: Tinh chỉnh đường cong Spline 1 (Độ dốc tổng) và Spline 2 (Mặt cắt vuông góc). Khối 3D trên màn hình đối diện phản hồi tức thì.
4. **Xuất xưởng:**
   - Nhấn `[Bake & Export STL]`. Hệ thống tự làm kín đáy, kiểm tra Watertight và xuất file chuẩn gia công CNC.

---

<h2 id="8-lộ-trình-triển-khai">8. LỘ TRÌNH TRIỂN KHAI (IMPLEMENTATION ROADMAP)</h2>

**Phase 1: Lõi Toán học SDF & Thuật toán Hình thái 2D (Pure Logic Core)**
- [ ] Viết bộ giải thuật đồ thị phẳng 2D (Planar Graph / Closed Loop Extraction) trong `src/bscu/core/cad/`.
- [ ] Lập trình giải thuật Trim, Extend, Fillet, Chamfer thuần Python (`tests/unit/`).
- [ ] Xây dựng cụm Geometry Nodes đo khoảng cách SDF trên Lưới phẳng chuẩn hóa (Uniform Sampling Grid).
- [ ] Tích hợp bộ chặn trần chống xuyên khối và điều khiển `Float Curve`.

**Phase 2: Hệ thống Studio 2D Canvas (Hybrid Viewport Engine)**
- [ ] Xây dựng Leftbar: Quản lý danh sách Layer, kéo thả Z-order, phân loại 3 kiểu Layer.
- [ ] Xây dựng Centerbar: Modal Operator + GPU Shader vẽ đường bắt điểm, hiển thị anchor/tangent dots, và lưới nắn đường sinh dốc.
- [ ] Xây dựng Rightbar: Bảng thuộc tính ngữ cảnh và widget điều khiển đồ thị độ dốc 2 cấp (Dual-Spline).

**Phase 3: Hệ thống Phép chiếu (Projection) & Bơm khối**
- [ ] Đọc tín hiệu Z ảo từ Phase 1 sang Không gian 3D.
- [ ] Sử dụng `Sample UV Surface` đồng bộ tọa độ (X,Y) = (U,V).
- [ ] Cắm `$Z_Height_Virtual` vào lệnh đẩy Normal (`Set Position`).
- [ ] Đồng bộ hóa tính tương tác thời gian thực giữa 2D Canvas và 3D Model.

**Phase 4: Tự động hóa Dọn rác & Xuất STL Watertight**
- [ ] Tích hợp macro 1-Click làm mịn lưới UV (`bpy.ops.uv.minimize_stretch`).
- [ ] Tự động hóa hàn kín thành và đáy tạo khối Watertight không lỗi non-manifold.
- [ ] Xuất file STL chuẩn và báo cáo dung tích/kích thước phôi.
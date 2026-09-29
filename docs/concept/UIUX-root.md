UI và UX như sau:
Tôi vào Blender sau đó tạo mô hình 3D (phôi), sau khi tạo 3D xong tôi sẽ mở addon lên. Addon có các tab:
Tab 1: tên là "Caro map":
Đây là bước đầu tiên của quy trình:Mục đích là để áp 1 map caro lên mô hình 3D để xem các ô caro phân bố trên mô hình đều chưa và có thể phân bố lại 1 cách thủ công theo vùng cụ thể hoặc tự động, khi Map caro được trải lên mô hình ổn rồi thì các thông số UV sẽ là cơ sở để sau khi có highmap sẽ gán heighmap trở lại mô hình dựa trên UV của map caro này.
Khi ở tab caro map Mô hình lập tức được gán vật liệu caro lên toàn bộ mô hình để user kiểm tra ngay lập tức. Mô hình 3D sẽ là 1 mô hình phức tạp với nhiều hình dạng cong lồi lõi khác nhau. user sẽ xem việc phân bố các ô caro trên mô hình được đồng đều hay chưa bằng cách có thể scale ô caro to nhỏ,và dùng các chức năng phân tự động phân bố caro đồng đều theo thuật toán đã bàn hoặc chọn cục bộ 1 vùng để kéo giãn hay co lại để điều chỉnh mật độ và kích thước UV vùng đó để đảm bảo mật độ và kích thước của caro được đồng đều và có kích thước tương đối đều nhau. Hãy học cách mà các phần mềm chuyên nghiệp làm để tham khảo và thực hiện.
Khi quay lại tab này ta cũng có thể chỉnh sửa lại UV và ở các bước tiếp theo thì UV cũng được đồng bộ cập nhật.
Tab 2: Seam:
Sau khi đã gán caro map và chỉnh sửa UV thì đây là chức năng dùng để tách từng mảng của mô hình thành từng phần để trải ra thành 2D. Vì mô hình phức tạp nên chúng ta cần cắt bề mặt mô hình thành từng phần nhỏ đảm bảo khi trải trên mặt phẳng 2D thì chúng không bị overlap lên nhau để chuẩn bị cho bước tạo heigmap trên đó.
Tại bước này user có thể tạo đường seam bằng cách chọn các đường sinh của mô hình, các đường này sẽ liên tục với nhau thành 1 đường kín để tách bề mặt mô hình thành từng mảng khác nhau, addon sẽ hỗ trợ chọn 2 đoạn đầu và cuốicủa 1 chuỗi đường và chọn các đường liên tục. Hoặc dùng 1 mặt phẳng tham chiếu để cắt những mặt được chọn để tạo đường cắt giữa về mặt mô hình và mặt phẳng tham chiếu để tạo 1 đường cắt liên tục và dùng nó thành đường seam.
Hoặc vẽ một mặt phẳng tham chiếu sau đó chiếu các mặt đã chọn lên mặt phẳng đã chọn đó và lấy đường viền của những mặt phẳng đã chọn đó để tạo đường cắt trên mặt đã chọn.
Ta cũng có thể chọn các mặt của mô hình, các mặt này liên kết với nhau thành 1 tổ hợp các mặt và tạo đường seam chính là đường viền bao mặt đó.
Tôi muốn khi quay lại chỉnh sửa đường seam thì ở bước sau là bước unwrap thì các mảng đó cũng được cập nhật đồng bộ

Tab 3: Unwrap:
Mục đích của tab này là trải phẳng mặt 3D của mô hình 3D thành 2D để chuẩn bị cho bước đưa heighmap vào các vùng đã unwrap này, sau đó heighmap sẽ được gán ngay lập tức và mô hình 3D để user có thể xem được mô hình 3D thay đổi ngay lập tức.
Dựa vào các đường seam đã được tạo ở tab3 thì mặt 3D của mô hình 3D sẽ được trải phẳng ra, hãy dùng các thuật toán có sẵn của blender hoặc các thuật toán khác để trải phẳng mặt 3D này, khi thay đổi ở tab này thì tab 4 cũng sẽ được thay đổi theo

Tab 4: Heigh map:
Đây là bước để tạo heighmap bằng các dựa vào các đường vector để tạo thành heimap theo ý muốn của người dùng, và đặc biệt có thể thay đổi heighmap 1 cách nhanh chóng và dễ dàng.
Đây là UI UX của nó:
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
  3. **Layer Vùng (Bounded Region):** Nơi chứa các vùng khép kín tự động sinh ra từ các nét kín của _Layer Nét vẽ_.

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
  - _Spline 1 (Biểu đồ chính):_ Đường cong thể hiện sự biến thiên độ dốc/chiều cao theo biên dạng (tương tự đồ thị Curve trong 3ds Max). Trên đường cong có các điểm neo (Dots) để thay đổi vị trí.
  - _Spline 2 (Biểu đồ cắt vuông góc):_ Khi click chọn 1 Dot trên Spline 1, một biểu đồ thứ hai xuất hiện để hiệu chỉnh riêng cho Dot này:
    - _Đối với Vùng:_ Định nghĩa độ dốc của phương vuông góc với điểm đó.
    - _Đối với Đường:_ Định nghĩa cao độ hoặc độ sâu tại vị trí lát cắt.

# Benchmark MySQL và MongoDB

Bộ benchmark này chỉ đọc dữ liệu; không thay đổi schema hoặc ghi/xóa dữ liệu.
Mọi file được tạo đều nằm trong `ecommerce-benchmark/results/`.

## Các workload

| Workload | MySQL | MongoDB |
|---|---|---|
| `order_detail` | Đọc order và 3 bảng con trong 4 truy vấn | Đọc một document order đã embed dữ liệu con |
| `customer_order_history` | Đọc lịch sử order và lấy dữ liệu con theo batch | Đọc các order của customer, dữ liệu con đã embed |
| `filtered_orders_page` | Lọc status + khoảng thời gian, sort, limit 100 | Cùng điều kiện, sort và limit 100 |
| `order_count_by_status` | `GROUP BY order_status` | Aggregation `$group` |
| `sales_by_product` | Join orders/order_items, nhóm theo product | Match orders, unwind `items`, nhóm theo product |

Hai workload đầu đo cách truy cập theo mô hình dữ liệu thực tế của dự án, không phải
so sánh hai câu lệnh có cùng số round-trip: MySQL chuẩn hóa dữ liệu theo bảng,
còn MongoDB lưu items/payments/reviews bên trong order.

Trước khi đo, chương trình:

1. Kiểm tra cấu hình kết nối và ping MongoDB.
2. So sánh số bản ghi MySQL với document MongoDB, gồm cả tổng số phần tử được
   nhúng trong `orders`. Nếu khác, benchmark dừng mặc định.
3. Chạy mỗi workload một lần trên cả hai DB, chuẩn hóa và so sánh SHA-256 của
   kết quả; nếu khác, không đo workload đó.
4. Chạy warm-up rồi đo latency từng lần. Thứ tự MySQL/MongoDB được luân phiên.
5. Ghi median, p95, min/max và số kết quả ra JSON/CSV.

Với dữ liệu tiền tệ đang là `double` trong MongoDB và `DECIMAL` trong MySQL,
phép so sánh kết quả chuẩn hóa số thực về 2 chữ số thập phân.

## Chạy

Yêu cầu: MySQL và MongoDB đang chạy, đã nạp cùng một bộ dữ liệu, và file
`C:\Workspace\HQTCSDL\.env` có các biến:

```text
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_DATABASE=ecommerce_olist
MONGO_URI=mongodb://localhost:27017/
MONGO_DATABASE=ecommerce_olist
```

Từ PowerShell tại thư mục gốc dự án:

```powershell
.\.venv\Scripts\python.exe .\ecommerce-benchmark\benchmark.py
```

Chạy nhanh hoặc tăng số lần lặp:

```powershell
.\.venv\Scripts\python.exe .\ecommerce-benchmark\benchmark.py --warmup 3 --iterations 10
.\.venv\Scripts\python.exe .\ecommerce-benchmark\benchmark.py --warmup 10 --iterations 100
```

Không khuyến nghị bỏ kiểm tra số lượng; chỉ dùng nếu đã biết rõ khác biệt dữ liệu:

```powershell
.\.venv\Scripts\python.exe .\ecommerce-benchmark\benchmark.py --skip-count-check
```

## Cách chạy để kết quả đáng tin cậy

- Chạy cả hai database trên cùng máy, cùng trạng thái tải, cùng dữ liệu và cấu hình
  tài nguyên; không chạy ETL/import trong lúc đo.
- Đóng các ứng dụng nặng khác. Thực hiện tối thiểu 3 lượt benchmark riêng biệt.
- Dùng median để so sánh chính, p95 để xem độ trễ đuôi; đừng kết luận từ một lượt.
- Mặc định các truy vấn được warm-up và lặp lại nên đây là kết quả **warm-cache**.
  Script không xóa cache hệ điều hành hoặc cache database.
- `MYSQL/MONGO > 1` nghĩa là median MySQL chậm hơn; `< 1` nghĩa là median MySQL
  nhanh hơn cho workload đó. Đây không phải kết luận chung database nào tốt hơn.
- Kiểm tra `result_sha256` giống nhau giữa hai DB trước khi dùng latency.
- `sales_by_product` tính tổng giá item (`price`), không cộng phí vận chuyển.
- Bộ dữ liệu geolocation không được ETL hiện tại đưa vào MySQL/MongoDB nên không
  nằm trong workload này.

## Giới hạn

- Đây là benchmark workload ứng dụng đọc dữ liệu, bao gồm cả thời gian round-trip
  và materialize kết quả; không phải benchmark phần cứng hay thông lượng tải đồng
  thời.
- Script không tự tạo/xóa dữ liệu thử nghiệm và không chạy write benchmark.
- Chỉ số `result_rows` là số phần tử cấp cao nhất của kết quả; workload tổng hợp
  báo số nhóm.
- Bộ truy vấn phụ thuộc các bảng/collection hiện có trong schema của dự án.

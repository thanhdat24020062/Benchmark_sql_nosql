# So sánh hiệu năng MySQL và MongoDB & Quản trị dữ liệu không gian

Dự án thực hiện so sánh hiệu năng giữa MySQL và MongoDB trên bộ dữ liệu thương mại điện tử quy mô lớn, đồng thời nghiên cứu các kỹ thuật quản trị và truy vấn dữ liệu không gian.

## 1. Tổng quan dự án

Dự án gồm hai phần chính:

- **Phần A – So sánh hiệu năng MySQL và MongoDB:** Xây dựng cơ sở dữ liệu trên cùng một bộ dữ liệu thương mại điện tử, thiết kế mô hình dữ liệu phù hợp với từng hệ quản trị và đánh giá hiệu năng thông qua các truy vấn thực tế.
- **Phần B – Quản trị dữ liệu không gian:** Nghiên cứu mô hình dữ liệu không gian, phương pháp lưu trữ, cấu trúc chỉ mục và các kỹ thuật truy vấn dữ liệu không gian.

Mục tiêu là đánh giá ảnh hưởng của mô hình dữ liệu, chỉ mục và cách tổ chức truy vấn đến hiệu năng của các hệ quản trị cơ sở dữ liệu.

## 2. Bộ dữ liệu

**Nguồn dữ liệu:** [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)

Đây là bộ dữ liệu thương mại điện tử tại Brazil, bao gồm thông tin khách hàng, người bán, sản phẩm, đơn hàng, thanh toán, đánh giá và vị trí địa lý.

### Các bảng dữ liệu chính

| Bảng | Số lượng bản ghi (xấp xỉ) |
|---|---:|
| `orders` | 99.441 |
| `order_items` | 112.650 |
| `order_payments` | 103.886 |
| `order_reviews` | 99.224 |
| `products` | 32.951 |
| `sellers` | 3.095 |
| `geolocation` | ~1.000.000 |

Bộ dữ liệu gốc gồm 9 tệp CSV:

- `olist_customers_dataset.csv`
- `olist_geolocation_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `olist_orders_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `product_category_name_translation.csv`

**Lưu ý:** Bảng `geolocation` được sử dụng cho phần quản trị dữ liệu không gian, không nằm trong phạm vi benchmark MySQL và MongoDB hiện tại.

## 3. Kiến trúc và luồng xử lý dữ liệu

```text
              Olist Dataset
                (CSV Files)
                     |
                     v
                 MySQL DB
             (Relational Model)
                     |
                     | ETL
                     v
                MongoDB
             (Document Model)
                     |
                     v
              Benchmark Script
                     |
                     v
              Results (JSON/CSV)
```

Quy trình thực hiện:

1. Tải và kiểm tra dữ liệu CSV từ Olist.
2. Xây dựng cấu trúc cơ sở dữ liệu quan hệ trên MySQL.
3. Import dữ liệu CSV vào MySQL.
4. Thực hiện ETL từ MySQL sang MongoDB.
5. Kiểm tra tính nhất quán giữa hai hệ quản trị.
6. Chạy benchmark và lưu kết quả đo hiệu năng.

## 4. Thiết kế cơ sở dữ liệu

### 4.1. MySQL – Mô hình quan hệ

MySQL sử dụng mô hình dữ liệu quan hệ, tổ chức dữ liệu thành các bảng riêng biệt và liên kết thông qua khóa chính, khóa ngoại.

Các bảng chính:

- `customers`
- `sellers`
- `products`
- `category_translation`
- `orders`
- `order_items`
- `order_payments`
- `order_reviews`

Các quan hệ chính:

```text
customers 1 ----- N orders

orders 1 -------- N order_items
orders 1 -------- N order_payments
orders 1 -------- N order_reviews

products 1 ------ N order_items
sellers 1 ------- N order_items
```

Đặc điểm thiết kế:

- Sử dụng InnoDB.
- Xây dựng Primary Key và Foreign Key.
- Tạo chỉ mục cho các cột thường xuyên được sử dụng trong truy vấn.
- Tách dữ liệu thành các bảng nhằm hạn chế dư thừa và đảm bảo tính toàn vẹn tham chiếu.

### 4.2. MongoDB – Mô hình tài liệu

MongoDB sử dụng mô hình document-oriented, trong đó thông tin liên quan đến một đơn hàng được tổ chức trong cùng một document.

Các collections:

- `orders`
- `customers`
- `products`
- `sellers`
- `categories`

Collection `orders` sử dụng mô hình embedding đối với dữ liệu có quan hệ một-nhiều và thường được truy xuất cùng đơn hàng.

Ví dụ cấu trúc document:

```json
{
  "_id": "order_id",
  "customer_id": "customer_id",
  "order_status": "delivered",
  "order_purchase_timestamp": "2017-10-02T10:56:33",
  "items": [
    {
      "order_item_id": 1,
      "product_id": "product_id",
      "seller_id": "seller_id",
      "price": 29.99,
      "freight_value": 8.72
    }
  ],
  "payments": [
    {
      "payment_sequential": 1,
      "payment_type": "credit_card",
      "payment_installments": 2,
      "payment_value": 38.71
    }
  ],
  "reviews": []
}
```

Đặc điểm thiết kế:

- Embedding `items`, `payments`, `reviews` trong document đơn hàng.
- Sử dụng reference đối với `customer_id`, `product_id` và `seller_id`.
- Tạo index trên các trường thường xuyên được truy vấn.
- Giữ lại đơn hàng không có dữ liệu con bằng các mảng rỗng, không loại bỏ dữ liệu trong quá trình ETL.

## 5. Quy trình ETL

Dữ liệu được chuyển từ MySQL sang MongoDB bằng Python.

Các bước chính:

1. Đọc dữ liệu từ MySQL.
2. Nhóm dữ liệu `order_items`, `order_payments`, `order_reviews` theo `order_id`.
3. Xây dựng document đơn hàng với các mảng dữ liệu được embedding.
4. Chuyển đổi kiểu dữ liệu phù hợp với BSON.
5. Ghi dữ liệu vào MongoDB bằng bulk upsert.
6. Tạo các index phục vụ truy vấn.

Một số kiểm tra dữ liệu sau khi import:

| Nội dung | Số lượng |
|---|---:|
| Tổng số đơn hàng | 99.441 |
| Đơn hàng không có sản phẩm | 775 |
| Đơn hàng không có thanh toán | 1 |
| Đơn hàng có nhiều hơn một đánh giá | 547 |

Các trường hợp đặc biệt được giữ lại để đảm bảo dữ liệu giữa hai hệ quản trị có thể đối chiếu.

## 6. Benchmark MySQL và MongoDB

### 6.1. Các workload

Benchmark tập trung vào 5 workload đọc dữ liệu:

| Workload | MySQL | MongoDB |
|---|---|---|
| `order_detail` | Đọc đơn hàng và 3 bảng dữ liệu con qua 4 truy vấn | Đọc một document đơn hàng chứa dữ liệu con |
| `customer_order_history` | Đọc lịch sử đơn hàng và lấy dữ liệu con theo từng batch | Đọc các đơn hàng của khách hàng, dữ liệu con đã embedding |
| `filtered_orders_page` | Lọc theo trạng thái và khoảng thời gian, sắp xếp, giới hạn 100 bản ghi | Thực hiện cùng điều kiện lọc, sắp xếp và giới hạn 100 document |
| `order_count_by_status` | `GROUP BY order_status` | Aggregation với `$group` |
| `sales_by_product` | JOIN `orders` và `order_items`, nhóm theo sản phẩm | `$match`, `$unwind` mảng `items` và `$group` theo sản phẩm |

Hai workload đầu tiên phản ánh cách truy xuất dữ liệu theo mô hình thực tế của mỗi hệ quản trị. Vì vậy, số lượng truy vấn hoặc round-trip giữa hai bên không nhất thiết giống nhau.

### 6.2. Quy trình đo hiệu năng

Trước khi đo:

1. Kiểm tra cấu hình kết nối và ping MongoDB.
2. Đối chiếu số lượng bản ghi giữa MySQL và MongoDB, bao gồm tổng số phần tử trong các mảng được embedding.
3. Chạy thử từng workload trên cả hai hệ quản trị.
4. Chuẩn hóa kết quả và so sánh SHA-256.
5. Chỉ đo hiệu năng khi kết quả giữa hai hệ quản trị khớp nhau.

Trong quá trình đo:

- Thực hiện warm-up trước khi đo.
- Chạy nhiều lần cho mỗi workload.
- Luân phiên thứ tự chạy MySQL và MongoDB.
- Tính các chỉ số latency: median, p95, min, max.
- Ghi nhận số lượng kết quả trả về.
- Lưu kết quả dưới định dạng JSON và CSV.

Các trường dữ liệu tiền tệ được chuẩn hóa về 2 chữ số thập phân trước khi so sánh.

### 6.3. Cách đọc kết quả

Tỷ lệ so sánh được tính theo:

```text
Ratio = MySQL Median Latency / MongoDB Median Latency
```

- `Ratio > 1`: MySQL có median latency cao hơn MongoDB.
- `Ratio < 1`: MySQL có median latency thấp hơn MongoDB.
- `Ratio = 1`: Hai hệ quản trị có median latency bằng nhau.

Không sử dụng kết quả của một workload đơn lẻ để kết luận hệ quản trị nào tốt hơn trong mọi trường hợp.

### 6.4. Lưu ý về benchmark

- Hai hệ quản trị được chạy trên cùng máy và sử dụng cùng bộ dữ liệu.
- Không thực hiện import hoặc ETL trong thời gian đo.
- Kết quả mặc định phản ánh hiệu năng trong điều kiện warm-cache.
- Script không xóa cache của hệ điều hành hoặc hệ quản trị.
- Đây là benchmark ở mức ứng dụng, bao gồm thời gian round-trip và materialization kết quả.
- Không đánh giá concurrent throughput hoặc hiệu năng ghi dữ liệu.
- Workload `sales_by_product` chỉ tính tổng `price`, không bao gồm `freight_value`.
- `result_rows` là số lượng kết quả cấp cao nhất; với truy vấn aggregation, đây là số nhóm được trả về.

## 7. Cấu hình và chạy chương trình

### 7.1. Yêu cầu môi trường

- Python 3.x
- MySQL
- MongoDB
- Các thư viện Python được khai báo trong `requirements.txt`

### 7.2. Cài đặt thư viện

```powershell
python -m venv .venv

.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 7.3. Cấu hình biến môi trường

Tạo file `.env` tại thư mục gốc dự án:

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=your_username
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=ecommerce_olist

MONGO_URI=mongodb://localhost:27017/
MONGO_DATABASE=ecommerce_olist
```

Không commit file `.env` chứa thông tin đăng nhập lên GitHub. Sử dụng `.env.example` để chia sẻ cấu trúc cấu hình.

### 7.4. Chạy benchmark

Đảm bảo MySQL và MongoDB đang hoạt động, dữ liệu đã được import vào cả hai hệ quản trị.

Từ thư mục gốc repository, chạy:

```powershell
.\.venv\Scripts\python.exe .\ecommerce-benchmark\benchmark.py
```

Chạy với số lần lặp tùy chỉnh:

```powershell
.\.venv\Scripts\python.exe .\ecommerce-benchmark\benchmark.py --warmup 3 --iterations 10
```

Tăng số lần đo để có kết quả ổn định hơn:

```powershell
.\.venv\Scripts\python.exe .\ecommerce-benchmark\benchmark.py --warmup 10 --iterations 100
```

Có thể bỏ qua kiểm tra số lượng bản ghi bằng:

```powershell
.\.venv\Scripts\python.exe .\ecommerce-benchmark\benchmark.py --skip-count-check
```

Không khuyến nghị sử dụng tùy chọn này nếu chưa xác định được nguyên nhân dữ liệu không khớp.

### 7.5. Kết quả

Các tệp kết quả benchmark được lưu tại:

```text
ecommerce-benchmark/results/
```

Bao gồm dữ liệu JSON và CSV phục vụ phân tích, so sánh và trực quan hóa kết quả.

## 8. Quản trị dữ liệu không gian

Phần này nghiên cứu các khái niệm và kỹ thuật quản trị dữ liệu không gian, sử dụng dữ liệu geolocation trong bộ dữ liệu Olist làm ngữ cảnh.

Các nội dung chính:

### 8.1. Mô hình dữ liệu không gian

- Vector và Raster.
- Point, LineString, Polygon.
- GeoJSON, WKT và WKB.
- Hệ tọa độ CRS và WGS84.

### 8.2. Chỉ mục không gian

- R-tree.
- Quad-tree.
- Geohash.

### 8.3. Truy vấn không gian

- Range Query.
- k-Nearest Neighbor (kNN).
- Spatial Intersection.
- Distance Query.

### 8.4. Hệ quản trị cơ sở dữ liệu

Nghiên cứu và so sánh khả năng hỗ trợ dữ liệu không gian của:

- PostgreSQL/PostGIS.
- Oracle Spatial.
- MongoDB.
- MySQL Spatial.

## 9. Cấu trúc dự án

```text
HQTCSDL/
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
│
├── data/
│   └── raw/
│
├── mysql/
│   └── schema.sql
│
├── scripts/
│   ├── inspect_dataset.py
│   ├── load_mysql.py
│   └── etl_mysql_to_mongodb.py
│
└── ecommerce-benchmark/
    ├── benchmark.py
    └── results/
```

Cấu trúc trên thể hiện các thành phần chính của dự án; có thể được cập nhật theo cấu trúc thực tế của repository.

## 10. Công nghệ sử dụng

| Công nghệ | Mục đích |
|---|---|
| Python | Xử lý dữ liệu và xây dựng benchmark |
| Pandas | Đọc, xử lý và biến đổi dữ liệu |
| SQLAlchemy | Kết nối và thao tác với MySQL |
| PyMySQL | Driver kết nối MySQL |
| PyMongo | Kết nối và thao tác với MongoDB |
| MySQL | Hệ quản trị cơ sở dữ liệu quan hệ |
| MongoDB | Hệ quản trị cơ sở dữ liệu hướng tài liệu |
| Git | Quản lý mã nguồn |

## 11. Giới hạn của dự án

- Benchmark hiện tại tập trung vào các workload đọc dữ liệu.
- Chưa đánh giá hiệu năng ghi, cập nhật và xóa dữ liệu.
- Chưa đánh giá khả năng xử lý nhiều người dùng đồng thời.
- Kết quả phụ thuộc vào cấu hình phần cứng, bộ nhớ, cache và index.
- Dữ liệu geolocation chưa được đưa vào benchmark MySQL và MongoDB hiện tại.
- Kết quả chỉ phản ánh các workload được xây dựng trong dự án, không đại diện cho mọi tình huống sử dụng cơ sở dữ liệu.

## 12. Nguồn dữ liệu và tham khảo

- [Brazilian E-Commerce Public Dataset by Olist – Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
- [MySQL Documentation](https://dev.mysql.com/doc/)
- [MongoDB Documentation](https://www.mongodb.com/docs/)
- [PostGIS Documentation](https://postgis.net/documentation/)

Dữ liệu Olist được sử dụng theo điều khoản giấy phép đi kèm bộ dữ liệu. Vui lòng kiểm tra và tuân thủ giấy phép khi phân phối hoặc sử dụng lại dữ liệu.

---

**Môn học:** Hệ Quản Trị Cơ Sở Dữ Liệu  
**Chủ đề:** So sánh hiệu năng MySQL và MongoDB & Quản trị dữ liệu không gian
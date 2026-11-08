// Kết nối/Chuyển sang database ecommerce_olist
db = db.getSiblingDB('ecommerce_olist');

// ==========================================
// 1. ĐỊNH NGHĨA SCHEMA VALIDATION (Đã rút gọn)
// ==========================================
const ordersSchema = {
    $jsonSchema: {
        bsonType: "object",
        required: ["_id", "customer_id", "order_status"],
        properties: {
            _id: { bsonType: "string" },
            customer_id: { bsonType: "string" },
            order_status: { bsonType: "string" },
            items: {
                bsonType: ["array", "null"],
                items: {
                    bsonType: "object",
                    required: ["product_id", "seller_id"]
                }
            },
            payments: { bsonType: ["array", "null"] },
            reviews: { bsonType: ["array", "null"] }
        }
    }
};

// ==========================================
// 2. KHỞI TẠO COLLECTION & ÁP DỤNG SCHEMA
// ==========================================
try {
    db.createCollection("orders", { validator: ordersSchema });
    print("  + Đã tạo collection 'orders' với Schema Validation.");
} catch (e) {
    db.runCommand({ collMod: "orders", validator: ordersSchema });
    print("  + Đã cập nhật Schema cho collection 'orders' hiện tại.");
}

const subCollections = ["customers", "products", "sellers", "categories"];
subCollections.forEach(coll => {
    try {
        db.createCollection(coll);
        print(`  + Đã tạo collection '${coll}'`);
    } catch (e) {
        print(`  - Collection '${coll}' đã tồn tại.`);
    }
});

// ==========================================
// 3. THIẾT LẬP INDEX (CHỈ MỤC)
// ==========================================
print("\n[*] Đang tạo Indexes...");

db.orders.createIndex({ "customer_id": 1 });
db.orders.createIndex({ "order_status": 1 });
db.orders.createIndex({ "order_purchase_timestamp": 1 });

db.orders.createIndex({ "items.product_id": 1 });
db.orders.createIndex({ "items.seller_id": 1 });

db.customers.createIndex({ "customer_unique_id": 1 });
db.customers.createIndex({ "customer_zip_code_prefix": 1 });
db.products.createIndex({ "product_category_name": 1 });
db.sellers.createIndex({ "seller_zip_code_prefix": 1 });

print("  + Đã tạo Index thành công.");

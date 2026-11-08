CREATE DATABASE ecommerce_olist
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE ecommerce_olist;

CREATE TABLE customers (
    customer_id CHAR(32) PRIMARY KEY,
    customer_unique_id CHAR(32),
    customer_zip_code_prefix CHAR(5),
    customer_city VARCHAR(100),
    customer_state CHAR(2),

    INDEX idx_customer_unique_id (customer_unique_id)
);

CREATE TABLE sellers (
    seller_id CHAR(32) PRIMARY KEY,
    seller_zip_code_prefix CHAR(5),
    seller_city VARCHAR(100),
    seller_state CHAR(2)
);

CREATE TABLE products (
    product_id CHAR(32) PRIMARY KEY,
    product_category_name VARCHAR(100),
    product_name_length INT,
    product_description_length INT,
    product_photos_qty INT,
    product_weight_g INT,
    product_length_cm INT,
    product_height_cm INT,
    product_width_cm INT
);

CREATE TABLE category_translation (
    product_category_name VARCHAR(100) PRIMARY KEY,
    product_category_name_english VARCHAR(100)
);

CREATE TABLE orders (
    order_id CHAR(32) PRIMARY KEY,
    customer_id CHAR(32) NOT NULL,

    order_status VARCHAR(30),

    order_purchase_timestamp DATETIME,
    order_approved_at DATETIME,
    order_delivered_carrier_date DATETIME,
    order_delivered_customer_date DATETIME,
    order_estimated_delivery_date DATETIME,

    INDEX idx_orders_customer (customer_id),
    INDEX idx_orders_purchase_date (order_purchase_timestamp),
    INDEX idx_orders_status (order_status),

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_id CHAR(32),
    order_item_id INT,

    product_id CHAR(32),
    seller_id CHAR(32),

    shipping_limit_date DATETIME,

    price DECIMAL(12,2),
    freight_value DECIMAL(12,2),

    PRIMARY KEY (order_id, order_item_id),

    INDEX idx_items_product (product_id),
    INDEX idx_items_seller (seller_id),

    FOREIGN KEY (order_id)
        REFERENCES orders(order_id),

    FOREIGN KEY (product_id)
        REFERENCES products(product_id),

    FOREIGN KEY (seller_id)
        REFERENCES sellers(seller_id)
);

CREATE TABLE order_payments (
    order_id CHAR(32),
    payment_sequential INT,

    payment_type VARCHAR(30),
    payment_installments INT,
    payment_value DECIMAL(12,2),

    PRIMARY KEY (order_id, payment_sequential),

    FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
);

CREATE TABLE order_reviews (
    review_row_id BIGINT AUTO_INCREMENT PRIMARY KEY,

    review_id CHAR(32),
    order_id CHAR(32),

    review_score INT,
    review_comment_title TEXT,
    review_comment_message TEXT,

    review_creation_date DATETIME,
    review_answer_timestamp DATETIME,

    INDEX idx_reviews_order (order_id),

    FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
);
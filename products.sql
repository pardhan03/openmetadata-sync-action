-- description: Stores all product inventory records
-- owner: inventory-team@company.com
-- tags: inventory, operations

CREATE TABLE products (
    product_id   INT           NOT NULL,  -- PK: Unique product identifier
    sku          VARCHAR(50)   NOT NULL,  -- Unique SKU code for the product
    name         VARCHAR(200)  NOT NULL,
    description  TEXT,
    price        DECIMAL(10,2) NOT NULL,
    stock_count  INT           DEFAULT 0,
    category_id  INT,                     -- FK: References categories table
    created_at   TIMESTAMP     NOT NULL,
    updated_at   TIMESTAMP
);

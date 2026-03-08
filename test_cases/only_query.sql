-- =====================================================
-- Схема: s_grnplm_vd_rozn_ss_core
-- =====================================================

-- 1. Базовые таблицы
DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_core.t_core_client CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_core.t_core_client (
    epk_id BIGINT PRIMARY KEY,
    client_id VARCHAR(50) NOT NULL,
    full_name VARCHAR(200),
    birth_date DATE,
    region_code VARCHAR(10),
    segment VARCHAR(20),
    client_status VARCHAR(20),
    registration_date DATE,
    last_update TIMESTAMP
);

-- Добавляем CHECK constraint отдельно для совместимости
ALTER TABLE s_grnplm_vd_rozn_ss_core.t_core_client 
ADD CONSTRAINT chk_segment CHECK (segment IN ('MVS', 'VIP', 'PB', 'MASS', 'YOUNG'));

DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_core.t_core_product CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_core.t_core_product (
    product_id INTEGER PRIMARY KEY,
    product_code VARCHAR(50) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    product_category VARCHAR(50),
    product_subcategory VARCHAR(50),
    brand VARCHAR(100),
    supplier_id INTEGER,
    unit_price DECIMAL(15,2),
    vat_rate DECIMAL(5,2),
    is_active BOOLEAN DEFAULT true,
    created_date DATE
);

DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_core.t_core_supplier CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_core.t_core_supplier (
    supplier_id INTEGER PRIMARY KEY,
    supplier_code VARCHAR(50),
    supplier_name VARCHAR(200),
    country VARCHAR(100),
    city VARCHAR(100),
    rating INTEGER,
    contract_date DATE,
    is_premium BOOLEAN
);

-- 2. Представления (с префиксом v_)
DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_core.v_core_client CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_core.v_core_client AS
SELECT 
    epk_id,
    client_id,
    full_name,
    EXTRACT(YEAR FROM age(CURRENT_DATE, birth_date))::INTEGER as age,
    region_code,
    segment,
    client_status,
    registration_date,
    CASE 
        WHEN registration_date < '2020-01-01' THEN 'OLD'
        WHEN registration_date < '2023-01-01' THEN 'REGULAR'
        ELSE 'NEW'
    END as client_tenure,
    last_update
FROM s_grnplm_vd_rozn_ss_core.t_core_client
WHERE client_status != 'CLOSED';

DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_core.v_core_product CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_core.v_core_product AS
SELECT 
    p.product_id,
    p.product_code,
    p.product_name,
    p.product_category,
    p.product_subcategory,
    p.brand,
    s.supplier_name,
    s.country as supplier_country,
    s.rating as supplier_rating,
    p.unit_price,
    p.vat_rate,
    p.unit_price * (1 + p.vat_rate/100) as price_with_vat,
    p.is_active,
    CASE 
        WHEN p.unit_price > 1000 THEN 'HIGH'
        WHEN p.unit_price > 100 THEN 'MEDIUM'
        ELSE 'LOW'
    END as price_category
FROM s_grnplm_vd_rozn_ss_core.t_core_product p
LEFT JOIN s_grnplm_vd_rozn_ss_core.t_core_supplier s 
    ON p.supplier_id = s.supplier_id;

DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_core.v_core_premium_suppliers CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_core.v_core_premium_suppliers AS
SELECT 
    supplier_id,
    supplier_code,
    supplier_name,
    country,
    rating
FROM s_grnplm_vd_rozn_ss_core.t_core_supplier
WHERE rating >= 8 AND is_premium = true;

-- Представление, использующее другое представление
DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_core.v_core_premium_products CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_core.v_core_premium_products AS
SELECT 
    p.product_id,
    p.product_name,
    p.product_category,
    p.brand,
    p.unit_price,
    p.price_with_vat,
    s.supplier_name,
    s.rating
FROM s_grnplm_vd_rozn_ss_core.v_core_product p
JOIN s_grnplm_vd_rozn_ss_core.v_core_premium_suppliers s 
    ON p.supplier_name = s.supplier_name
WHERE p.price_category = 'HIGH';

-- =====================================================
-- Схема: s_grnplm_vd_rozn_ss_stg
-- =====================================================

-- 1. Базовые таблицы
DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_stg.t_stg_sales CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_stg.t_stg_sales (
    transaction_id BIGINT PRIMARY KEY,
    epk_id BIGINT NOT NULL,
    product_id INTEGER NOT NULL,
    store_id INTEGER,
    transaction_date DATE NOT NULL,
    transaction_time TIME,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(15,2) NOT NULL,
    discount_amount DECIMAL(15,2) DEFAULT 0,
    payment_type VARCHAR(20),
    cashier_id INTEGER,
    is_return BOOLEAN DEFAULT false,
    load_date DATE DEFAULT CURRENT_DATE
);

-- В PostgreSQL 9.4 нет GENERATED COLUMNS, создаем обычное поле
ALTER TABLE s_grnplm_vd_rozn_ss_stg.t_stg_sales 
ADD COLUMN total_amount DECIMAL(15,2);

-- Создаем триггер для автоматического расчета total_amount (опционально)
-- Но для тестов можно заполнить вручную

DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_stg.t_stg_store CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_stg.t_stg_store (
    store_id INTEGER PRIMARY KEY,
    store_code VARCHAR(20),
    store_name VARCHAR(200),
    store_type VARCHAR(50),
    region_code VARCHAR(10),
    city VARCHAR(100),
    address TEXT,
    opening_date DATE,
    is_active BOOLEAN
);

DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_stg.t_stg_cashier CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_stg.t_stg_cashier (
    cashier_id INTEGER PRIMARY KEY,
    store_id INTEGER NOT NULL,
    cashier_name VARCHAR(200),
    hire_date DATE,
    position VARCHAR(50),
    is_active BOOLEAN
);

-- 2. Представления (с префиксом v_)
DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_stg.v_stg_sales CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_stg.v_stg_sales AS
SELECT 
    s.transaction_id,
    s.epk_id,
    s.product_id,
    s.store_id,
    s.transaction_date,
    s.transaction_time,
    s.quantity,
    s.unit_price,
    s.discount_amount,
    s.quantity * s.unit_price - s.discount_amount as total_amount,
    s.payment_type,
    s.cashier_id,
    s.is_return,
    st.store_name,
    st.region_code,
    st.city,
    c.cashier_name,
    EXTRACT(DOW FROM s.transaction_date) as day_of_week,
    EXTRACT(MONTH FROM s.transaction_date) as month_num,
    EXTRACT(QUARTER FROM s.transaction_date) as quarter_num
FROM s_grnplm_vd_rozn_ss_stg.t_stg_sales s
LEFT JOIN s_grnplm_vd_rozn_ss_stg.t_stg_store st 
    ON s.store_id = st.store_id
LEFT JOIN s_grnplm_vd_rozn_ss_stg.t_stg_cashier c 
    ON s.cashier_id = c.cashier_id
WHERE s.is_return = false;

DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_stg.v_stg_sales_daily CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_stg.v_stg_sales_daily AS
SELECT 
    transaction_date,
    store_id,
    region_code,
    COUNT(*) as transaction_count,
    COUNT(DISTINCT epk_id) as unique_clients,
    SUM(quantity) as total_quantity,
    SUM(total_amount) as total_sales,
    AVG(total_amount) as avg_transaction_amount
FROM s_grnplm_vd_rozn_ss_stg.v_stg_sales
GROUP BY transaction_date, store_id, region_code;

-- Представление с рекурсивным раскрытием (будет использовать v_stg_sales_daily)
DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_stg.v_stg_sales_monthly CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_stg.v_stg_sales_monthly AS
SELECT 
    DATE_TRUNC('month', transaction_date) as month_start,
    store_id,
    region_code,
    SUM(transaction_count) as total_transactions,
    SUM(unique_clients) as total_unique_clients,
    SUM(total_quantity) as total_quantity,
    SUM(total_sales) as total_sales,
    AVG(avg_transaction_amount) as avg_monthly_amount
FROM s_grnplm_vd_rozn_ss_stg.v_stg_sales_daily
GROUP BY DATE_TRUNC('month', transaction_date), store_id, region_code;

-- Представление для топ-продуктов
DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_stg.v_stg_top_products CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_stg.v_stg_top_products AS
SELECT 
    s.product_id,
    p.product_name,
    p.product_category,
    COUNT(*) as sales_count,
    SUM(s.quantity) as total_quantity,
    SUM(s.total_amount) as total_sales,
    AVG(s.total_amount) as avg_sale_amount,
    RANK() OVER (ORDER BY SUM(s.total_amount) DESC) as sales_rank
FROM s_grnplm_vd_rozn_ss_stg.v_stg_sales s
JOIN s_grnplm_vd_rozn_ss_core.v_core_product p 
    ON s.product_id = p.product_id
WHERE s.transaction_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY s.product_id, p.product_name, p.product_category;

-- Функция для заполнения таблиц тестовыми данными
CREATE OR REPLACE FUNCTION fill_test_data(row_count INTEGER DEFAULT 1000000)
RETURNS void AS $$
DECLARE
    i INTEGER;
BEGIN
    -- Очищаем существующие данные
    TRUNCATE s_grnplm_vd_rozn_ss_core.t_core_client CASCADE;
    TRUNCATE s_grnplm_vd_rozn_ss_core.t_core_product CASCADE;
    TRUNCATE s_grnplm_vd_rozn_ss_core.t_core_supplier CASCADE;
    TRUNCATE s_grnplm_vd_rozn_ss_stg.t_stg_sales CASCADE;
    TRUNCATE s_grnplm_vd_rozn_ss_stg.t_stg_store CASCADE;
    TRUNCATE s_grnplm_vd_rozn_ss_stg.t_stg_cashier CASCADE;
    
    -- Заполняем suppliers (10% от общего количества)
    FOR i IN 1..(row_count/10) LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_core.t_core_supplier VALUES (
            i,
            'SUP' || LPAD(i::TEXT, 10, '0'),
            'Supplier ' || i,
            CASE (i % 10) 
                WHEN 0 THEN 'Россия'
                WHEN 1 THEN 'Китай'
                WHEN 2 THEN 'США'
                WHEN 3 THEN 'Германия'
                ELSE 'Другие'
            END,
            'City ' || (i % 100),
            (i % 10) + 1,
            CURRENT_DATE - (i * 100),
            (i % 5 = 0)
        );
    END LOOP;
    
    -- Заполняем products (20% от общего количества)
    FOR i IN 1..(row_count/5) LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_core.t_core_product VALUES (
            i,
            'PRD' || LPAD(i::TEXT, 10, '0'),
            'Product ' || i,
            CASE (i % 5)
                WHEN 0 THEN 'Электроника'
                WHEN 1 THEN 'Одежда'
                WHEN 2 THEN 'Продукты'
                WHEN 3 THEN 'Книги'
                ELSE 'Другое'
            END,
            'Subcategory ' || (i % 20),
            'Brand ' || (i % 50),
            (i % (row_count/10)) + 1,
            (i % 1000)::DECIMAL + 0.99,
            20.0,
            (i % 10 != 0),
            CURRENT_DATE - (i * 10)
        );
    END LOOP;
    
    -- Заполняем clients
    FOR i IN 1..row_count LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_core.t_core_client VALUES (
            i,
            'CL' || LPAD(i::TEXT, 10, '0'),
            'Client ' || i,
            CURRENT_DATE - (i * 1000),
            'REG' || LPAD((i % 10)::TEXT, 2, '0'),
            CASE (i % 6)
                WHEN 0 THEN 'MVS'
                WHEN 1 THEN 'VIP'
                WHEN 2 THEN 'PB'
                WHEN 3 THEN 'MASS'
                WHEN 4 THEN 'YOUNG'
                ELSE 'MASS'
            END,
            CASE (i % 5)
                WHEN 0 THEN 'ACTIVE'
                WHEN 1 THEN 'ACTIVE'
                WHEN 2 THEN 'ACTIVE'
                WHEN 3 THEN 'SUSPENDED'
                ELSE 'CLOSED'
            END,
            CURRENT_DATE - (i * 30),
            CURRENT_TIMESTAMP
        );
    END LOOP;
    
    -- Заполняем stores (5% от общего количества)
    FOR i IN 1..(row_count/20) LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_stg.t_stg_store VALUES (
            i,
            'STR' || LPAD(i::TEXT, 5, '0'),
            'Store ' || i,
            CASE (i % 3)
                WHEN 0 THEN 'Супермаркет'
                WHEN 1 THEN 'Гипермаркет'
                ELSE 'Минимаркет'
            END,
            'REG' || LPAD((i % 10)::TEXT, 2, '0'),
            'City ' || (i % 50),
            'Address ' || i,
            CURRENT_DATE - (i * 50),
            (i % 10 != 0)
        );
    END LOOP;
    
    -- Заполняем cashiers (10% от общего количества)
    FOR i IN 1..(row_count/10) LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_stg.t_stg_cashier VALUES (
            i,
            (i % (row_count/20)) + 1,
            'Cashier ' || i,
            CURRENT_DATE - (i * 200),
            CASE (i % 3)
                WHEN 0 THEN 'Старший кассир'
                WHEN 1 THEN 'Кассир'
                ELSE 'Стажер'
            END,
            (i % 10 != 0)
        );
    END LOOP;
    
    -- Заполняем sales (основная таблица)
    FOR i IN 1..row_count LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_stg.t_stg_sales (
            transaction_id,
            epk_id,
            product_id,
            store_id,
            transaction_date,
            transaction_time,
            quantity,
            unit_price,
            discount_amount,
            payment_type,
            cashier_id,
            is_return,
            load_date,
            total_amount
        ) VALUES (
            i,
            (i % row_count) + 1,
            (i % (row_count/5)) + 1,
            (i % (row_count/20)) + 1,
            CURRENT_DATE - ((row_count - i) % 365),
            CURRENT_TIME - ((i % 1000) * INTERVAL '1 minute'),
            (i % 5) + 1,
            ((i % 1000)::DECIMAL + 0.99),
            CASE WHEN i % 10 = 0 THEN ((i % 50)::DECIMAL) ELSE 0 END,
            CASE (i % 4)
                WHEN 0 THEN 'CASH'
                WHEN 1 THEN 'CARD'
                WHEN 2 THEN 'ONLINE'
                ELSE 'BONUS'
            END,
            (i % (row_count/10)) + 1,
            (i % 100 = 0),
            CURRENT_DATE,
            ((i % 5) + 1) * (((i % 1000)::DECIMAL + 0.99)) - 
                CASE WHEN i % 10 = 0 THEN ((i % 50)::DECIMAL) ELSE 0 END
        );
    END LOOP;
    
    -- Обновляем статистику
    ANALYZE s_grnplm_vd_rozn_ss_core.t_core_client;
    ANALYZE s_grnplm_vd_rozn_ss_core.t_core_product;
    ANALYZE s_grnplm_vd_rozn_ss_core.t_core_supplier;
    ANALYZE s_grnplm_vd_rozn_ss_stg.t_stg_sales;
    ANALYZE s_grnplm_vd_rozn_ss_stg.t_stg_store;
    ANALYZE s_grnplm_vd_rozn_ss_stg.t_stg_cashier;
    
    RAISE NOTICE 'Тестовые данные успешно загружены: % строк', row_count;
END;
$$ LANGUAGE plpgsql;

-- Заполнить тестовыми данными (например, 1 млн строк)
SELECT fill_test_data(1000000);
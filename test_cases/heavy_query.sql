-- =====================================================
-- ТЕСТ-КЕЙС №2: КРИТИЧЕСКАЯ НАГРУЗКА
-- Все объекты создаются в существующих схемах
-- =====================================================

-- =====================================================
-- Схема: s_grnplm_vd_rozn_ss_core (основные таблицы)
-- =====================================================

-- 1. Таблица клиентов
DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_core.t_core_client CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_core.t_core_client (
    epk_id BIGINT PRIMARY KEY,
    client_id VARCHAR(50) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    middle_name VARCHAR(100),
    birth_date DATE,
    gender CHAR(1),
    region_code VARCHAR(10),
    district_code VARCHAR(10),
    city_code VARCHAR(10),
    segment VARCHAR(20),
    subsegment VARCHAR(20),
    client_status VARCHAR(20),
    registration_date DATE,
    first_purchase_date DATE,
    last_purchase_date DATE,
    total_purchases DECIMAL(15,2),
    avg_check DECIMAL(15,2),
    loyalty_level INTEGER,
    risk_category VARCHAR(20),
    credit_score INTEGER,
    load_date DATE DEFAULT CURRENT_DATE
);

-- 2. Таблица продуктов
DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_core.t_core_product CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_core.t_core_product (
    product_id BIGINT PRIMARY KEY,
    product_code VARCHAR(50) NOT NULL,
    product_name VARCHAR(500) NOT NULL,
    product_category VARCHAR(50),
    product_subcategory VARCHAR(50),
    product_group VARCHAR(50),
    brand_id INTEGER,
    brand_name VARCHAR(200),
    supplier_id INTEGER,
    supplier_name VARCHAR(200),
    unit_price DECIMAL(15,2),
    wholesale_price DECIMAL(15,2),
    vat_rate DECIMAL(5,2),
    weight_kg DECIMAL(10,3),
    volume_m3 DECIMAL(10,3),
    is_perishable BOOLEAN,
    is_imported BOOLEAN,
    country_of_origin VARCHAR(100),
    min_stock_level INTEGER,
    max_stock_level INTEGER,
    current_stock INTEGER,
    created_date DATE,
    is_active BOOLEAN DEFAULT true
);

-- =====================================================
-- Схема: s_grnplm_vd_rozn_ss_stg (таблицы-источники)
-- =====================================================

-- 3. Таблица транзакций
DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_stg.t_stg_transaction CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_stg.t_stg_transaction (
    transaction_id BIGINT PRIMARY KEY,
    epk_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    store_id INTEGER,
    transaction_date DATE NOT NULL,
    transaction_time TIME,
    transaction_hour INTEGER,
    transaction_minute INTEGER,
    transaction_dow INTEGER,
    transaction_month INTEGER,
    transaction_quarter INTEGER,
    transaction_year INTEGER,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(15,2) NOT NULL,
    discount_percent DECIMAL(5,2),
    discount_amount DECIMAL(15,2),
    total_amount DECIMAL(15,2),
    payment_type VARCHAR(20),
    card_type VARCHAR(20),
    is_online BOOLEAN,
    is_mobile BOOLEAN,
    device_type VARCHAR(50),
    browser VARCHAR(50),
    os_type VARCHAR(50),
    ip_address VARCHAR(50),
    geolocation VARCHAR(100),
    cashier_id INTEGER,
    terminal_id INTEGER,
    is_return BOOLEAN DEFAULT false,
    return_reason VARCHAR(200),
    promo_code VARCHAR(50),
    campaign_id INTEGER,
    load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Таблица магазинов
DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_stg.t_stg_store CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_stg.t_stg_store (
    store_id INTEGER PRIMARY KEY,
    store_code VARCHAR(50),
    store_name VARCHAR(200),
    store_type VARCHAR(50),
    region_code VARCHAR(10),
    district_code VARCHAR(10),
    city_code VARCHAR(10),
    address TEXT,
    latitude DECIMAL(10,8),
    longitude DECIMAL(11,8),
    opening_date DATE,
    closing_date DATE,
    square_m2 INTEGER,
    employees_count INTEGER,
    has_parking BOOLEAN,
    has_cafe BOOLEAN,
    has_atm BOOLEAN,
    is_active BOOLEAN
);

-- 5. Таблица кассиров
DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_stg.t_stg_cashier CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_stg.t_stg_cashier (
    cashier_id INTEGER PRIMARY KEY,
    store_id INTEGER NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    hire_date DATE,
    termination_date DATE,
    position VARCHAR(50),
    salary_level INTEGER,
    shift VARCHAR(20),
    efficiency_rating DECIMAL(3,2),
    is_active BOOLEAN
);

-- 6. Таблица промо-кампаний
DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_stg.t_stg_campaign CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_stg.t_stg_campaign (
    campaign_id INTEGER PRIMARY KEY,
    campaign_name VARCHAR(200),
    campaign_type VARCHAR(50),
    start_date DATE,
    end_date DATE,
    discount_percent DECIMAL(5,2),
    min_purchase_amount DECIMAL(15,2),
    target_audience VARCHAR(200),
    budget DECIMAL(15,2),
    actual_cost DECIMAL(15,2),
    expected_roi DECIMAL(5,2),
    actual_roi DECIMAL(5,2)
);

-- 7. Таблица терминалов
DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_stg.t_stg_terminal CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_stg.t_stg_terminal (
    terminal_id INTEGER PRIMARY KEY,
    store_id INTEGER,
    terminal_type VARCHAR(50),
    model VARCHAR(100),
    manufacturer VARCHAR(100),
    installation_date DATE,
    last_maintenance_date DATE,
    software_version VARCHAR(50),
    is_active BOOLEAN
);

-- 8. Таблица возвратов
DROP TABLE IF EXISTS s_grnplm_vd_rozn_ss_stg.t_stg_return CASCADE;
CREATE TABLE s_grnplm_vd_rozn_ss_stg.t_stg_return (
    return_id BIGINT PRIMARY KEY,
    transaction_id BIGINT NOT NULL,
    epk_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    return_date DATE NOT NULL,
    return_reason VARCHAR(200),
    return_amount DECIMAL(15,2),
    refund_method VARCHAR(50),
    processed_by INTEGER,
    quality_check_passed BOOLEAN,
    restocked BOOLEAN
);

-- =====================================================
-- ПРЕДСТАВЛЕНИЯ (с префиксом v_)
-- =====================================================

-- 9. Представление клиентов с вычисляемыми полями
DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_core.v_core_client_full CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_core.v_core_client_full AS
SELECT 
    epk_id,
    client_id,
    first_name || ' ' || last_name as full_name,
    CASE WHEN middle_name IS NOT NULL THEN first_name || ' ' || middle_name || ' ' || last_name ELSE first_name || ' ' || last_name END as full_name_with_patronymic,
    birth_date,
    EXTRACT(YEAR FROM age(CURRENT_DATE, birth_date))::INTEGER as age,
    CASE 
        WHEN EXTRACT(YEAR FROM age(CURRENT_DATE, birth_date)) < 18 THEN 'CHILD'
        WHEN EXTRACT(YEAR FROM age(CURRENT_DATE, birth_date)) BETWEEN 18 AND 25 THEN 'YOUNG'
        WHEN EXTRACT(YEAR FROM age(CURRENT_DATE, birth_date)) BETWEEN 26 AND 35 THEN 'YOUNG_ADULT'
        WHEN EXTRACT(YEAR FROM age(CURRENT_DATE, birth_date)) BETWEEN 36 AND 50 THEN 'ADULT'
        WHEN EXTRACT(YEAR FROM age(CURRENT_DATE, birth_date)) BETWEEN 51 AND 65 THEN 'MIDDLE_AGE'
        ELSE 'SENIOR'
    END as age_group,
    gender,
    region_code,
    district_code,
    city_code,
    segment,
    subsegment,
    client_status,
    registration_date,
    EXTRACT(YEAR FROM registration_date)::INTEGER as reg_year,
    EXTRACT(MONTH FROM registration_date)::INTEGER as reg_month,
    CASE 
        WHEN registration_date < '2020-01-01' THEN 'OLD'
        WHEN registration_date < '2023-01-01' THEN 'REGULAR'
        ELSE 'NEW'
    END as client_tenure,
    first_purchase_date,
    last_purchase_date,
    (CURRENT_DATE - last_purchase_date)::INTEGER as days_since_last_purchase,
    total_purchases,
    avg_check,
    CASE 
        WHEN total_purchases > 1000000 THEN 'PLATINUM'
        WHEN total_purchases > 500000 THEN 'GOLD'
        WHEN total_purchases > 100000 THEN 'SILVER'
        WHEN total_purchases > 10000 THEN 'BRONZE'
        ELSE 'REGULAR'
    END as loyalty_level_name,
    risk_category,
    credit_score,
    CASE 
        WHEN credit_score > 800 THEN 'EXCELLENT'
        WHEN credit_score > 700 THEN 'GOOD'
        WHEN credit_score > 600 THEN 'FAIR'
        ELSE 'POOR'
    END as credit_rating
FROM s_grnplm_vd_rozn_ss_core.t_core_client;

-- 10. Представление продуктов с полной иерархией
DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_core.v_core_product_full CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_core.v_core_product_full AS
SELECT 
    p.product_id,
    p.product_code,
    p.product_name,
    p.product_category,
    p.product_subcategory,
    p.product_group,
    p.brand_id,
    p.brand_name,
    p.supplier_id,
    p.supplier_name,
    p.unit_price,
    p.wholesale_price,
    p.vat_rate,
    p.unit_price * (1 + p.vat_rate/100) as price_with_vat,
    p.unit_price - p.wholesale_price as margin,
    (p.unit_price - p.wholesale_price) / p.unit_price * 100 as margin_percent,
    p.weight_kg,
    p.volume_m3,
    p.is_perishable,
    p.is_imported,
    p.country_of_origin,
    CASE 
        WHEN p.unit_price > 10000 THEN 'LUXURY'
        WHEN p.unit_price > 5000 THEN 'PREMIUM'
        WHEN p.unit_price > 1000 THEN 'HIGH'
        WHEN p.unit_price > 100 THEN 'MEDIUM'
        ELSE 'LOW'
    END as price_category,
    p.min_stock_level,
    p.max_stock_level,
    p.current_stock,
    p.current_stock - p.min_stock_level as stock_above_min,
    p.max_stock_level - p.current_stock as stock_below_max,
    CASE 
        WHEN p.current_stock < p.min_stock_level THEN 'CRITICAL'
        WHEN p.current_stock < p.min_stock_level * 1.2 THEN 'LOW'
        WHEN p.current_stock > p.max_stock_level * 0.8 THEN 'HIGH'
        ELSE 'NORMAL'
    END as stock_status,
    p.created_date,
    p.is_active
FROM s_grnplm_vd_rozn_ss_core.t_core_product p;

-- 11. Представление транзакций с денормализацией (САМОЕ ТЯЖЕЛОЕ)
-- 11. Представление транзакций с денормализацией (ИСПРАВЛЕННАЯ ВЕРСИЯ)
DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_stg.v_stg_transaction_full CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_stg.v_stg_transaction_full AS
SELECT 
    t.transaction_id,
    t.epk_id,
    t.product_id,
    t.store_id,
    t.transaction_date,
    t.transaction_time,
    t.transaction_hour,
    t.transaction_minute,
    t.transaction_dow,
    t.transaction_month,
    t.transaction_quarter,
    t.transaction_year,
    CASE t.transaction_dow
        WHEN 0 THEN 'Sunday'
        WHEN 1 THEN 'Monday'
        WHEN 2 THEN 'Tuesday'
        WHEN 3 THEN 'Wednesday'
        WHEN 4 THEN 'Thursday'
        WHEN 5 THEN 'Friday'
        WHEN 6 THEN 'Saturday'
    END as day_of_week_name,
    t.quantity,
    t.unit_price,
    t.discount_percent,
    t.discount_amount,
    t.total_amount,
    t.payment_type,
    t.card_type,
    t.is_online,
    t.is_mobile,
    t.device_type,
    t.browser,
    t.os_type,
    t.ip_address,
    t.geolocation,
    t.cashier_id,
    t.terminal_id,
    t.is_return,
    t.return_reason,
    t.promo_code,
    t.campaign_id,
    -- Исправлено: используем full_name вместо first_name + last_name
    c.full_name as client_name,
    c.segment as client_segment,
    c.subsegment as client_subsegment,
    c.region_code as client_region,
    c.district_code as client_district,
    c.city_code as client_city,
    c.age_group,
    c.gender,
    c.loyalty_level_name,
    c.credit_rating,
    p.product_name,
    p.product_category,
    p.product_subcategory,
    p.product_group,
    p.brand_name,
    p.supplier_name,
    p.price_category,
    p.is_perishable,
    p.is_imported,
    p.country_of_origin,
    s.store_name,
    s.store_type,
    s.region_code as store_region,
    s.district_code as store_district,
    s.city_code as store_city,
    s.has_parking,
    s.has_cafe,
    s.has_atm,
    cr.first_name || ' ' || cr.last_name as cashier_name,  -- Исправлено: конкатенация
    cr.position as cashier_position,
    cr.efficiency_rating,
    tmn.terminal_type,
    tmn.software_version,
    cmp.campaign_name,
    cmp.campaign_type,
    CASE 
        WHEN t.transaction_date BETWEEN cmp.start_date AND cmp.end_date THEN 'ACTIVE'
        ELSE 'INACTIVE'
    END as campaign_status
FROM s_grnplm_vd_rozn_ss_stg.t_stg_transaction t
LEFT JOIN s_grnplm_vd_rozn_ss_core.v_core_client_full c ON t.epk_id = c.epk_id
LEFT JOIN s_grnplm_vd_rozn_ss_core.v_core_product_full p ON t.product_id = p.product_id
LEFT JOIN s_grnplm_vd_rozn_ss_stg.t_stg_store s ON t.store_id = s.store_id
LEFT JOIN s_grnplm_vd_rozn_ss_stg.t_stg_cashier cr ON t.cashier_id = cr.cashier_id
LEFT JOIN s_grnplm_vd_rozn_ss_stg.t_stg_terminal tmn ON t.terminal_id = tmn.terminal_id
LEFT JOIN s_grnplm_vd_rozn_ss_stg.t_stg_campaign cmp ON t.campaign_id = cmp.campaign_id;

-- 12. Представление для аналитики по часам
-- 12. Представление для аналитики по часам (ИСПРАВЛЕННАЯ ВЕРСИЯ)
DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_stg.v_stg_hourly_stats CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_stg.v_stg_hourly_stats AS
SELECT 
    transaction_date,
    transaction_hour,
    store_id,
    store_region as region_code,  -- Исправлено: store_region вместо region_code
    COUNT(*) as transaction_count,
    COUNT(DISTINCT epk_id) as unique_clients,
    COUNT(DISTINCT product_id) as unique_products,
    SUM(quantity) as total_quantity,
    SUM(total_amount) as total_sales,
    AVG(total_amount) as avg_transaction,
    SUM(CASE WHEN is_online THEN 1 ELSE 0 END) as online_count,
    SUM(CASE WHEN is_online THEN total_amount ELSE 0 END) as online_sales,
    SUM(CASE WHEN payment_type = 'CARD' THEN total_amount ELSE 0 END) as card_sales,
    SUM(CASE WHEN payment_type = 'CASH' THEN total_amount ELSE 0 END) as cash_sales
FROM s_grnplm_vd_rozn_ss_stg.v_stg_transaction_full
GROUP BY transaction_date, transaction_hour, store_id, store_region;

-- 13. Представление для аналитики по клиентам
-- 13. Представление для аналитики по клиентам (ИСПРАВЛЕННАЯ ВЕРСИЯ)
DROP VIEW IF EXISTS s_grnplm_vd_rozn_ss_stg.v_stg_client_stats CASCADE;
CREATE VIEW s_grnplm_vd_rozn_ss_stg.v_stg_client_stats AS
SELECT 
    epk_id,
    client_segment,
    client_region,
    COUNT(*) as total_transactions,
    COUNT(DISTINCT transaction_date) as active_days,
    SUM(total_amount) as lifetime_value,
    AVG(total_amount) as avg_transaction_value,
    MIN(transaction_date) as first_transaction,
    MAX(transaction_date) as last_transaction,
    COUNT(DISTINCT product_category) as categories_purchased,
    COUNT(DISTINCT store_id) as stores_visited,
    SUM(CASE WHEN is_online THEN total_amount ELSE 0 END) as online_lifetime_value,
    SUM(CASE WHEN is_online THEN 1 ELSE 0 END) as online_transactions,
    SUM(CASE WHEN payment_type = 'CARD' THEN total_amount ELSE 0 END) as card_lifetime_value
FROM s_grnplm_vd_rozn_ss_stg.v_stg_transaction_full
GROUP BY epk_id, client_segment, client_region;

-- =====================================================
-- Функция для генерации тестовых данных
-- =====================================================

drop FUNCTION if EXISTS fill_test_data_heavy(row_count INTEGER);
drop FUNCTION if EXISTS s_grnplm_vd_rozn_ss_core.fill_test_data_heavy(row_count INTEGER);
CREATE OR REPLACE FUNCTION s_grnplm_vd_rozn_ss_core.fill_test_data_heavy(row_count INTEGER DEFAULT 1000000)
RETURNS void AS $$
DECLARE
    i INTEGER;
BEGIN
    -- Очищаем существующие данные
    TRUNCATE s_grnplm_vd_rozn_ss_core.t_core_client CASCADE;
    TRUNCATE s_grnplm_vd_rozn_ss_core.t_core_product CASCADE;
    TRUNCATE s_grnplm_vd_rozn_ss_stg.t_stg_transaction CASCADE;
    TRUNCATE s_grnplm_vd_rozn_ss_stg.t_stg_store CASCADE;
    TRUNCATE s_grnplm_vd_rozn_ss_stg.t_stg_cashier CASCADE;
    TRUNCATE s_grnplm_vd_rozn_ss_stg.t_stg_campaign CASCADE;
    TRUNCATE s_grnplm_vd_rozn_ss_stg.t_stg_terminal CASCADE;
    TRUNCATE s_grnplm_vd_rozn_ss_stg.t_stg_return CASCADE;
    
    -- Заполняем stores (1% от количества транзакций)
    FOR i IN 1..(row_count/100) LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_stg.t_stg_store VALUES (
            i,
            'STR' || LPAD(i::TEXT, 10, '0'),
            'Store ' || i,
            CASE (i % 5)
                WHEN 0 THEN 'Mega'
                WHEN 1 THEN 'Super'
                WHEN 2 THEN 'Express'
                WHEN 3 THEN 'Hyper'
                ELSE 'Mini'
            END,
            'REG' || LPAD((i % 20)::TEXT, 2, '0'),
            'DST' || LPAD((i % 50)::TEXT, 2, '0'),
            'CITY' || (i % 100),
            'Address ' || i,
            55.75 + (i % 1000) / 1000.0,
            37.62 + (i % 1000) / 1000.0,
            CURRENT_DATE - (i * 100),
            NULL,
            500 + (i % 1000),
            20 + (i % 50),
            (i % 3 = 0),
            (i % 5 = 0),
            (i % 7 = 0),
            true
        );
    END LOOP;
    
    -- Заполняем cashiers (1% от количества транзакций)
    FOR i IN 1..(row_count/100) LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_stg.t_stg_cashier VALUES (
            i,
            (i % (row_count/100)) + 1,
            'FirstName' || i,
            'LastName' || i,
            CURRENT_DATE - (i * 200),
            NULL,
            CASE (i % 3)
                WHEN 0 THEN 'Senior'
                WHEN 1 THEN 'Junior'
                ELSE 'Trainee'
            END,
            30000 + (i % 50000),
            CASE (i % 3)
                WHEN 0 THEN 'Morning'
                WHEN 1 THEN 'Evening'
                ELSE 'Night'
            END,
            3.5 + (i % 50) / 100.0,
            true
        );
    END LOOP;
    
    -- Заполняем terminals (0.2% от количества транзакций)
    FOR i IN 1..(row_count/500) LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_stg.t_stg_terminal VALUES (
            i,
            (i % (row_count/100)) + 1,
            CASE (i % 4)
                WHEN 0 THEN 'POS'
                WHEN 1 THEN 'ATM'
                WHEN 2 THEN 'SelfService'
                ELSE 'Mobile'
            END,
            'Model ' || (i % 20),
            CASE (i % 3)
                WHEN 0 THEN 'Verifone'
                WHEN 1 THEN 'Ingenico'
                ELSE 'PAX'
            END,
            CURRENT_DATE - (i * 300),
            CURRENT_DATE - (i % 30),
            'v' || (i % 10) || '.' || (i % 5) || '.' || (i % 3),
            true
        );
    END LOOP;
    
    -- Заполняем campaigns (0.5% от количества транзакций)
    FOR i IN 1..(row_count/200) LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_stg.t_stg_campaign VALUES (
            i,
            'Campaign ' || i,
            CASE (i % 5)
                WHEN 0 THEN 'Seasonal'
                WHEN 1 THEN 'Holiday'
                WHEN 2 THEN 'Clearance'
                WHEN 3 THEN 'NewProduct'
                ELSE 'Loyalty'
            END,
            CURRENT_DATE - (i * 10),
            CURRENT_DATE + (i * 10),
            5.0 + (i % 20),
            500 + (i % 500),
            'Segment ' || (i % 10),
            100000 + (i * 1000),
            95000 + (i * 900),
            120.0 + (i % 50),
            115.0 + (i % 45)
        );
    END LOOP;
    
    -- Заполняем products (5% от количества транзакций)
    FOR i IN 1..(row_count/20) LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_core.t_core_product VALUES (
            i,
            'PRD' || LPAD(i::TEXT, 10, '0'),
            'Product ' || i || ' ' || md5(i::TEXT),
            CASE (i % 15)
                WHEN 0 THEN 'Electronics'
                WHEN 1 THEN 'Clothing'
                WHEN 2 THEN 'Food'
                WHEN 3 THEN 'Books'
                WHEN 4 THEN 'Sports'
                WHEN 5 THEN 'Toys'
                WHEN 6 THEN 'Furniture'
                WHEN 7 THEN 'Jewelry'
                WHEN 8 THEN 'Cosmetics'
                WHEN 9 THEN 'Pharmacy'
                WHEN 10 THEN 'Automotive'
                WHEN 11 THEN 'Garden'
                WHEN 12 THEN 'Music'
                WHEN 13 THEN 'Movies'
                ELSE 'Other'
            END,
            'Subcat ' || (i % 100),
            'Group ' || (i % 50),
            i % 1000,
            'Brand ' || (i % 500),
            i % 5000,
            'Supplier ' || (i % 1000),
            (i % 10000)::DECIMAL + 0.99,
            (i % 8000)::DECIMAL + 0.50,
            20.0,
            (i % 100)::DECIMAL / 10,
            (i % 10)::DECIMAL / 100,
            (i % 4 = 0),
            (i % 10 = 0),
            CASE (i % 10)
                WHEN 0 THEN 'China'
                WHEN 1 THEN 'USA'
                WHEN 2 THEN 'Germany'
                WHEN 3 THEN 'Japan'
                WHEN 4 THEN 'Korea'
                ELSE 'Russia'
            END,
            100 + (i % 1000),
            1000 + (i % 5000),
            500 + (i % 2000),
            CURRENT_DATE - (i * 10),
            true
        );
    END LOOP;
    
    -- Заполняем clients (10% от количества транзакций)
    FOR i IN 1..(row_count/10) LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_core.t_core_client VALUES (
            i,
            'CL' || LPAD(i::TEXT, 10, '0'),
            'FirstName' || i,
            'LastName' || i,
            CASE WHEN i % 3 = 0 THEN 'MiddleName' || i ELSE NULL END,
            CURRENT_DATE - (i * 100),
            CASE i % 2 WHEN 0 THEN 'M' ELSE 'F' END,
            'REG' || LPAD((i % 20)::TEXT, 2, '0'),
            'DST' || LPAD((i % 50)::TEXT, 2, '0'),
            'CITY' || (i % 100),
            CASE (i % 6)
                WHEN 0 THEN 'MVS'
                WHEN 1 THEN 'VIP'
                WHEN 2 THEN 'PB'
                WHEN 3 THEN 'MASS'
                WHEN 4 THEN 'YOUNG'
                ELSE 'MASS'
            END,
            CASE (i % 10)
                WHEN 0 THEN 'Premium'
                WHEN 1 THEN 'Standard'
                WHEN 2 THEN 'Economy'
                ELSE 'Regular'
            END,
            CASE (i % 5)
                WHEN 0 THEN 'ACTIVE'
                WHEN 1 THEN 'ACTIVE'
                WHEN 2 THEN 'ACTIVE'
                WHEN 3 THEN 'SUSPENDED'
                ELSE 'CLOSED'
            END,
            CURRENT_DATE - (i * 30),
            CURRENT_DATE - (i * 20),
            CURRENT_DATE - (i * 5),
            (i * 1000)::DECIMAL,
            (i * 100)::DECIMAL,
            i % 10,
            CASE (i % 5)
                WHEN 0 THEN 'LOW'
                WHEN 1 THEN 'MEDIUM'
                WHEN 2 THEN 'HIGH'
                ELSE 'NORMAL'
            END,
            300 + (i % 700)
        );
    END LOOP;
    
    -- Заполняем transactions (ОСНОВНАЯ НАГРУЗКА)
    FOR i IN 1..row_count LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_stg.t_stg_transaction (
            transaction_id,
            epk_id,
            product_id,
            store_id,
            transaction_date,
            transaction_time,
            transaction_hour,
            transaction_minute,
            transaction_dow,
            transaction_month,
            transaction_quarter,
            transaction_year,
            quantity,
            unit_price,
            discount_percent,
            discount_amount,
            total_amount,
            payment_type,
            card_type,
            is_online,
            is_mobile,
            device_type,
            browser,
            os_type,
            ip_address,
            geolocation,
            cashier_id,
            terminal_id,
            is_return,
            return_reason,
            promo_code,
            campaign_id
        ) VALUES (
            i,
            (i % (row_count/10)) + 1,
            (i % (row_count/20)) + 1,
            (i % (row_count/100)) + 1,
            CURRENT_DATE - ((row_count - i) % 365),
            CURRENT_TIME - ((i % 1000) * INTERVAL '1 minute'),
            EXTRACT(HOUR FROM CURRENT_TIME - ((i % 1000) * INTERVAL '1 minute'))::INTEGER,
            EXTRACT(MINUTE FROM CURRENT_TIME - ((i % 1000) * INTERVAL '1 minute'))::INTEGER,
            EXTRACT(DOW FROM CURRENT_DATE - ((row_count - i) % 365))::INTEGER,
            EXTRACT(MONTH FROM CURRENT_DATE - ((row_count - i) % 365))::INTEGER,
            EXTRACT(QUARTER FROM CURRENT_DATE - ((row_count - i) % 365))::INTEGER,
            EXTRACT(YEAR FROM CURRENT_DATE - ((row_count - i) % 365))::INTEGER,
            (i % 10) + 1,
            ((i % 1000)::DECIMAL + 0.99),
            CASE WHEN i % 20 = 0 THEN 10.0 ELSE 0 END,
            CASE WHEN i % 20 = 0 THEN ((i % 1000)::DECIMAL + 0.99) * 0.1 ELSE 0 END,
            ((i % 10) + 1) * ((i % 1000)::DECIMAL + 0.99) * 
                CASE WHEN i % 20 = 0 THEN 0.9 ELSE 1.0 END,
            CASE (i % 4)
                WHEN 0 THEN 'CASH'
                WHEN 1 THEN 'CARD'
                WHEN 2 THEN 'ONLINE'
                ELSE 'BONUS'
            END,
            CASE WHEN i % 4 = 1 THEN 'VISA' WHEN i % 4 = 2 THEN 'MASTERCARD' ELSE NULL END,
            (i % 3 = 0),
            (i % 5 = 0),
            CASE (i % 5)
                WHEN 0 THEN 'Desktop'
                WHEN 1 THEN 'Mobile'
                WHEN 2 THEN 'Tablet'
                ELSE 'Other'
            END,
            CASE (i % 4)
                WHEN 0 THEN 'Chrome'
                WHEN 1 THEN 'Firefox'
                WHEN 2 THEN 'Safari'
                ELSE 'Edge'
            END,
            CASE (i % 3)
                WHEN 0 THEN 'Windows'
                WHEN 1 THEN 'MacOS'
                ELSE 'Linux'
            END,
            '192.168.' || (i % 255) || '.' || (i % 255),
            'POINT(' || (55.75 + (i % 1000) / 1000.0) || ' ' || (37.62 + (i % 1000) / 1000.0) || ')',
            (i % (row_count/100)) + 1,
            (i % (row_count/500)) + 1,
            (i % 100 = 0),
            CASE WHEN i % 100 = 0 THEN 'Defective' ELSE NULL END,
            CASE WHEN i % 50 = 0 THEN 'PROMO' || (i % 10) ELSE NULL END,
            CASE WHEN i % 30 = 0 THEN (i % 100) + 1 ELSE NULL END
        );
        
        IF i % 100000 = 0 THEN
            RAISE NOTICE 'Loaded % transactions', i;
        END IF;
    END LOOP;
    
    -- Заполняем returns (10% от количества транзакций)
    FOR i IN 1..(row_count/10) LOOP
        INSERT INTO s_grnplm_vd_rozn_ss_stg.t_stg_return VALUES (
            i,
            i * 10,
            (i % (row_count/10)) + 1,
            (i % (row_count/20)) + 1,
            CURRENT_DATE - (i * 5),
            CASE (i % 5)
                WHEN 0 THEN 'Defective'
                WHEN 1 THEN 'Wrong size'
                WHEN 2 THEN 'Changed mind'
                WHEN 3 THEN 'Damaged'
                ELSE 'Other'
            END,
            (i % 1000)::DECIMAL + 0.99,
            CASE (i % 3)
                WHEN 0 THEN 'Cash'
                WHEN 1 THEN 'Card'
                ELSE 'Store credit'
            END,
            (i % (row_count/100)) + 1,
            (i % 2 = 0),
            (i % 3 = 0)
        );
    END LOOP;
    
    -- Обновляем статистику
    ANALYZE s_grnplm_vd_rozn_ss_core.t_core_client;
    ANALYZE s_grnplm_vd_rozn_ss_core.t_core_product;
    ANALYZE s_grnplm_vd_rozn_ss_stg.t_stg_transaction;
    ANALYZE s_grnplm_vd_rozn_ss_stg.t_stg_store;
    ANALYZE s_grnplm_vd_rozn_ss_stg.t_stg_cashier;
    ANALYZE s_grnplm_vd_rozn_ss_stg.t_stg_campaign;
    ANALYZE s_grnplm_vd_rozn_ss_stg.t_stg_terminal;
    ANALYZE s_grnplm_vd_rozn_ss_stg.t_stg_return;
    
    RAISE NOTICE 'Test data loaded successfully: % transactions', row_count;
END;
$$ LANGUAGE plpgsql;

select s_grnplm_vd_rozn_ss_core.fill_test_data_heavy();

-- =====================================================
-- КРИТИЧЕСКИЙ ЗАПРОС ДЛЯ ТЕСТИРОВАНИЯ
-- =====================================================
WITH RECURSIVE 
client_metrics AS (
    SELECT 
        epk_id,
        client_segment,
        client_region,
        lifetime_value,
        avg_transaction_value,
        total_transactions,
        active_days,
        RANK() OVER (PARTITION BY client_segment ORDER BY lifetime_value DESC) as rank_in_segment,
        PERCENT_RANK() OVER (ORDER BY lifetime_value) as value_percentile,
        NTILE(10) OVER (ORDER BY lifetime_value) as value_decile
    FROM s_grnplm_vd_rozn_ss_stg.v_stg_client_stats
    WHERE lifetime_value > 0
),
hourly_trends AS (
    SELECT 
        transaction_date,
        transaction_hour,
        store_id,
        region_code,
        total_sales,
        transaction_count,
        unique_clients,
        AVG(total_sales) OVER (PARTITION BY store_id ORDER BY transaction_date, transaction_hour ROWS BETWEEN 23 PRECEDING AND CURRENT ROW) as moving_avg_24h,
        SUM(total_sales) OVER (PARTITION BY store_id, EXTRACT(DOW FROM transaction_date) ORDER BY transaction_date) as cumulative_weekly_sales,
        total_sales::FLOAT / NULLIF(SUM(total_sales) OVER (PARTITION BY transaction_date), 0) as sales_share_of_day
    FROM s_grnplm_vd_rozn_ss_stg.v_stg_hourly_stats
    WHERE transaction_date >= CURRENT_DATE - INTERVAL '90 days'
),
product_ranking AS (
    SELECT 
        product_id,
        product_category,
        product_subcategory,
        brand_name,
        COUNT(*) as sales_count,
        SUM(total_amount) as total_sales,
        AVG(unit_price) as avg_price,
        STDDEV(unit_price) as price_stddev,
        COUNT(DISTINCT epk_id) as unique_buyers,
        SUM(quantity) as total_units,
        RANK() OVER (PARTITION BY product_category ORDER BY SUM(total_amount) DESC) as rank_in_category,
        DENSE_RANK() OVER (ORDER BY SUM(total_amount) DESC) as overall_rank,
        ROW_NUMBER() OVER (PARTITION BY brand_name ORDER BY SUM(total_amount) DESC) as rank_in_brand,
        SUM(SUM(total_amount)) OVER (PARTITION BY product_category) as category_total,
        SUM(total_amount)::FLOAT / NULLIF(SUM(SUM(total_amount)) OVER (PARTITION BY product_category), 0) * 100 as pct_of_category
    FROM s_grnplm_vd_rozn_ss_stg.v_stg_transaction_full
    WHERE transaction_date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY product_id, product_category, product_subcategory, brand_name
),
client_segments_detailed AS (
    SELECT 
        epk_id,
        client_segment,
        lifetime_value,
        total_transactions,
        active_days,
        avg_transaction_value,
        last_transaction,
        client_region,
        CASE 
            WHEN lifetime_value > (SELECT PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY lifetime_value) FROM s_grnplm_vd_rozn_ss_stg.v_stg_client_stats) THEN 'TOP_10'
            WHEN lifetime_value > (SELECT PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY lifetime_value) FROM s_grnplm_vd_rozn_ss_stg.v_stg_client_stats) THEN 'TOP_25'
            WHEN lifetime_value > (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lifetime_value) FROM s_grnplm_vd_rozn_ss_stg.v_stg_client_stats) THEN 'TOP_50'
            ELSE 'BOTTOM_50'
        END as value_segment,
        CASE 
            WHEN active_days > (SELECT PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY active_days) FROM s_grnplm_vd_rozn_ss_stg.v_stg_client_stats) THEN 'FREQUENT'
            WHEN active_days > (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY active_days) FROM s_grnplm_vd_rozn_ss_stg.v_stg_client_stats) THEN 'REGULAR'
            ELSE 'OCCASIONAL'
        END as frequency_segment,
        CASE 
            WHEN avg_transaction_value > (SELECT PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY avg_transaction_value) FROM s_grnplm_vd_rozn_ss_stg.v_stg_client_stats) THEN 'BIG_SPENDER'
            WHEN avg_transaction_value > (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY avg_transaction_value) FROM s_grnplm_vd_rozn_ss_stg.v_stg_client_stats) THEN 'MEDIUM_SPENDER'
            ELSE 'SMALL_SPENDER'
        END as spending_segment
    FROM s_grnplm_vd_rozn_ss_stg.v_stg_client_stats
),
correlation_analysis AS (
    SELECT 
        h.transaction_date,
        h.transaction_hour,
        h.store_id,
        h.total_sales,
        h.transaction_count,
        h.unique_clients,
        h.region_code,
        p.total_sales as product_total_sales,
        p.unique_buyers,
        RANK() OVER (PARTITION BY h.store_id ORDER BY h.total_sales DESC) as store_hour_rank,
        DENSE_RANK() OVER (ORDER BY p.total_sales DESC) as product_global_rank,
        SUM(h.total_sales) OVER (PARTITION BY h.region_code, EXTRACT(DOW FROM h.transaction_date)) as region_dow_total,
        AVG(p.total_sales) OVER (PARTITION BY p.product_category) as avg_category_sales
    FROM hourly_trends h
    CROSS JOIN LATERAL (
        SELECT 
            pr.product_category,
            pr.total_sales,
            pr.unique_buyers
        FROM product_ranking pr
        WHERE pr.rank_in_category <= 5
        ORDER BY pr.total_sales DESC
        LIMIT 3
    ) p
    WHERE h.moving_avg_24h > 10000
),
consolidated_stats AS (
    SELECT 
        'CLIENT' as metric_type,
        client_segment as dimension,
        COUNT(*) as record_count,
        SUM(lifetime_value) as total_value,
        AVG(lifetime_value) as avg_value
    FROM client_metrics
    WHERE rank_in_segment <= 100
    GROUP BY client_segment
    
    UNION ALL
    
    SELECT 
        'PRODUCT' as metric_type,
        product_category as dimension,
        COUNT(*) as record_count,
        SUM(total_sales) as total_value,
        AVG(total_sales) as avg_value
    FROM product_ranking
    WHERE rank_in_category <= 20
    GROUP BY product_category
    
    UNION ALL
    
    SELECT 
        'HOURLY' as metric_type,
        region_code as dimension,
        COUNT(*) as record_count,
        SUM(total_sales) as total_value,
        AVG(total_sales) as avg_value
    FROM hourly_trends
    WHERE moving_avg_24h IS NOT NULL
    GROUP BY region_code
),
sales_hierarchy AS (
    SELECT 
        product_category as level1,
        product_subcategory as level2,
        NULL::VARCHAR as level3,
        SUM(total_sales) as value,
        2 as depth
    FROM product_ranking
    GROUP BY product_category, product_subcategory
    
    UNION ALL
    
    SELECT 
        product_category as level1,
        NULL as level2,
        NULL as level3,
        SUM(total_sales) as value,
        1 as depth
    FROM product_ranking
    GROUP BY product_category
)
SELECT 
    csd.client_segment,
    csd.value_segment,
    csd.frequency_segment,
    csd.spending_segment,
    COUNT(DISTINCT csd.epk_id) as client_count,
    SUM(csd.lifetime_value) as segment_lifetime_value,
    AVG(csd.lifetime_value) as avg_client_value,
    pr.product_category,
    COUNT(DISTINCT pr.product_id) as products_in_category,
    SUM(pr.total_sales) as category_sales,
    AVG(pr.avg_price) as avg_category_price,
    ca.avg_category_sales,
    ca.store_hour_rank,
    sh.value as hierarchy_sales,
    cs.record_count as consolidated_count,
    cs.total_value as consolidated_value,
    RANK() OVER (PARTITION BY csd.client_segment ORDER BY SUM(csd.lifetime_value) DESC) as segment_rank,
    SUM(pr.total_sales) / NULLIF(SUM(SUM(pr.total_sales)) OVER (), 0) * 100 as pct_of_total_sales,
    (SELECT COUNT(*) FROM hourly_trends ht WHERE ht.region_code = csd.client_region) as region_hours_count,
    (SELECT AVG(moving_avg_24h) FROM hourly_trends) as global_moving_avg,
    (SELECT STDDEV(lifetime_value) FROM client_metrics) as lifetime_value_stddev,
    CURRENT_TIMESTAMP as analysis_time,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MAX(csd.last_transaction)))::INTEGER as seconds_since_last_activity
FROM client_segments_detailed csd
JOIN client_metrics cm ON csd.epk_id = cm.epk_id
JOIN s_grnplm_vd_rozn_ss_stg.v_stg_transaction_full t ON csd.epk_id = t.epk_id
JOIN product_ranking pr ON t.product_category = pr.product_category
LEFT JOIN correlation_analysis ca ON t.store_region = ca.region_code  -- Исправлено: store_region вместо region_code
    AND t.transaction_hour = ca.transaction_hour
LEFT JOIN consolidated_stats cs ON csd.client_segment = cs.dimension
LEFT JOIN sales_hierarchy sh ON pr.product_category = sh.level1 
    AND (
        (sh.level2 IS NULL AND sh.depth = 1) OR
        (sh.level2 = pr.product_subcategory AND sh.depth = 2)
    )
WHERE t.transaction_date >= CURRENT_DATE - INTERVAL '90 days'
  AND csd.lifetime_value > (SELECT PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY lifetime_value) FROM client_metrics)
GROUP BY 
    csd.client_segment,
    csd.value_segment,
    csd.frequency_segment,
    csd.spending_segment,
    pr.product_category,
    ca.avg_category_sales,
    ca.store_hour_rank,
    sh.value,
    sh.depth,
    cs.record_count,
    cs.total_value,
    csd.client_region
HAVING SUM(csd.lifetime_value) > 1000000
ORDER BY 
    csd.client_segment,
    segment_rank,
    category_sales DESC
LIMIT 1000;
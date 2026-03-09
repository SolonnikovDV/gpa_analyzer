CREATE OR REPLACE FUNCTION s_grnplm_vd_rozn_ss_core.f_dq_check_sp_fill_pens_gosb_agg(p_date character varying, p_thread_name character varying DEFAULT 'ORIGPENSOPERATIONALAGG'::character varying, p_search_depth character varying DEFAULT '6 month'::character varying, p_threshold_value character varying DEFAULT '{"check_limit": 10}'::character varying)
 RETURNS TABLE(scenario character varying, table_name_ character varying, metric_name character varying, metric_dimension character varying, current_value text, previous_periods_dynamics text, same_period_last_year_dynamics text, dq_status character varying, dq_check_result boolean, details text)
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_report_date DATE;
    v_start_date DATE;
    v_prev_start_date DATE;
    v_prev_end_date DATE;
    v_last_year_start_date DATE;
    v_last_year_end_date DATE;
    v_interval_days INTEGER;
    v_gosb_list TEXT[];
    v_gosb TEXT;
    v_current_unique_epk NUMERIC;
    v_prev_unique_epk NUMERIC;
    v_last_year_unique_epk NUMERIC;
    v_prev_dynamics NUMERIC;
    v_year_dynamics NUMERIC;
    v_has_prev_data BOOLEAN;
    v_has_year_data BOOLEAN;
    v_threshold NUMERIC;
    v_threshold_value_json JSON;
    v_global_alert BOOLEAN := FALSE;
    v_global_warn BOOLEAN := FALSE;
    v_gosb_status VARCHAR;
    v_gosb_result BOOLEAN;
    v_gosb_details TEXT;
    v_alert_reasons TEXT[];
    v_warn_reasons TEXT[];
    v_abs_prev_dynamics NUMERIC;
    v_abs_year_dynamics NUMERIC;
    v_metric_name TEXT;
    v_month_start DATE;
    v_month_end DATE;
    v_temp NUMERIC;
    v_sum_prev NUMERIC;
    v_count_prev INTEGER;
    
    -- Для сбора результатов по ГОСБ
    v_current_json TEXT := '{';
    v_prev_json TEXT := '{';
    v_year_json TEXT := '{';
    v_details_json TEXT := '{';
    v_first BOOLEAN := TRUE;
    
    -- Для определения наличия данных по ГОСБ в previous
    v_gosb_has_prev_data BOOLEAN;
    v_gosb_has_year_data BOOLEAN;
    v_total_prev_months INTEGER;
    v_months_with_data INTEGER;
BEGIN
    -- ===== 1. ОПРЕДЕЛЕНИЕ ОТЧЁТНОГО ПЕРИОДА =====
    IF p_date = '' THEN
        v_report_date := s_grnplm_vd_rozn_ss_core.srv_last_day((current_date - interval '1 month')::date);
    ELSE
        v_report_date := s_grnplm_vd_rozn_ss_core.srv_last_day(p_date::date);
    END IF;
    
    v_start_date := s_grnplm_vd_rozn_ss_core.srv_first_day(v_report_date);
    
    -- ===== 2. ОПРЕДЕЛЕНИЕ ГРАНИЦ СРАВНЕНИЯ =====
    v_prev_start_date := (v_start_date - p_search_depth::INTERVAL)::DATE;
    v_prev_end_date := (v_start_date - 1)::DATE;
    
    v_last_year_start_date := (v_start_date - INTERVAL '1 year')::DATE;
    v_last_year_end_date := (v_report_date - INTERVAL '1 year')::DATE;
    
    v_interval_days := (v_report_date - v_start_date) + 1;
    
    -- ===== 3. ПАРСИНГ ПОРОГА =====
    IF p_threshold_value IS NOT NULL AND p_threshold_value != '' THEN
        BEGIN
            v_threshold_value_json := p_threshold_value::JSON;
            v_threshold := COALESCE((v_threshold_value_json->>'check_limit')::NUMERIC, 10);
        EXCEPTION WHEN OTHERS THEN
            v_threshold_value_json := '{}'::JSON;
            v_threshold := 10;
        END;
    ELSE
        v_threshold_value_json := '{}'::JSON;
        v_threshold := 10;
    END IF;
    
    -- ===== 4. ПОЛУЧЕНИЕ СПИСКА ГОСБ ИЗ ТЕКУЩЕГО ПЕРИОДА =====
    SELECT array_agg(DISTINCT gosb_name)
    INTO v_gosb_list
    FROM s_grnplm_vd_rozn_ss_core.pens_pre_result_gosb
    WHERE gosb_name IS NOT NULL AND gosb_name != ''
      AND report_dt BETWEEN v_start_date AND v_report_date;
    
    RAISE NOTICE '==========================================';
    RAISE NOTICE 'report_date: %', v_report_date;
    RAISE NOTICE 'Период: % - % (дней: %)', v_start_date, v_report_date, v_interval_days;
    RAISE NOTICE 'Предыдущий lookback: % - %', v_prev_start_date, v_prev_end_date;
    RAISE NOTICE 'Прошлый год: % - %', v_last_year_start_date, v_last_year_end_date;
    RAISE NOTICE 'Количество ГОСБ в текущем периоде: %', COALESCE(array_length(v_gosb_list, 1), 0);
    RAISE NOTICE 'Порог: %', v_threshold;
    RAISE NOTICE '==========================================';
    
    -- ===== 5. ЦИКЛ ПО ГОСБ ИЗ ТЕКУЩЕГО ПЕРИОДА =====
    IF v_gosb_list IS NOT NULL THEN
        FOREACH v_gosb IN ARRAY v_gosb_list LOOP
            v_metric_name := 'ГОСБ ' || COALESCE(v_gosb, 'НЕИЗВЕСТНО');
            
            -- ===== ТЕКУЩИЙ ПЕРИОД =====
            EXECUTE format('
                SELECT COUNT(DISTINCT epk_id)
                FROM s_grnplm_vd_rozn_ss_core.pens_pre_result_gosb
                WHERE report_dt BETWEEN $1 AND $2
                AND gosb_name = $3
            ')
            INTO v_current_unique_epk
            USING v_start_date, v_report_date, v_gosb;
            
            v_current_unique_epk := COALESCE(v_current_unique_epk, 0);
            
            -- ===== ПРОВЕРКА НАЛИЧИЯ В PREVIOUS ПЕРИОДЕ (ПОМЕСЯЧНО) =====
            v_sum_prev := 0;
            v_count_prev := 0;
            v_months_with_data := 0;
            v_month_end := date_trunc('month', v_prev_end_date) + INTERVAL '1 month' - INTERVAL '1 day';
            
            WHILE v_month_end >= v_prev_start_date LOOP
                v_month_start := date_trunc('month', v_month_end);
                
                IF v_month_start < v_prev_start_date THEN
                    v_month_start := v_prev_start_date;
                END IF;
                IF v_month_end > v_prev_end_date THEN
                    v_month_end := v_prev_end_date;
                END IF;
                
                EXECUTE format('
                    SELECT COUNT(DISTINCT epk_id)
                    FROM s_grnplm_vd_rozn_ss_core.pens_pre_result_gosb
                    WHERE report_dt BETWEEN $1 AND $2
                    AND gosb_name = $3
                ')
                INTO v_temp
                USING v_month_start, v_month_end, v_gosb;
                
                v_temp := COALESCE(v_temp, 0);
                
                IF v_temp > 0 THEN
                    v_months_with_data := v_months_with_data + 1;
                END IF;
                
                v_sum_prev := v_sum_prev + v_temp;
                v_count_prev := v_count_prev + 1;
                v_month_end := v_month_start - INTERVAL '1 day';
            END LOOP;
            
            -- Данные в previous ЕСТЬ, если хотя бы в одном месяце есть записи
            v_gosb_has_prev_data := (v_months_with_data > 0);
            
            IF v_count_prev > 0 AND v_gosb_has_prev_data THEN
                v_prev_unique_epk := v_sum_prev / v_count_prev;
                v_has_prev_data := true;
            ELSE
                v_prev_unique_epk := 0;
                v_has_prev_data := false;
                v_gosb_has_prev_data := false;
            END IF;
            
            -- ===== ПРОВЕРКА НАЛИЧИЯ В YEAR ПЕРИОДЕ =====
            EXECUTE format('
                SELECT COUNT(DISTINCT epk_id)
                FROM s_grnplm_vd_rozn_ss_core.pens_pre_result_gosb
                WHERE report_dt BETWEEN $1 AND $2
                AND gosb_name = $3
            ')
            INTO v_last_year_unique_epk
            USING v_last_year_start_date, v_last_year_end_date, v_gosb;
            
            v_last_year_unique_epk := COALESCE(v_last_year_unique_epk, 0);
            v_gosb_has_year_data := (v_last_year_unique_epk > 0);
            v_has_year_data := v_gosb_has_year_data;
            
            -- ===== РАСЧЁТ ДИНАМИКИ =====
            IF v_has_prev_data AND v_prev_unique_epk > 0 THEN
                v_prev_dynamics := ROUND(((v_current_unique_epk - v_prev_unique_epk) / v_prev_unique_epk) * 100, 2);
            ELSE
                v_prev_dynamics := NULL;
            END IF;
            
            IF v_has_year_data AND v_last_year_unique_epk > 0 THEN
                v_year_dynamics := ROUND(((v_current_unique_epk - v_last_year_unique_epk) / v_last_year_unique_epk) * 100, 2);
            ELSE
                v_year_dynamics := NULL;
            END IF;
            
            -- ===== ЛОГИКА СТАТУСА ДЛЯ ГОСБ =====
            v_alert_reasons := ARRAY[]::TEXT[];
            v_warn_reasons := ARRAY[]::TEXT[];
            
            -- Проверка previous для данного ГОСБ
            IF v_gosb_has_prev_data THEN
                IF v_prev_dynamics IS NOT NULL THEN
                    v_abs_prev_dynamics := ABS(v_prev_dynamics);
                    IF v_abs_prev_dynamics > v_threshold THEN
                        v_alert_reasons := array_append(v_alert_reasons, 'prev');
                    ELSIF v_abs_prev_dynamics > 0.5 THEN
                        v_warn_reasons := array_append(v_warn_reasons, 'prev');
                    END IF;
                END IF;
            ELSE
                -- Нет данных в previous для этого ГОСБ -> WARN
                v_warn_reasons := array_append(v_warn_reasons, 'prev_missing');
            END IF;
            
            -- Проверка year для данного ГОСБ
            IF v_gosb_has_year_data THEN
                IF v_year_dynamics IS NOT NULL THEN
                    v_abs_year_dynamics := ABS(v_year_dynamics);
                    IF v_abs_year_dynamics > v_threshold THEN
                        v_alert_reasons := array_append(v_alert_reasons, 'year');
                    ELSIF v_abs_year_dynamics > 0.5 THEN
                        v_warn_reasons := array_append(v_warn_reasons, 'year');
                    END IF;
                END IF;
            ELSE
                -- Нет данных в year для этого ГОСБ -> WARN (если есть current)
                IF v_current_unique_epk > 0 THEN
                    v_warn_reasons := array_append(v_warn_reasons, 'year_missing');
                END IF;
            END IF;
            
            -- Статус ГОСБ
            IF array_length(v_alert_reasons, 1) > 0 THEN
                v_gosb_status := 'ALERT';
                v_gosb_result := FALSE;
                v_global_alert := TRUE;
            ELSIF array_length(v_warn_reasons, 1) > 0 THEN
                v_gosb_status := 'WARN';
                v_gosb_result := TRUE;
                v_global_warn := TRUE;
            ELSE
                v_gosb_status := 'INFO';
                v_gosb_result := TRUE;
            END IF;
            
            -- Добавляем в JSON-сборщики
            IF NOT v_first THEN
                v_current_json := v_current_json || ',';
                v_prev_json := v_prev_json || ',';
                v_year_json := v_year_json || ',';
                v_details_json := v_details_json || ',';
            END IF;
            v_first := FALSE;
            
            v_current_json := v_current_json || format('"%s": %s', v_gosb, v_current_unique_epk);
            v_prev_json := v_prev_json || format('"%s": %s', v_gosb, COALESCE(v_prev_dynamics::TEXT, 'null'));
            v_year_json := v_year_json || format('"%s": %s', v_gosb, COALESCE(v_year_dynamics::TEXT, 'null'));
            v_details_json := v_details_json || format('"%s": {"status": "%s", "result": %s, "prev": %s, "year": %s, "prev_data": %s, "year_data": %s}', 
                v_gosb,
                v_gosb_status,
                v_gosb_result,
                COALESCE(v_prev_dynamics::TEXT, 'null'),
                COALESCE(v_year_dynamics::TEXT, 'null'),
                v_gosb_has_prev_data,
                v_gosb_has_year_data
            );
            
        END LOOP;
    END IF;
    
    -- Закрываем JSON
    v_current_json := v_current_json || '}';
    v_prev_json := v_prev_json || '}';
    v_year_json := v_year_json || '}';
    v_details_json := v_details_json || '}';
    
    -- ===== ГЛОБАЛЬНЫЙ СТАТУС =====
    IF v_global_alert THEN
        dq_status := 'ALERT';
        dq_check_result := FALSE;
    ELSIF v_global_warn THEN
        dq_status := 'WARN';
        dq_check_result := TRUE;
    ELSE
        dq_status := 'INFO';
        dq_check_result := TRUE;
    END IF;
    
    -- Формирование выходной строки
    scenario := p_thread_name;
    table_name_ := 'pens_pre_result_gosb';
    metric_name := 'ГОСБ';
    metric_dimension := 'all_gosb';
    current_value := v_current_json;
    previous_periods_dynamics := v_prev_json;
    same_period_last_year_dynamics := v_year_json;
    details := v_details_json;
    
    RETURN NEXT;
END;
$function$

CREATE OR REPLACE FUNCTION s_grnplm_vd_rozn_ss_stg.f_dq_check_ft_payroll_pfr_mpp(p_date_from character varying, p_date_to character varying, p_thread_name character varying DEFAULT 'ORIGPAYROLLPFRMPP'::character varying, p_search_depth character varying DEFAULT '6 month'::character varying, p_threshold_value character varying DEFAULT '{"unique_epk": 10, "total_amount": 10, "epk_changes": 10}'::character varying)
 RETURNS TABLE(scenario character varying, table_name character varying, metric_name character varying, metric_dimension character varying, current_value numeric, previous_periods_dynamics numeric, same_period_last_year_dynamics numeric, dq_status character varying, dq_check_result boolean, details text)
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_date_from DATE;
    v_date_to DATE;
    v_prev_date_from DATE;
    v_prev_date_to DATE;
    v_last_year_date_from DATE;
    v_last_year_date_to DATE;
    v_interval_days INTEGER;
    
    -- Переменные для метрики 1: Количество уникальных ЕПК
    v_current_unique_epk NUMERIC;
    v_prev_unique_epk NUMERIC;
    v_last_year_unique_epk NUMERIC;
    v_prev_dynamics_unique_epk NUMERIC;
    v_year_dynamics_unique_epk NUMERIC;
    v_has_prev_unique_epk BOOLEAN;
    v_has_year_unique_epk BOOLEAN;
    
    -- Переменные для метрики 2: Сумма зачислений
    v_current_total_amount NUMERIC;
    v_prev_total_amount NUMERIC;
    v_last_year_total_amount NUMERIC;
    v_prev_dynamics_total_amount NUMERIC;
    v_year_dynamics_total_amount NUMERIC;
    v_has_prev_total_amount BOOLEAN;
    v_has_year_total_amount BOOLEAN;
    
    -- Переменные для метрики 3: Количество изменений ЕПК относительно счета
    v_current_epk_changes NUMERIC;
    v_prev_epk_changes NUMERIC;
    v_last_year_epk_changes NUMERIC;
    v_prev_dynamics_epk_changes NUMERIC;
    v_year_dynamics_epk_changes NUMERIC;
    v_has_prev_epk_changes BOOLEAN;
    v_has_year_epk_changes BOOLEAN;
    
    -- Переменные для порогов
    v_threshold_unique_epk NUMERIC;
    v_threshold_total_amount NUMERIC;
    v_threshold_epk_changes NUMERIC;
    
    -- Переменные для статуса
    v_status VARCHAR;
    v_result BOOLEAN;
    v_details TEXT;
    v_alert_reasons TEXT[];
    v_warn_reasons TEXT[];
    
    -- Вспомогательные
    v_abs_prev_dynamics NUMERIC;
    v_abs_year_dynamics NUMERIC;
BEGIN
    -- Парсим пороги из JSON
    BEGIN
        v_threshold_unique_epk := COALESCE((p_threshold_value::json->>'unique_epk')::NUMERIC, 10);
        v_threshold_total_amount := COALESCE((p_threshold_value::json->>'total_amount')::NUMERIC, 10);
        v_threshold_epk_changes := COALESCE((p_threshold_value::json->>'epk_changes')::NUMERIC, 10);
    EXCEPTION WHEN OTHERS THEN
        -- Если ошибка парсинга JSON, используем значения по умолчанию
        v_threshold_unique_epk := 10;
        v_threshold_total_amount := 10;
        v_threshold_epk_changes := 10;
        RAISE NOTICE 'Ошибка парсинга порогов из JSON, используются значения по умолчанию: unique_epk=10, total_amount=10, epk_changes=10';
    END;
    
    -- Преобразование входных параметров в даты
    v_date_from := p_date_from::DATE;
    v_date_to := p_date_to::DATE;
    
    -- Вычисляем длительность периода в днях
    v_interval_days := GREATEST((v_date_to - v_date_from)::INTEGER, 0);
    
    -- Расчет дат для сравнения с предыдущим периодом
    v_prev_date_from := v_date_from - p_search_depth::INTERVAL;
    v_prev_date_to := v_prev_date_from + v_interval_days;
    
    -- Расчет дат для сравнения с прошлым годом
    v_last_year_date_from := v_date_from - INTERVAL '1 year';
    v_last_year_date_to := v_last_year_date_from + v_interval_days;
    
    -- Отладочная информация
    RAISE NOTICE '==========================================';
    RAISE NOTICE 'Проверка периода: % - %', v_date_from, v_date_to;
    RAISE NOTICE 'Предыдущий период: % - %', v_prev_date_from, v_prev_date_to;
    RAISE NOTICE 'Прошлый год: % - %', v_last_year_date_from, v_last_year_date_to;
    RAISE NOTICE 'Пороги: unique_epk=%, total_amount=%, epk_changes=%', 
        v_threshold_unique_epk, v_threshold_total_amount, v_threshold_epk_changes;
    RAISE NOTICE '==========================================';
    
    -- МЕТРИКА 1: Количество уникальных ЕПК (epk_id)
    
    -- Текущий период
    SELECT COUNT(DISTINCT epk_id) INTO v_current_unique_epk
    FROM s_grnplm_vd_rozn_ss_core.ft_payroll_pfr_mpp
    WHERE targetday BETWEEN v_date_from AND v_date_to;
    
    -- Предыдущий период
    SELECT COUNT(DISTINCT epk_id) INTO v_prev_unique_epk
    FROM s_grnplm_vd_rozn_ss_core.ft_payroll_pfr_mpp
    WHERE targetday BETWEEN v_prev_date_from AND v_prev_date_to;
    
    -- Прошлый год
    SELECT COUNT(DISTINCT epk_id) INTO v_last_year_unique_epk
    FROM s_grnplm_vd_rozn_ss_core.ft_payroll_pfr_mpp
    WHERE targetday BETWEEN v_last_year_date_from AND v_last_year_date_to;
    
    -- Проверяем наличие данных
    v_has_prev_unique_epk := COALESCE(v_prev_unique_epk, 0) > 0;
    v_has_year_unique_epk := COALESCE(v_last_year_unique_epk, 0) > 0;
    
    -- Рассчитываем динамику к предыдущему периоду
    IF v_has_prev_unique_epk THEN
        v_prev_dynamics_unique_epk := ROUND(
            ((COALESCE(v_current_unique_epk, 0) - v_prev_unique_epk)::NUMERIC / 
             v_prev_unique_epk) * 100, 2);
    ELSE
        v_prev_dynamics_unique_epk := NULL;
    END IF;
    
    -- Рассчитываем динамику к прошлому году
    IF v_has_year_unique_epk THEN
        v_year_dynamics_unique_epk := ROUND(
            ((COALESCE(v_current_unique_epk, 0) - v_last_year_unique_epk)::NUMERIC / 
             v_last_year_unique_epk) * 100, 2);
    ELSE
        v_year_dynamics_unique_epk := NULL;
    END IF;
    
    -- Сбрасываем массивы причин
    v_alert_reasons := ARRAY[]::TEXT[];
    v_warn_reasons := ARRAY[]::TEXT[];
    
    -- Проверяем динамику к предыдущему периоду
    IF v_has_prev_unique_epk THEN
        v_abs_prev_dynamics := ABS(v_prev_dynamics_unique_epk);
        IF v_abs_prev_dynamics > v_threshold_unique_epk THEN
            v_alert_reasons := array_append(v_alert_reasons, 
                'Динамика ЕПК к предыдущему периоду: ' || v_prev_dynamics_unique_epk || 
                '% (порог: ' || v_threshold_unique_epk || '%)');
        ELSIF v_abs_prev_dynamics > 0.5 THEN
            v_warn_reasons := array_append(v_warn_reasons, 
                'Динамика ЕПК к предыдущему периоду: ' || v_prev_dynamics_unique_epk || '%');
        END IF;
    ELSE
        v_warn_reasons := array_append(v_warn_reasons, 
            'Нет данных за предыдущий период для сравнения ЕПК');
    END IF;
    
    -- Проверяем динамику к прошлому году
    IF v_has_year_unique_epk THEN
        v_abs_year_dynamics := ABS(v_year_dynamics_unique_epk);
        IF v_abs_year_dynamics > v_threshold_unique_epk THEN
            v_alert_reasons := array_append(v_alert_reasons, 
                'Динамика ЕПК к прошлому году: ' || v_year_dynamics_unique_epk || 
                '% (порог: ' || v_threshold_unique_epk || '%)');
        ELSIF v_abs_year_dynamics > 0.5 THEN
            v_warn_reasons := array_append(v_warn_reasons, 
                'Динамика ЕПК к прошлому году: ' || v_year_dynamics_unique_epk || '%');
        END IF;
    ELSE
        v_warn_reasons := array_append(v_warn_reasons, 
            'Нет данных за прошлый год для сравнения ЕПК');
    END IF;
    
    -- Определяем общий статус для метрики 1
    IF array_length(v_alert_reasons, 1) > 0 THEN
        v_status := 'ALERT';
        v_result := FALSE;
        v_details := 'Причины ALERT: ' || array_to_string(v_alert_reasons, '; ') || 
                    CASE WHEN array_length(v_warn_reasons, 1) > 0 
                        THEN '; WARN: ' || array_to_string(v_warn_reasons, '; ') 
                        ELSE '' END;
    ELSIF array_length(v_warn_reasons, 1) > 0 THEN
        v_status := 'WARN';
        v_result := TRUE;
        v_details := 'Причины WARN: ' || array_to_string(v_warn_reasons, '; ');
    ELSE
        v_status := 'INFO';
        v_result := TRUE;
        v_details := 'Изменения в пределах нормы (≤0.5%)';
    END IF;
    
    -- Возвращаем результат для метрики 1
    scenario := p_thread_name;
    table_name := 'ft_payroll_pfr_mpp';
    metric_name := 'Количество уникальных ЕПК';
    metric_dimension := 'unique_epk_count';
    current_value := COALESCE(v_current_unique_epk, 0);
    previous_periods_dynamics := COALESCE(v_prev_dynamics_unique_epk, 0);
    same_period_last_year_dynamics := COALESCE(v_year_dynamics_unique_epk, 0);
    dq_status := v_status;
    dq_check_result := v_result;
    details := v_details;
    
    RETURN NEXT;
    
    -- МЕТРИКА 2: Сумма зачислений (amount)
    
    -- Текущий период
    SELECT COALESCE(SUM(amount), 0) INTO v_current_total_amount
    FROM s_grnplm_vd_rozn_ss_core.ft_payroll_pfr_mpp
    WHERE targetday BETWEEN v_date_from AND v_date_to;
    
    -- Предыдущий период
    SELECT COALESCE(SUM(amount), 0) INTO v_prev_total_amount
    FROM s_grnplm_vd_rozn_ss_core.ft_payroll_pfr_mpp
    WHERE targetday BETWEEN v_prev_date_from AND v_prev_date_to;
    
    -- Прошлый год
    SELECT COALESCE(SUM(amount), 0) INTO v_last_year_total_amount
    FROM s_grnplm_vd_rozn_ss_core.ft_payroll_pfr_mpp
    WHERE targetday BETWEEN v_last_year_date_from AND v_last_year_date_to;
    
    -- Проверяем наличие данных
    v_has_prev_total_amount := v_prev_total_amount > 0;
    v_has_year_total_amount := v_last_year_total_amount > 0;
    
    -- Рассчитываем динамику к предыдущему периоду
    IF v_has_prev_total_amount THEN
        v_prev_dynamics_total_amount := ROUND(
            ((v_current_total_amount - v_prev_total_amount) / 
             ABS(v_prev_total_amount)) * 100, 2);
    ELSE
        v_prev_dynamics_total_amount := NULL;
    END IF;
    
    -- Рассчитываем динамику к прошлому году
    IF v_has_year_total_amount THEN
        v_year_dynamics_total_amount := ROUND(
            ((v_current_total_amount - v_last_year_total_amount) / 
             ABS(v_last_year_total_amount)) * 100, 2);
    ELSE
        v_year_dynamics_total_amount := NULL;
    END IF;
    
    -- Сбрасываем массивы причин
    v_alert_reasons := ARRAY[]::TEXT[];
    v_warn_reasons := ARRAY[]::TEXT[];
    
    -- Проверяем динамику к предыдущему периоду
    IF v_has_prev_total_amount THEN
        v_abs_prev_dynamics := ABS(v_prev_dynamics_total_amount);
        IF v_abs_prev_dynamics > v_threshold_total_amount THEN
            v_alert_reasons := array_append(v_alert_reasons, 
                'Динамика суммы к предыдущему периоду: ' || v_prev_dynamics_total_amount || 
                '% (порог: ' || v_threshold_total_amount || '%)');
        ELSIF v_abs_prev_dynamics > 0.5 THEN
            v_warn_reasons := array_append(v_warn_reasons, 
                'Динамика суммы к предыдущему периоду: ' || v_prev_dynamics_total_amount || '%');
        END IF;
    ELSE
        v_warn_reasons := array_append(v_warn_reasons, 
            'Нет данных за предыдущий период для сравнения суммы');
    END IF;
    
    -- Проверяем динамику к прошлому году
    IF v_has_year_total_amount THEN
        v_abs_year_dynamics := ABS(v_year_dynamics_total_amount);
        IF v_abs_year_dynamics > v_threshold_total_amount THEN
            v_alert_reasons := array_append(v_alert_reasons, 
                'Динамика суммы к прошлому году: ' || v_year_dynamics_total_amount || 
                '% (порог: ' || v_threshold_total_amount || '%)');
        ELSIF v_abs_year_dynamics > 0.5 THEN
            v_warn_reasons := array_append(v_warn_reasons, 
                'Динамика суммы к прошлому году: ' || v_year_dynamics_total_amount || '%');
        END IF;
    ELSE
        v_warn_reasons := array_append(v_warn_reasons, 
            'Нет данных за прошлый год для сравнения суммы');
    END IF;
    
    -- Определяем общий статус для метрики 2
    IF array_length(v_alert_reasons, 1) > 0 THEN
        v_status := 'ALERT';
        v_result := FALSE;
        v_details := 'Причины ALERT: ' || array_to_string(v_alert_reasons, '; ') || 
                    CASE WHEN array_length(v_warn_reasons, 1) > 0 
                        THEN '; WARN: ' || array_to_string(v_warn_reasons, '; ') 
                        ELSE '' END;
    ELSIF array_length(v_warn_reasons, 1) > 0 THEN
        v_status := 'WARN';
        v_result := TRUE;
        v_details := 'Причины WARN: ' || array_to_string(v_warn_reasons, '; ');
    ELSE
        v_status := 'INFO';
        v_result := TRUE;
        v_details := 'Изменения в пределах нормы (≤0.5%)';
    END IF;
    
    -- Возвращаем результат для метрики 2
    scenario := p_thread_name;
    table_name := 'ft_payroll_pfr_mpp';
    metric_name := 'Сумма зачислений';
    metric_dimension := 'total_amount';
    current_value := v_current_total_amount;
    previous_periods_dynamics := COALESCE(v_prev_dynamics_total_amount, 0);
    same_period_last_year_dynamics := COALESCE(v_year_dynamics_total_amount, 0);
    dq_status := v_status;
    dq_check_result := v_result;
    details := v_details;
    
    RETURN NEXT;
    
    -- МЕТРИКА 3: Количество изменений ЕПК относительно одного счета зачисления
    
    -- Текущий период: account с более чем одним уникальным epk_id
    WITH account_epk_counts AS (
        SELECT account, COUNT(DISTINCT epk_id) as epk_count
        FROM s_grnplm_vd_rozn_ss_core.ft_payroll_pfr_mpp
        WHERE targetday BETWEEN v_date_from AND v_date_to
        GROUP BY account
    )
    SELECT COALESCE(COUNT(*), 0) INTO v_current_epk_changes
    FROM account_epk_counts 
    WHERE epk_count > 1;
    
    -- Предыдущий период
    WITH account_epk_counts AS (
        SELECT account, COUNT(DISTINCT epk_id) as epk_count
        FROM s_grnplm_vd_rozn_ss_core.ft_payroll_pfr_mpp
        WHERE targetday BETWEEN v_prev_date_from AND v_prev_date_to
        GROUP BY account
    )
    SELECT COALESCE(COUNT(*), 0) INTO v_prev_epk_changes
    FROM account_epk_counts 
    WHERE epk_count > 1;
    
    -- Прошлый год
    WITH account_epk_counts AS (
        SELECT account, COUNT(DISTINCT epk_id) as epk_count
        FROM s_grnplm_vd_rozn_ss_core.ft_payroll_pfr_mpp
        WHERE targetday BETWEEN v_last_year_date_from AND v_last_year_date_to
        GROUP BY account
    )
    SELECT COALESCE(COUNT(*), 0) INTO v_last_year_epk_changes
    FROM account_epk_counts 
    WHERE epk_count > 1;
    
    -- Проверяем наличие данных
    v_has_prev_epk_changes := v_prev_epk_changes > 0;
    v_has_year_epk_changes := v_last_year_epk_changes > 0;
    
    -- Рассчитываем динамику к предыдущему периоду
    IF v_has_prev_epk_changes THEN
        v_prev_dynamics_epk_changes := ROUND(
            ((v_current_epk_changes - v_prev_epk_changes)::NUMERIC / 
             v_prev_epk_changes) * 100, 2);
    ELSE
        v_prev_dynamics_epk_changes := NULL;
    END IF;
    
    -- Рассчитываем динамику к прошлому году
    IF v_has_year_epk_changes THEN
        v_year_dynamics_epk_changes := ROUND(
            ((v_current_epk_changes - v_last_year_epk_changes)::NUMERIC / 
             v_last_year_epk_changes) * 100, 2);
    ELSE
        v_year_dynamics_epk_changes := NULL;
    END IF;
    
    -- Сбрасываем массивы причин
    v_alert_reasons := ARRAY[]::TEXT[];
    v_warn_reasons := ARRAY[]::TEXT[];
    
    -- Проверяем динамику к предыдущему периоду
    IF v_has_prev_epk_changes THEN
        v_abs_prev_dynamics := ABS(v_prev_dynamics_epk_changes);
        IF v_abs_prev_dynamics > v_threshold_epk_changes THEN
            v_alert_reasons := array_append(v_alert_reasons, 
                'Динамика изменений ЕПК на счете к предыдущему периоду: ' || 
                v_prev_dynamics_epk_changes || '% (порог: ' || v_threshold_epk_changes || '%)');
        ELSIF v_abs_prev_dynamics > 0.5 THEN
            v_warn_reasons := array_append(v_warn_reasons, 
                'Динамика изменений ЕПК на счете к предыдущему периоду: ' || 
                v_prev_dynamics_epk_changes || '%');
        END IF;
    ELSE
        IF v_current_epk_changes > 0 THEN
            v_warn_reasons := array_append(v_warn_reasons, 
                'Появились новые счета с несколькими ЕПК (предыдущий период: 0)');
        END IF;
    END IF;
    
    -- Проверяем динамику к прошлому году
    IF v_has_year_epk_changes THEN
        v_abs_year_dynamics := ABS(v_year_dynamics_epk_changes);
        IF v_abs_year_dynamics > v_threshold_epk_changes THEN
            v_alert_reasons := array_append(v_alert_reasons, 
                'Динамика изменений ЕПК на счете к прошлому году: ' || 
                v_year_dynamics_epk_changes || '% (порог: ' || v_threshold_epk_changes || '%)');
        ELSIF v_abs_year_dynamics > 0.5 THEN
            v_warn_reasons := array_append(v_warn_reasons, 
                'Динамика изменений ЕПК на счете к прошлому году: ' || 
                v_year_dynamics_epk_changes || '%');
        END IF;
    ELSE
        IF v_current_epk_changes > 0 AND v_last_year_epk_changes = 0 THEN
            v_warn_reasons := array_append(v_warn_reasons, 
                'Появились счета с несколькими ЕПК (прошлый год: 0)');
        END IF;
    END IF;
    
    -- Если нет изменений вообще
    IF v_current_epk_changes = 0 AND v_prev_epk_changes = 0 AND v_last_year_epk_changes = 0 THEN
        v_details := 'Нет счетов с несколькими ЕПК';
    END IF;
    
    -- Определяем общий статус для метрики 3
    IF array_length(v_alert_reasons, 1) > 0 THEN
        v_status := 'ALERT';
        v_result := FALSE;
        v_details := 'Причины ALERT: ' || array_to_string(v_alert_reasons, '; ') || 
                    CASE WHEN array_length(v_warn_reasons, 1) > 0 
                        THEN '; WARN: ' || array_to_string(v_warn_reasons, '; ') 
                        ELSE '' END;
    ELSIF array_length(v_warn_reasons, 1) > 0 THEN
        v_status := 'WARN';
        v_result := TRUE;
        v_details := 'Причины WARN: ' || array_to_string(v_warn_reasons, '; ');
    ELSE
        v_status := 'INFO';
        v_result := TRUE;
        v_details := CASE 
            WHEN v_current_epk_changes = 0 THEN 'Нет счетов с несколькими ЕПК'
            ELSE 'Изменения в пределах нормы (≤0.5%)'
        END;
    END IF;
    
    -- Возвращаем результат для метрики 3
    scenario := p_thread_name;
    table_name := 'ft_payroll_pfr_mpp';
    metric_name := 'Количество изменений ЕПК относительно счета';
    metric_dimension := 'epk_changes_per_account';
    current_value := v_current_epk_changes;
    previous_periods_dynamics := COALESCE(v_prev_dynamics_epk_changes, 0);
    same_period_last_year_dynamics := COALESCE(v_year_dynamics_epk_changes, 0);
    dq_status := v_status;
    dq_check_result := v_result;
    details := v_details;
    
    RETURN NEXT;
    
    -- Итоговая отладочная информация
    RAISE NOTICE 'МЕТРИКА 1 - Уникальные ЕПК: текущий=%, предыдущий=%, прошлый_год=%', 
        v_current_unique_epk, v_prev_unique_epk, v_last_year_unique_epk;
    RAISE NOTICE 'МЕТРИКА 2 - Сумма зачислений: текущий=%, предыдущий=%, прошлый_год=%', 
        v_current_total_amount, v_prev_total_amount, v_last_year_total_amount;
    RAISE NOTICE 'МЕТРИКА 3 - Изменения ЕПК на счете: текущий=%, предыдущий=%, прошлый_год=%', 
        v_current_epk_changes, v_prev_epk_changes, v_last_year_epk_changes;
    
END;
$function$

CREATE OR REPLACE FUNCTION s_grnplm_vd_rozn_ss_core.f_calc_dm_aum_client(p_hist_depth text, p_run_dt text, p_hist_reload_months integer, p_reload_start_date text)
 RETURNS boolean
 LANGUAGE plpgsql
AS $function$
declare
    l_log s_grnplm_vd_rozn_ss_core.tp_log_instance;
    proc varchar := 'f_calc_dm_aum_client';
    v_hist_start date;
    v_run_dt date;
    v_prev_run_dt date;
    v_prev_two_month_end_eom date;
    v_prev_month_start date;
    v_curr_month_start date;
    v_next_month_start date;
    v_reload_start date;
    v_buf_min_dt date;
    v_buf_max_dt date;
    v_min_mart_dt date;
    v_cnt_month_ins bigint := 0;
    v_cnt_day_ins bigint := 0;
    v_cnt_total_ins bigint := 0;
    v_cnt_month_total bigint := 0;
    v_cnt_day_total bigint := 0;
    v_segment_change_date date := '2026-03-01'::date; -- Дата смены сегментации
begin
    -- Инициализация лога
    l_log := s_grnplm_vd_rozn_ss_core.srv_create_log(
            proc,
            coalesce(
                    s_grnplm_vd_rozn_ss_core.srv_get_parameter_value('prep_hashtag', 'run_id')::bigint,
                    nextval('s_grnplm_vd_rozn_ss_core.sq_procedure_run_id'::regclass)::bigint
                )::bigint
        );
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION START] Старт f_calc_dm_aum_client (p_hist_depth: %s, p_run_dt: %s, p_hist_reload_months: %s, p_reload_start_date: %s)',
        p_hist_depth, p_run_dt, p_hist_reload_months, p_reload_start_date),
        'INFO'
    );
    -- Преобразование p_hist_depth в date
    begin
        if p_hist_depth is null or p_hist_depth = '' then
            v_hist_start := '2024-01-01'::date;
        else
            v_hist_start := p_hist_depth::date;
        end if;
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION PREP 0.1] Успешное преобразование p_hist_depth в v_hist_start: %s', v_hist_start),
            'INFO'
        );
    exception when others then
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION PREP 0.1] ERROR преобразования p_hist_depth: %s - %s (значение: %s)', sqlstate, sqlerrm, p_hist_depth),
            'ERROR'
        );
        return false;
    end;
    -- Преобразование p_run_dt в date
    begin
        if p_run_dt is null or p_run_dt = '' then
            v_run_dt := current_date;
        elsif lower(p_run_dt) = 'current_date' then
            v_run_dt := current_date;
        else
            v_run_dt := p_run_dt::date;
        end if;
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION PREP 0.2] Успешное преобразование p_run_dt в v_run_dt: %s', v_run_dt),
            'INFO'
        );
    exception when others then
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION PREP 0.2] ERROR преобразования p_run_dt: %s - %s (значение: %s)', sqlstate, sqlerrm, p_run_dt),
            'ERROR'
        );
        return false;
    end;
    v_prev_run_dt := (v_run_dt - interval '1 day')::date;
    v_prev_two_month_end_eom := (date_trunc('month', v_run_dt - interval '2 months') + interval '1 month' - interval '1 day')::date;
    v_prev_month_start := date_trunc('month', v_run_dt - interval '1 month')::date;
    v_curr_month_start := date_trunc('month', v_run_dt)::date;
    v_next_month_start := date_trunc('month', v_run_dt + interval '1 month')::date;
    -- Определение v_reload_start
    begin
        if p_reload_start_date is not null and p_reload_start_date <> '' then
            v_reload_start := date_trunc('month', p_reload_start_date::date)::date;
        else
            v_reload_start := date_trunc('month', v_run_dt - (interval '1 month') * p_hist_reload_months)::date;
        end if;
        if v_reload_start < v_hist_start then
            v_reload_start := v_hist_start;
        end if;
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION PREP 0.3] v_reload_start определена: %s', v_reload_start),
            'INFO'
        );
    exception when others then
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION PREP 0.3] ERROR преобразования p_reload_start_date: %s - %s (значение: %s)', sqlstate, sqlerrm, p_reload_start_date),
            'ERROR'
        );
        return false;
    end;
    -- 1. TRUNCATE буфер
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        '[SECTION 1] TRUNCATE буфер dm_aum_client_daily_buf',
        'INFO'
    );
    truncate s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf;
    -- 2. Загрузка месячных данных в буфер
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 2] Загрузка месячных данных от %s до %s', v_reload_start, v_prev_two_month_end_eom),
        'INFO'
    );
    -- Вставка месячных данных с использованием LATERAL для правильного поиска сегментации
    insert into s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf
    (report_dt, product, epk_id, chan, segment_cx, segment_dt, dvalue, src)
    select
        (date_trunc('month', m.dtoptndate::date) + interval '1 month' - interval '1 day')::date as report_dt,
        case
            when m.sdzoid = 'Сбер' then 'PASS_BALANCE'
            when m.sdzoid = 'НПФ' then 'PENS_NPF_BALANCE'
            when m.sdzoid = 'УКП' and m.sdicproductname in ('ИИС','Доверительное управление - розничные клиенты')
                then 'UKP_DU_IIS_BALANCE'
            when m.sdzoid = 'УКП' and m.sdicproductname not in ('ИИС','Доверительное управление - розничные клиенты')
                then 'UKP_PIF_BALANCE'
            when m.sdzoid = 'УЭР' then 'PAO_BROKERIDGE_BALANCE'
            when m.sdzoid = 'СФН' then 'SFN_ZPIF_BALANCE'
            when m.sdzoid = 'СБСЖ' then 'SBSZH_BALANCE'
            when m.sdzoid = 'АО' then 'AO_BROKERIDGE_BALANCE'
        end as product,
        m.nclienttid::bigint as epk_id,
        ft.seg_service_channel_cd as chan,
        -- Логика выбора сегмента на основе даты сегментации
        case
            when ft.report_dt < v_segment_change_date then
                -- Для сегментации до даты смены используем CX
                case
                    when ft.seg_client_cx_segment_cd = 'MVS' then 'MVS'
                    when ft.seg_client_cx_segment_cd = 'TOP_AFFL' then 'VIP'
                    when ft.seg_client_cx_segment_cd = 'PB' then 'PB'
                    when ft.seg_client_cx_segment_cd in ('TEEN','KIDS') then 'Дети и подростки'
                    when ft.seg_client_cx_segment_cd in ('YOUTH','PREADULT') then 'Молодежь'
                    when ft.seg_client_cx_segment_cd = 'GROWN_UP' then 'Становление'
                    when ft.seg_client_cx_segment_cd = 'PRIME_AGE' then 'Расцвет'
                    when ft.seg_client_cx_segment_cd = 'SENIOR' then 'Зрелость'
                    else NULL
                end
            else
                -- Для сегментации после/включая дату смены используем FT
                case
                    when ft.seg_client_ft_segment_cd = 'MVS' then 'MVS'
                    when ft.seg_client_ft_segment_cd = 'TOP_AFFL' then 'VIP'
                    when ft.seg_client_ft_segment_cd = 'PB' then 'PB'
                    when ft.seg_client_ft_segment_cd in ('TEEN','KIDS') then 'Дети и подростки'
                    when ft.seg_client_ft_segment_cd in ('YOUTH','PREADULT') then 'Молодежь'
                    when ft.seg_client_ft_segment_cd = 'GROWN_UP' then 'Становление'
                    when ft.seg_client_ft_segment_cd = 'PRIME_AGE' then 'Расцвет'
                    when ft.seg_client_ft_segment_cd = 'SENIOR' then 'Зрелость'
                    else NULL
                end
        end as segment_cx,
        ft.report_dt as segment_dt,
        sum(m.dvaluerur)::numeric(38,8) as dvalue,
        'M'::varchar
    from s_grnplm_vd_rozn_ss_stg.v_stg_t_netto_incom_outcom_m m
    left join lateral (
        select
            ft.epk_id,
            ft.seg_service_channel_cd,
            ft.seg_client_cx_segment_cd,
            ft.seg_client_ft_segment_cd,
            ft.report_dt
        from s_grnplm_vd_rozn_ss_stg.v_stg_ft_client_aggr_mnth ft
        where ft.epk_id = m.nclienttid
          and (
              -- Для исторических дат берем сегментацию до даты смены
              ((date_trunc('month', m.dtoptndate::date) + interval '1 month' - interval '1 day')::date < v_segment_change_date
               and ft.report_dt <= v_segment_change_date - interval '1 day')
              or
              -- Для дат после смены берем сегментацию на дату операции
              ((date_trunc('month', m.dtoptndate::date) + interval '1 month' - interval '1 day')::date >= v_segment_change_date
               and ft.report_dt <= (date_trunc('month', m.dtoptndate::date) + interval '1 month' - interval '1 day')::date)
          )
        order by ft.report_dt desc
        limit 1
    ) ft on true
    where m.dtoptndate::date between v_reload_start and v_prev_two_month_end_eom
      and (
          -- Проверяем наличие соответствующей сегментации
          ((date_trunc('month', m.dtoptndate::date) + interval '1 month' - interval '1 day')::date < v_segment_change_date
           and ft.seg_client_cx_segment_cd is not null)
          or
          ((date_trunc('month', m.dtoptndate::date) + interval '1 month' - interval '1 day')::date >= v_segment_change_date
           and ft.seg_client_ft_segment_cd is not null)
      )
    group by 1,2,3,4,5,6;
    get diagnostics v_cnt_month_ins := row_count;
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 2.1] Вставлено месячных записей: %s за период от %s до %s', v_cnt_month_ins, v_reload_start, v_prev_two_month_end_eom),
        'INFO'
    );
    -- 3. Загрузка дневных данных в буфер
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 3] Загрузка дневных данных от %s до %s', v_prev_month_start, v_prev_run_dt),
        'INFO'
    );
    -- Вставка дневных данных с использованием LATERAL
    insert into s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf
    (report_dt, product, epk_id, chan, segment_cx, segment_dt, dvalue, src)
    select
        d.dtoptndate::date as report_dt,
        case
            when d.sdzoid = 'Сбер' then 'PASS_BALANCE'
            when d.sdzoid = 'НПФ' then 'PENS_NPF_BALANCE'
            when d.sdzoid = 'УКП' and d.sdicproductname in ('ИИС','Доверительное управление - розничные клиенты')
                then 'UKP_DU_IIS_BALANCE'
            when d.sdzoid = 'УКП' and d.sdicproductname not in ('ИИС','Доверительное управление - розничные клиенты')
               then 'UKP_PIF_BALANCE'
            when d.sdzoid = 'УЭР' then 'PAO_BROKERIDGE_BALANCE'
            when d.sdzoid = 'СФН' then 'SFN_ZPIF_BALANCE'
            when d.sdzoid = 'СБСЖ' then 'SBSZH_BALANCE'
            when d.sdzoid = 'АО' then 'AO_BROKERIDGE_BALANCE'
        end as product,
        d.nclienttid::bigint as epk_id,
        ft.seg_service_channel_cd as chan,
        -- Логика выбора сегмента на основе даты сегментации
        case
            when ft.report_dt < v_segment_change_date then
                -- Для сегментации до даты смены используем CX
                case
                    when ft.seg_client_cx_segment_cd = 'MVS' then 'MVS'
                    when ft.seg_client_cx_segment_cd = 'TOP_AFFL' then 'VIP'
                    when ft.seg_client_cx_segment_cd = 'PB' then 'PB'
                    when ft.seg_client_cx_segment_cd in ('TEEN','KIDS') then 'Дети и подростки'
                    when ft.seg_client_cx_segment_cd in ('YOUTH','PREADULT') then 'Молодежь'
                    when ft.seg_client_cx_segment_cd = 'GROWN_UP' then 'Становление'
                    when ft.seg_client_cx_segment_cd = 'PRIME_AGE' then 'Расцвет'
                    when ft.seg_client_cx_segment_cd = 'SENIOR' then 'Зрелость'
                    else NULL
                end
            else
                -- Для сегментации после/включая дату смены используем FT
                case
                    when ft.seg_client_ft_segment_cd = 'MVS' then 'MVS'
                    when ft.seg_client_ft_segment_cd = 'TOP_AFFL' then 'VIP'
                    when ft.seg_client_ft_segment_cd = 'PB' then 'PB'
                    when ft.seg_client_ft_segment_cd in ('TEEN','KIDS') then 'Дети и подростки'
                    when ft.seg_client_ft_segment_cd in ('YOUTH','PREADULT') then 'Молодежь'
                    when ft.seg_client_ft_segment_cd = 'GROWN_UP' then 'Становление'
                    when ft.seg_client_ft_segment_cd = 'PRIME_AGE' then 'Расцвет'
                    when ft.seg_client_ft_segment_cd = 'SENIOR' then 'Зрелость'
                    else NULL
                end
        end as segment_cx,
        ft.report_dt as segment_dt,
        sum(d.dvaluerur)::numeric(38,8) as dvalue,
        'D'::varchar
    from s_grnplm_vd_rozn_ss_stg.v_stg_t_netto_incom_outcom d
    left join lateral (
        select
            ft.epk_id,
            ft.seg_service_channel_cd,
            ft.seg_client_cx_segment_cd,
            ft.seg_client_ft_segment_cd,
            ft.report_dt
        from s_grnplm_vd_rozn_ss_stg.v_stg_ft_client_aggr_mnth ft
        where ft.epk_id = d.nclienttid
          and (
              -- Для исторических дат берем сегментацию до даты смены
              (d.dtoptndate::date < v_segment_change_date
               and ft.report_dt <= v_segment_change_date - interval '1 day')
              or
              -- Для дат после смены берем сегментацию на дату операции
              (d.dtoptndate::date >= v_segment_change_date
               and ft.report_dt <= d.dtoptndate::date)
          )
        order by ft.report_dt desc
        limit 1
    ) ft on true
    where d.dtoptndate::date between v_prev_month_start and v_prev_run_dt
      and (
          -- Проверяем наличие соответствующей сегментации
          (d.dtoptndate::date < v_segment_change_date and ft.seg_client_cx_segment_cd is not null)
          or
          (d.dtoptndate::date >= v_segment_change_date and ft.seg_client_ft_segment_cd is not null)
      )
    group by 1,2,3,4,5,6;
    get diagnostics v_cnt_day_ins := row_count;
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 3.1] Вставлено дневных записей: %s за период от %s до %s', v_cnt_day_ins, v_prev_month_start, v_prev_run_dt),
        'INFO'
    );
    -- 4. Получить min/max из буфера + проверка на пустой буфер
    select min(report_dt), max(report_dt) into v_buf_min_dt, v_buf_max_dt
    from s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf;
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 4] Буфер: min_dt=%s, max_dt=%s, месячных=%s, дневных=%s',
               coalesce(v_buf_min_dt::text, 'NULL'), coalesce(v_buf_max_dt::text, 'NULL'),
               v_cnt_month_ins, v_cnt_day_ins),
        'INFO'
    );
    if v_buf_min_dt is null or v_buf_max_dt is null or v_cnt_month_ins + v_cnt_day_ins = 0 then
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION 4] ПРЕДУПРЕЖДЕНИЕ: Буфер пуст (min=%s, max=%s, total=%s). Завершение без загрузки.',
                   coalesce(v_buf_min_dt::text, 'NULL'), coalesce(v_buf_max_dt::text, 'NULL'),
                   v_cnt_month_ins + v_cnt_day_ins),
            'WARN'
        );
        truncate s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf;
        return true;
    end if;
    -- 5. Очистка данных в итоговой таблице dm_aum_client по диапазону из буфера (DELETE)
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 5] Очистка данных из dm_aum_client по диапазону от %s до %s', v_buf_min_dt, v_buf_max_dt),
        'INFO'
    );
    execute format('delete from s_grnplm_vd_rozn_ss_core.dm_aum_client where report_dt between %L and %L;', v_buf_min_dt, v_buf_max_dt);
    -- 6. Перегрузка из буфера в итоговую таблицу
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        '[SECTION 6] Перегрузка из буфера dm_aum_client_daily_buf в итоговую таблицу dm_aum_client',
        'INFO'
    );
    insert into s_grnplm_vd_rozn_ss_core.dm_aum_client
    (report_dt, product, epk_id, chan, segment_cx, segment_dt, dvalue, load_ts)
    select report_dt, product, epk_id, chan, segment_cx, segment_dt, dvalue, now()
    from s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf;
    get diagnostics v_cnt_total_ins := row_count;
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 6.1] Вставлено всего записей: %s за период от %s до %s', v_cnt_total_ins, v_buf_min_dt, v_buf_max_dt),
        'INFO'
    );
    -- 7. Очистка буфера
    truncate s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf;
    -- 8. Подсчет общего количества данных в итоговой таблице
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        '[SECTION 7] Подсчет общего количества данных в итоговой таблице dm_aum_client',
        'INFO'
    );
    select count(*) into v_cnt_month_total
    from s_grnplm_vd_rozn_ss_core.dm_aum_client
    where report_dt <= v_prev_two_month_end_eom
      and report_dt = (date_trunc('month', report_dt) + interval '1 month' - interval '1 day')::date;
    select count(*) into v_cnt_day_total
    from s_grnplm_vd_rozn_ss_core.dm_aum_client
    where report_dt >= v_prev_month_start
      and report_dt <= v_run_dt
      and report_dt <> (date_trunc('month', report_dt) + interval '1 month' - interval '1 day')::date;
    select min(report_dt) into v_min_mart_dt from s_grnplm_vd_rozn_ss_core.dm_aum_client;
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 7.1] Общее количество месячных строк: %s (от %s до %s)', v_cnt_month_total, v_min_mart_dt, v_prev_two_month_end_eom),
        'INFO'
    );
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 7.2] Общее количество дневных строк: %s (от %s до %s)', v_cnt_day_total, v_prev_month_start, v_run_dt),
        'INFO'
    );
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 7.3] Итого строк в итоговой таблице: %s (от %s до %s)', v_cnt_day_total + v_cnt_month_total, v_min_mart_dt, v_run_dt),
        'INFO'
    );
    analyze s_grnplm_vd_rozn_ss_core.dm_aum_client;
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        '[SECTION FINAL] SUCCESS: f_calc_dm_aum_client завершен успешно',
        'SUCCESS'
    );
    l_log := s_grnplm_vd_rozn_ss_core.srv_save_log(l_log);
    return true;
exception when others then
    l_log:=s_grnplm_vd_rozn_ss_core.srv_add_log_error(
        l_log, SQLSTATE, SQLERRM
    );
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('ERROR: %s, %s', SQLSTATE, SQLERRM),
        'ERROR'
    );
    l_log := s_grnplm_vd_rozn_ss_core.srv_save_log(l_log);
    truncate s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf;
    return false;
end;
$function$
CREATE OR REPLACE FUNCTION s_grnplm_vd_rozn_ss_core.f_calc_dm_aum_client(p_hist_depth text, p_run_dt text, p_hist_reload_months integer, p_reload_start_date text)
 RETURNS boolean
 LANGUAGE plpgsql
AS $function$
declare
    l_log s_grnplm_vd_rozn_ss_core.tp_log_instance;
    proc varchar := 'f_calc_dm_aum_client';
    v_hist_start date;
    v_run_dt date;
    v_prev_run_dt date;
    v_prev_two_month_end_eom date;
    v_prev_month_start date;
    v_curr_month_start date;
    v_next_month_start date;
    v_reload_start date;
    v_buf_min_dt date;
    v_buf_max_dt date;
    v_min_mart_dt date;
    v_cnt_month_ins bigint := 0;
    v_cnt_day_ins bigint := 0;
    v_cnt_total_ins bigint := 0;
    v_cnt_month_total bigint := 0;
    v_cnt_day_total bigint := 0;
    v_segment_change_date date := '2026-03-01'::date; -- Дата смены сегментации
begin
    -- Инициализация лога
    l_log := s_grnplm_vd_rozn_ss_core.srv_create_log(
            proc,
            coalesce(
                    s_grnplm_vd_rozn_ss_core.srv_get_parameter_value('prep_hashtag', 'run_id')::bigint,
                    nextval('s_grnplm_vd_rozn_ss_core.sq_procedure_run_id'::regclass)::bigint
                )::bigint
        );
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION START] Старт f_calc_dm_aum_client (p_hist_depth: %s, p_run_dt: %s, p_hist_reload_months: %s, p_reload_start_date: %s)',
        p_hist_depth, p_run_dt, p_hist_reload_months, p_reload_start_date),
        'INFO'
    );
    -- Преобразование p_hist_depth в date
    begin
        if p_hist_depth is null or p_hist_depth = '' then
            v_hist_start := '2024-01-01'::date;
        else
            v_hist_start := p_hist_depth::date;
        end if;
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION PREP 0.1] Успешное преобразование p_hist_depth в v_hist_start: %s', v_hist_start),
            'INFO'
        );
    exception when others then
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION PREP 0.1] ERROR преобразования p_hist_depth: %s - %s (значение: %s)', sqlstate, sqlerrm, p_hist_depth),
            'ERROR'
        );
        return false;
    end;
    -- Преобразование p_run_dt в date
    begin
        if p_run_dt is null or p_run_dt = '' then
            v_run_dt := current_date;
        elsif lower(p_run_dt) = 'current_date' then
            v_run_dt := current_date;
        else
            v_run_dt := p_run_dt::date;
        end if;
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION PREP 0.2] Успешное преобразование p_run_dt в v_run_dt: %s', v_run_dt),
            'INFO'
        );
    exception when others then
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION PREP 0.2] ERROR преобразования p_run_dt: %s - %s (значение: %s)', sqlstate, sqlerrm, p_run_dt),
            'ERROR'
        );
        return false;
    end;
    v_prev_run_dt := (v_run_dt - interval '1 day')::date;
    v_prev_two_month_end_eom := (date_trunc('month', v_run_dt - interval '2 months') + interval '1 month' - interval '1 day')::date;
    v_prev_month_start := date_trunc('month', v_run_dt - interval '1 month')::date;
    v_curr_month_start := date_trunc('month', v_run_dt)::date;
    v_next_month_start := date_trunc('month', v_run_dt + interval '1 month')::date;
    -- Определение v_reload_start
    begin
        if p_reload_start_date is not null and p_reload_start_date <> '' then
            v_reload_start := date_trunc('month', p_reload_start_date::date)::date;
        else
            v_reload_start := date_trunc('month', v_run_dt - (interval '1 month') * p_hist_reload_months)::date;
        end if;
        if v_reload_start < v_hist_start then
            v_reload_start := v_hist_start;
        end if;
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION PREP 0.3] v_reload_start определена: %s', v_reload_start),
            'INFO'
        );
    exception when others then
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION PREP 0.3] ERROR преобразования p_reload_start_date: %s - %s (значение: %s)', sqlstate, sqlerrm, p_reload_start_date),
            'ERROR'
        );
        return false;
    end;
    -- 1. TRUNCATE буфер
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        '[SECTION 1] TRUNCATE буфер dm_aum_client_daily_buf',
        'INFO'
    );
    truncate s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf;
    -- 2. Загрузка месячных данных в буфер
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 2] Загрузка месячных данных от %s до %s', v_reload_start, v_prev_two_month_end_eom),
        'INFO'
    );
    -- Вставка месячных данных с использованием LATERAL для правильного поиска сегментации
    insert into s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf
    (report_dt, product, epk_id, chan, segment_cx, segment_dt, dvalue, src)
    select
        (date_trunc('month', m.dtoptndate::date) + interval '1 month' - interval '1 day')::date as report_dt,
        case
            when m.sdzoid = 'Сбер' then 'PASS_BALANCE'
            when m.sdzoid = 'НПФ' then 'PENS_NPF_BALANCE'
            when m.sdzoid = 'УКП' and m.sdicproductname in ('ИИС','Доверительное управление - розничные клиенты')
                then 'UKP_DU_IIS_BALANCE'
            when m.sdzoid = 'УКП' and m.sdicproductname not in ('ИИС','Доверительное управление - розничные клиенты')
                then 'UKP_PIF_BALANCE'
            when m.sdzoid = 'УЭР' then 'PAO_BROKERIDGE_BALANCE'
            when m.sdzoid = 'СФН' then 'SFN_ZPIF_BALANCE'
            when m.sdzoid = 'СБСЖ' then 'SBSZH_BALANCE'
            when m.sdzoid = 'АО' then 'AO_BROKERIDGE_BALANCE'
        end as product,
        m.nclienttid::bigint as epk_id,
        ft.seg_service_channel_cd as chan,
        -- Логика выбора сегмента на основе даты сегментации
        case
            when ft.report_dt < v_segment_change_date then
                -- Для сегментации до даты смены используем CX
                case
                    when ft.seg_client_cx_segment_cd = 'MVS' then 'MVS'
                    when ft.seg_client_cx_segment_cd = 'TOP_AFFL' then 'VIP'
                    when ft.seg_client_cx_segment_cd = 'PB' then 'PB'
                    when ft.seg_client_cx_segment_cd in ('TEEN','KIDS') then 'Дети и подростки'
                    when ft.seg_client_cx_segment_cd in ('YOUTH','PREADULT') then 'Молодежь'
                    when ft.seg_client_cx_segment_cd = 'GROWN_UP' then 'Становление'
                    when ft.seg_client_cx_segment_cd = 'PRIME_AGE' then 'Расцвет'
                    when ft.seg_client_cx_segment_cd = 'SENIOR' then 'Зрелость'
                    else NULL
                end
            else
                -- Для сегментации после/включая дату смены используем FT
                case
                    when ft.seg_client_ft_segment_cd = 'MVS' then 'MVS'
                    when ft.seg_client_ft_segment_cd = 'TOP_AFFL' then 'VIP'
                    when ft.seg_client_ft_segment_cd = 'PB' then 'PB'
                    when ft.seg_client_ft_segment_cd in ('TEEN','KIDS') then 'Дети и подростки'
                    when ft.seg_client_ft_segment_cd in ('YOUTH','PREADULT') then 'Молодежь'
                    when ft.seg_client_ft_segment_cd = 'GROWN_UP' then 'Становление'
                    when ft.seg_client_ft_segment_cd = 'PRIME_AGE' then 'Расцвет'
                    when ft.seg_client_ft_segment_cd = 'SENIOR' then 'Зрелость'
                    else NULL
                end
        end as segment_cx,
        ft.report_dt as segment_dt,
        sum(m.dvaluerur)::numeric(38,8) as dvalue,
        'M'::varchar
    from s_grnplm_vd_rozn_ss_stg.v_stg_t_netto_incom_outcom_m m
    left join lateral (
        select
            ft.epk_id,
            ft.seg_service_channel_cd,
            ft.seg_client_cx_segment_cd,
            ft.seg_client_ft_segment_cd,
            ft.report_dt
        from s_grnplm_vd_rozn_ss_stg.v_stg_ft_client_aggr_mnth ft
        where ft.epk_id = m.nclienttid
          and (
              -- Для исторических дат берем сегментацию до даты смены
              ((date_trunc('month', m.dtoptndate::date) + interval '1 month' - interval '1 day')::date < v_segment_change_date
               and ft.report_dt <= v_segment_change_date - interval '1 day')
              or
              -- Для дат после смены берем сегментацию на дату операции
              ((date_trunc('month', m.dtoptndate::date) + interval '1 month' - interval '1 day')::date >= v_segment_change_date
               and ft.report_dt <= (date_trunc('month', m.dtoptndate::date) + interval '1 month' - interval '1 day')::date)
          )
        order by ft.report_dt desc
        limit 1
    ) ft on true
    where m.dtoptndate::date between v_reload_start and v_prev_two_month_end_eom
      and (
          -- Проверяем наличие соответствующей сегментации
          ((date_trunc('month', m.dtoptndate::date) + interval '1 month' - interval '1 day')::date < v_segment_change_date
           and ft.seg_client_cx_segment_cd is not null)
          or
          ((date_trunc('month', m.dtoptndate::date) + interval '1 month' - interval '1 day')::date >= v_segment_change_date
           and ft.seg_client_ft_segment_cd is not null)
      )
    group by 1,2,3,4,5,6;
    get diagnostics v_cnt_month_ins := row_count;
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 2.1] Вставлено месячных записей: %s за период от %s до %s', v_cnt_month_ins, v_reload_start, v_prev_two_month_end_eom),
        'INFO'
    );
    -- 3. Загрузка дневных данных в буфер
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 3] Загрузка дневных данных от %s до %s', v_prev_month_start, v_prev_run_dt),
        'INFO'
    );
    -- Вставка дневных данных с использованием LATERAL
    insert into s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf
    (report_dt, product, epk_id, chan, segment_cx, segment_dt, dvalue, src)
    select
        d.dtoptndate::date as report_dt,
        case
            when d.sdzoid = 'Сбер' then 'PASS_BALANCE'
            when d.sdzoid = 'НПФ' then 'PENS_NPF_BALANCE'
            when d.sdzoid = 'УКП' and d.sdicproductname in ('ИИС','Доверительное управление - розничные клиенты')
                then 'UKP_DU_IIS_BALANCE'
            when d.sdzoid = 'УКП' and d.sdicproductname not in ('ИИС','Доверительное управление - розничные клиенты')
               then 'UKP_PIF_BALANCE'
            when d.sdzoid = 'УЭР' then 'PAO_BROKERIDGE_BALANCE'
            when d.sdzoid = 'СФН' then 'SFN_ZPIF_BALANCE'
            when d.sdzoid = 'СБСЖ' then 'SBSZH_BALANCE'
            when d.sdzoid = 'АО' then 'AO_BROKERIDGE_BALANCE'
        end as product,
        d.nclienttid::bigint as epk_id,
        ft.seg_service_channel_cd as chan,
        -- Логика выбора сегмента на основе даты сегментации
        case
            when ft.report_dt < v_segment_change_date then
                -- Для сегментации до даты смены используем CX
                case
                    when ft.seg_client_cx_segment_cd = 'MVS' then 'MVS'
                    when ft.seg_client_cx_segment_cd = 'TOP_AFFL' then 'VIP'
                    when ft.seg_client_cx_segment_cd = 'PB' then 'PB'
                    when ft.seg_client_cx_segment_cd in ('TEEN','KIDS') then 'Дети и подростки'
                    when ft.seg_client_cx_segment_cd in ('YOUTH','PREADULT') then 'Молодежь'
                    when ft.seg_client_cx_segment_cd = 'GROWN_UP' then 'Становление'
                    when ft.seg_client_cx_segment_cd = 'PRIME_AGE' then 'Расцвет'
                    when ft.seg_client_cx_segment_cd = 'SENIOR' then 'Зрелость'
                    else NULL
                end
            else
                -- Для сегментации после/включая дату смены используем FT
                case
                    when ft.seg_client_ft_segment_cd = 'MVS' then 'MVS'
                    when ft.seg_client_ft_segment_cd = 'TOP_AFFL' then 'VIP'
                    when ft.seg_client_ft_segment_cd = 'PB' then 'PB'
                    when ft.seg_client_ft_segment_cd in ('TEEN','KIDS') then 'Дети и подростки'
                    when ft.seg_client_ft_segment_cd in ('YOUTH','PREADULT') then 'Молодежь'
                    when ft.seg_client_ft_segment_cd = 'GROWN_UP' then 'Становление'
                    when ft.seg_client_ft_segment_cd = 'PRIME_AGE' then 'Расцвет'
                    when ft.seg_client_ft_segment_cd = 'SENIOR' then 'Зрелость'
                    else NULL
                end
        end as segment_cx,
        ft.report_dt as segment_dt,
        sum(d.dvaluerur)::numeric(38,8) as dvalue,
        'D'::varchar
    from s_grnplm_vd_rozn_ss_stg.v_stg_t_netto_incom_outcom d
    left join lateral (
        select
            ft.epk_id,
            ft.seg_service_channel_cd,
            ft.seg_client_cx_segment_cd,
            ft.seg_client_ft_segment_cd,
            ft.report_dt
        from s_grnplm_vd_rozn_ss_stg.v_stg_ft_client_aggr_mnth ft
        where ft.epk_id = d.nclienttid
          and (
              -- Для исторических дат берем сегментацию до даты смены
              (d.dtoptndate::date < v_segment_change_date
               and ft.report_dt <= v_segment_change_date - interval '1 day')
              or
              -- Для дат после смены берем сегментацию на дату операции
              (d.dtoptndate::date >= v_segment_change_date
               and ft.report_dt <= d.dtoptndate::date)
          )
        order by ft.report_dt desc
        limit 1
    ) ft on true
    where d.dtoptndate::date between v_prev_month_start and v_prev_run_dt
      and (
          -- Проверяем наличие соответствующей сегментации
          (d.dtoptndate::date < v_segment_change_date and ft.seg_client_cx_segment_cd is not null)
          or
          (d.dtoptndate::date >= v_segment_change_date and ft.seg_client_ft_segment_cd is not null)
      )
    group by 1,2,3,4,5,6;
    get diagnostics v_cnt_day_ins := row_count;
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 3.1] Вставлено дневных записей: %s за период от %s до %s', v_cnt_day_ins, v_prev_month_start, v_prev_run_dt),
        'INFO'
    );
    -- 4. Получить min/max из буфера + проверка на пустой буфер
    select min(report_dt), max(report_dt) into v_buf_min_dt, v_buf_max_dt
    from s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf;
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 4] Буфер: min_dt=%s, max_dt=%s, месячных=%s, дневных=%s',
               coalesce(v_buf_min_dt::text, 'NULL'), coalesce(v_buf_max_dt::text, 'NULL'),
               v_cnt_month_ins, v_cnt_day_ins),
        'INFO'
    );
    if v_buf_min_dt is null or v_buf_max_dt is null or v_cnt_month_ins + v_cnt_day_ins = 0 then
        l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
            l_log,
            format('[SECTION 4] ПРЕДУПРЕЖДЕНИЕ: Буфер пуст (min=%s, max=%s, total=%s). Завершение без загрузки.',
                   coalesce(v_buf_min_dt::text, 'NULL'), coalesce(v_buf_max_dt::text, 'NULL'),
                   v_cnt_month_ins + v_cnt_day_ins),
            'WARN'
        );
        truncate s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf;
        return true;
    end if;
    -- 5. Очистка данных в итоговой таблице dm_aum_client по диапазону из буфера (DELETE)
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 5] Очистка данных из dm_aum_client по диапазону от %s до %s', v_buf_min_dt, v_buf_max_dt),
        'INFO'
    );
    execute format('delete from s_grnplm_vd_rozn_ss_core.dm_aum_client where report_dt between %L and %L;', v_buf_min_dt, v_buf_max_dt);
    -- 6. Перегрузка из буфера в итоговую таблицу
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        '[SECTION 6] Перегрузка из буфера dm_aum_client_daily_buf в итоговую таблицу dm_aum_client',
        'INFO'
    );
    insert into s_grnplm_vd_rozn_ss_core.dm_aum_client
    (report_dt, product, epk_id, chan, segment_cx, segment_dt, dvalue, load_ts)
    select report_dt, product, epk_id, chan, segment_cx, segment_dt, dvalue, now()
    from s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf;
    get diagnostics v_cnt_total_ins := row_count;
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 6.1] Вставлено всего записей: %s за период от %s до %s', v_cnt_total_ins, v_buf_min_dt, v_buf_max_dt),
        'INFO'
    );
    -- 7. Очистка буфера
    truncate s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf;
    -- 8. Подсчет общего количества данных в итоговой таблице
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        '[SECTION 7] Подсчет общего количества данных в итоговой таблице dm_aum_client',
        'INFO'
    );
    select count(*) into v_cnt_month_total
    from s_grnplm_vd_rozn_ss_core.dm_aum_client
    where report_dt <= v_prev_two_month_end_eom
      and report_dt = (date_trunc('month', report_dt) + interval '1 month' - interval '1 day')::date;
    select count(*) into v_cnt_day_total
    from s_grnplm_vd_rozn_ss_core.dm_aum_client
    where report_dt >= v_prev_month_start
      and report_dt <= v_run_dt
      and report_dt <> (date_trunc('month', report_dt) + interval '1 month' - interval '1 day')::date;
    select min(report_dt) into v_min_mart_dt from s_grnplm_vd_rozn_ss_core.dm_aum_client;
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 7.1] Общее количество месячных строк: %s (от %s до %s)', v_cnt_month_total, v_min_mart_dt, v_prev_two_month_end_eom),
        'INFO'
    );
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 7.2] Общее количество дневных строк: %s (от %s до %s)', v_cnt_day_total, v_prev_month_start, v_run_dt),
        'INFO'
    );
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('[SECTION 7.3] Итого строк в итоговой таблице: %s (от %s до %s)', v_cnt_day_total + v_cnt_month_total, v_min_mart_dt, v_run_dt),
        'INFO'
    );
    analyze s_grnplm_vd_rozn_ss_core.dm_aum_client;
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        '[SECTION FINAL] SUCCESS: f_calc_dm_aum_client завершен успешно',
        'SUCCESS'
    );
    l_log := s_grnplm_vd_rozn_ss_core.srv_save_log(l_log);
    return true;
exception when others then
    l_log:=s_grnplm_vd_rozn_ss_core.srv_add_log_error(
        l_log, SQLSTATE, SQLERRM
    );
    l_log := s_grnplm_vd_rozn_ss_core.srv_add_log_entry(
        l_log,
        format('ERROR: %s, %s', SQLSTATE, SQLERRM),
        'ERROR'
    );
    l_log := s_grnplm_vd_rozn_ss_core.srv_save_log(l_log);
    truncate s_grnplm_vd_rozn_ss_core.dm_aum_client_daily_buf;
    return false;
end;
$function$

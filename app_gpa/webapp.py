#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import io
import json
import threading
import queue
from contextlib import redirect_stdout
from datetime import datetime
from typing import Dict, Any, List, Optional

from flask import Flask, render_template, request, redirect, url_for, Response, jsonify, session
from jinja2 import ChoiceLoader, FileSystemLoader

from detailed.detailed_analyzer import DetailedGreenplumFunctionAnalyzer, ClusterConfig

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-this-in-production'

# Добавляем пути для шаблонов
app.jinja_loader = ChoiceLoader([
    FileSystemLoader('templates'),
    FileSystemLoader('detailed/templates')
])

# Default stand presets
STANDS = {
    'PROM': {
        'host': 'gp_dns_gp_rozn4.gp.df.sbrf.ru',
        'port': 5432,
        'dbname': 'gp_rozn2',
    },
    'LD': {
        'host': 'gp_dns_pkap1150.gp.df.sbrf.ru',
        'port': 5432,
        'dbname': 'gp_rozn2',
    },
    'IFT': {
        'host': 'tvlds-sdpgp0478.qa.df.sbrf.ru',
        'port': 5432,
        'dbname': 'iftadbcom',
    },
}

# In-memory store of running jobs and logs
_jobs: Dict[str, Dict[str, Any]] = {}
_logs: Dict[str, "queue.Queue[str]"] = {}


def _build_conn_string(stand_type: str, user: str, password: str, host: Optional[str], port: Optional[int], dbname: Optional[str]) -> str:
    """Формирует строку подключения к Greenplum"""
    preset = STANDS.get(stand_type.upper(), {})
    host_val = host or preset.get('host')
    port_val = port or preset.get('port')
    db_val = dbname or preset.get('dbname')
    return f"dbname={db_val} user={user} password={password} host={host_val} port={port_val}"


def _enqueue_log(job_id: str, text: str):
    """Добавляет сообщение в лог задачи"""
    if job_id not in _logs:
        _logs[job_id] = queue.Queue()
    for line in text.splitlines():
        _logs[job_id].put(line + "\n")


def _stream_stdout_to_queue(job_id: str):
    """Перенаправляет stdout в очередь логов"""
    class Stream(io.TextIOBase):
        def write(self, s):
            _enqueue_log(job_id, str(s))
            return len(s)
    return Stream()


def _run_discovery_job(job_id: str, payload: Dict[str, Any]):
    """Запуск первого этапа: обнаружение таблиц"""
    buf = _stream_stdout_to_queue(job_id)
    try:
        with redirect_stdout(buf):
            # Создаём конфигурацию кластера
            cluster_config = ClusterConfig(
                segments=payload.get('segments', 120),
                ram_per_seg_gb=payload.get('ram_per_seg_gb', 153.6)
            )
            analyzer = DetailedGreenplumFunctionAnalyzer(config=cluster_config)
            
            # Подключаемся к БД если нужно
            if payload.get('use_db_connection'):
                conn = _build_conn_string(
                    payload.get('stand_type', 'PROM'),
                    payload['user'], payload['password'],
                    payload.get('host'), payload.get('port'), payload.get('dbname')
                )
                if not analyzer.connect(conn):
                    _jobs[job_id]['status'] = 'error'
                    _jobs[job_id]['error'] = 'Не удалось подключиться к БД. Проверьте логин и пароль.'
                    return
            
            # Запускаем обнаружение таблиц
            result = analyzer.discover_tables(payload['ddl'])
            
            # Сохраняем анализатор и результат
            _jobs[job_id]['analyzer'] = analyzer
            _jobs[job_id]['discovery_result'] = result
            _jobs[job_id]['status'] = 'tables_discovered'
    except Exception as e:
        _jobs[job_id]['status'] = 'error'
        _jobs[job_id]['error'] = str(e)
        _enqueue_log(job_id, f"\n❌ Ошибка: {e}\n")
    finally:
        _enqueue_log(job_id, "\n[STREAM_END]\n")


def _run_analysis_job(job_id: str, payload: Dict[str, Any]):
    """Запуск второго этапа: анализ с пользовательскими размерами"""
    buf = _stream_stdout_to_queue(job_id)
    try:
        with redirect_stdout(buf):
            # Получаем сохранённый анализатор
            analyzer = _jobs[job_id]['analyzer']
            
            # Запускаем анализ с пользовательскими размерами
            params = payload.get('params', [])
            user_sizes = payload.get('user_sizes', {})
            
            result = analyzer.analyze_with_user_sizes(params, user_sizes)
            _jobs[job_id]['result'] = result
            _jobs[job_id]['status'] = 'done'
    except Exception as e:
        _jobs[job_id]['status'] = 'error'
        _jobs[job_id]['error'] = str(e)
        _enqueue_log(job_id, f"\n❌ Ошибка: {e}\n")
    finally:
        _enqueue_log(job_id, "\n[STREAM_END]\n")


@app.route('/')
def index():
    """Перенаправляем на страницу детального анализа"""
    return redirect(url_for('detailed_index'))


@app.route('/detailed')
def detailed_index():
    """Страница ввода DDL"""
    error = request.args.get('error', '')
    return render_template('detailed_input.html', stands=STANDS, error=error)


@app.route('/detailed/discover', methods=['POST'])
def detailed_discover():
    """Запуск первого этапа - обнаружение таблиц"""
    # Получаем данные формы
    ddl = request.form.get('ddl')
    use_db = request.form.get('use_db_connection') == 'on'
    
    # Базовые настройки
    data = {
        'ddl': ddl,
        'use_db_connection': use_db,
        'segments': int(request.form.get('segments', 120)),
        'ram_per_seg_gb': float(request.form.get('ram_per_seg_gb', 153.6)),
    }
    
    # Проверяем наличие DDL
    if not ddl or not ddl.strip():
        return redirect(url_for('detailed_index', error='ddl_required'))
    
    # Если используем БД, добавляем параметры подключения
    if use_db:
        user = request.form.get('user', '').strip()
        password = request.form.get('password', '').strip()
        
        # Проверяем наличие логина и пароля
        if not user or not password:
            return redirect(url_for('detailed_index', error='db_required'))
        
        data.update({
            'stand_type': request.form.get('stand_type', 'PROM'),
            'host': request.form.get('host') or None,
            'port': request.form.get('port') or None,
            'dbname': request.form.get('dbname') or None,
            'user': user,
            'password': password,
        })
    
    # Создаём задачу
    job_id = datetime.now().strftime('%Y%m%d%H%M%S%f') + '_disc'
    _jobs[job_id] = {'status': 'running', 'discovery_result': None}
    _logs[job_id] = queue.Queue()
    
    # Запускаем в отдельном потоке
    th = threading.Thread(target=_run_discovery_job, args=(job_id, data), daemon=True)
    th.start()
    
    return redirect(url_for('discovery_result', job_id=job_id))


@app.route('/discovery/result/<job_id>')
def discovery_result(job_id: str):
    """Страница с результатами обнаружения таблиц"""
    job = _jobs.get(job_id)
    if not job:
        return "Задача не найдена", 404
    return render_template('table_sizes.html', job_id=job_id, status=job['status'])


@app.route('/detailed/analyze', methods=['POST'])
def detailed_analyze():
    """Запуск второго этапа - анализ с пользовательскими размерами"""
    job_id = request.form.get('job_id')
    
    # Проверяем существование задачи
    if job_id not in _jobs:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    # Получаем параметры функции - ЭТО ВАЖНО!
    params_str = request.form.get('params', '').strip()
    params = [p.strip() for p in params_str.split(',') if p.strip()] if params_str else []
    
    print(f"DEBUG: Получены параметры для анализа: {params}")  # Отладка
    
    # Получаем пользовательские размеры из формы
    user_sizes = {}
    for key in request.form:
        if key.startswith('size_'):
            table_name = key[5:]  # убираем префикс 'size_'
            try:
                value = int(request.form[key])
                if value >= 0:
                    user_sizes[table_name] = value
            except ValueError:
                pass
    
    # Обновляем статус
    _jobs[job_id]['status'] = 'running'
    
    # Запускаем анализ в отдельном потоке с ПЕРЕДАЧЕЙ ПАРАМЕТРОВ
    th = threading.Thread(target=_run_analysis_job, args=(job_id, {
        'params': params,  # ← вот здесь передаём параметры!
        'user_sizes': user_sizes
    }), daemon=True)
    th.start()
    
    return redirect(url_for('detailed_result', job_id=job_id))


@app.route('/detailed/result/<job_id>')
def detailed_result(job_id: str):
    """Страница с результатами анализа"""
    job = _jobs.get(job_id)
    if not job:
        return "Задача не найдена", 404
    return render_template('detailed_result.html', job_id=job_id, status=job['status'])


@app.route('/stream/<job_id>')
def stream(job_id: str):
    """Server-Sent Events поток логов"""
    if job_id not in _logs:
        return "Лог не найден", 404

    def event_stream():
        q = _logs[job_id]
        while True:
            line = q.get()
            yield f"data: {line}\n\n"
            if line.strip() == '[STREAM_END]':
                break

    return Response(event_stream(), mimetype='text/event-stream')


@app.route('/status/<job_id>')
def status(job_id: str):
    """Возвращает статус задачи"""
    job = _jobs.get(job_id)
    if not job:
        return jsonify({'status': 'not_found'}), 404
    
    st = job['status']
    res = {'status': st}
    
    # Для этапа обнаружения таблиц
    if st == 'tables_discovered' and job.get('discovery_result'):
        res['discovery'] = job['discovery_result']
    
    # Для завершённого анализа
    if st == 'done' and job.get('result'):
        res['summary'] = {
            'function': job['result'].get('function', 'N/A'),
            'blocks_analyzed': job['result'].get('analyzed_blocks', 0),
            'total_memory_gb': job['result'].get('total_memory_gb', 0),
            'estimated_time_sec': job['result'].get('estimated_time_sec', 0),
            'risk': job['result'].get('risk', 'N/A'),
        }
    
    # Если есть ошибка
    if job.get('error'):
        res['error'] = job['error']
    
    return jsonify(res)


@app.route('/details/<job_id>')
def details(job_id: str):
    """Возвращает полные результаты анализа в JSON"""
    job = _jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Результат недоступен'}), 400
    return jsonify(job['result'])


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
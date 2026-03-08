import psutil
import os
import time
from datetime import datetime
from typing import Dict
import threading

class PerformanceMonitor:
    """Мониторинг производительности приложения"""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.start_time = time.time()
        self.memory_samples = []
        self.cpu_samples = []
        self.monitoring = False
        self.monitor_thread = None
    
    def start_monitoring(self):
        """Запускает мониторинг в фоновом потоке"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Останавливает мониторинг"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
    
    def _monitor_loop(self):
        """Фоновый сбор метрик"""
        while self.monitoring:
            try:
                # Сбор памяти
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                
                # Сбор CPU
                cpu_percent = self.process.cpu_percent(interval=0.1)
                
                timestamp = time.time() - self.start_time
                self.memory_samples.append((timestamp, memory_mb))
                self.cpu_samples.append((timestamp, cpu_percent))
                
                # Ограничиваем количество семплов
                if len(self.memory_samples) > 1000:
                    self.memory_samples = self.memory_samples[-1000:]
                    self.cpu_samples = self.cpu_samples[-1000:]
                
                time.sleep(1)
            except:
                break
    
    def get_stats(self) -> Dict:
        """Возвращает текущую статистику"""
        if not self.memory_samples:
            return {
                'current_memory_mb': 0,
                'peak_memory_mb': 0,
                'avg_memory_mb': 0,
                'current_cpu_percent': 0,
                'peak_cpu_percent': 0,
                'avg_cpu_percent': 0,
                'uptime_seconds': time.time() - self.start_time,
                'samples_count': 0
            }
        
        current_memory = self.memory_samples[-1][1] if self.memory_samples else 0
        peak_memory = max(m for _, m in self.memory_samples)
        avg_memory = sum(m for _, m in self.memory_samples) / len(self.memory_samples)
        
        current_cpu = self.cpu_samples[-1][1] if self.cpu_samples else 0
        peak_cpu = max(c for _, c in self.cpu_samples)
        avg_cpu = sum(c for _, c in self.cpu_samples) / len(self.cpu_samples) if self.cpu_samples else 0
        
        return {
            'current_memory_mb': round(current_memory, 2),
            'peak_memory_mb': round(peak_memory, 2),
            'avg_memory_mb': round(avg_memory, 2),
            'current_cpu_percent': round(current_cpu, 2),
            'peak_cpu_percent': round(peak_cpu, 2),
            'avg_cpu_percent': round(avg_cpu, 2),
            'uptime_seconds': round(time.time() - self.start_time, 2),
            'samples_count': len(self.memory_samples)
        }
    
    def log_stats(self):
        """Логирует статистику"""
        stats = self.get_stats()
        print(f"\n📊 ПРОИЗВОДИТЕЛЬНОСТЬ:")
        print(f"  Память: {stats['current_memory_mb']} MB (пик: {stats['peak_memory_mb']} MB, сред: {stats['avg_memory_mb']} MB)")
        print(f"  CPU: {stats['current_cpu_percent']}% (пик: {stats['peak_cpu_percent']}%, сред: {stats['avg_cpu_percent']}%)")
        print(f"  Время работы: {stats['uptime_seconds']} сек")
        print(f"  Семплов: {stats['samples_count']}")
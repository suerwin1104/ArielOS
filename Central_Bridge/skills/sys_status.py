import psutil
import json
import sys

def get_system_status():
    cpu_usage = psutil.cpu_percent(interval=1)
    memory_info = psutil.virtual_memory()
    memory_usage = memory_info.percent
    
    status = {
        "cpu_usage_percent": cpu_usage,
        "memory_usage_percent": memory_usage,
        "memory_available_mb": round(memory_info.available / (1024 * 1024), 2),
        "memory_total_mb": round(memory_info.total / (1024 * 1024), 2)
    }
    return status

if __name__ == "__main__":
    status = get_system_status()
    print(f"目前系統狀態：\n- CPU 使用率: {status['cpu_usage_percent']}%\n- 記憶體使用率: {status['memory_usage_percent']}% ({status['memory_available_mb']} MB / {status['memory_total_mb']} MB 可用)")

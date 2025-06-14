import json
import os
from threading import Lock

# 缓存文件路径（与本模块同级目录下）
CACHE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(CACHE_DIR, "cache.json")
cache_lock = Lock()

# 加载缓存数据
def load_cache():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

# 保存缓存数据
def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get(key):
    with cache_lock:
        data = load_cache()
        return data.get(key)

def set(key, value):
    with cache_lock:
        data = load_cache()
        data[key] = value
        save_cache(data)
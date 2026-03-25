import requests
import mysql.connector
import json
import gzip
import pytz
import sys

sys.path.append('c:\\Users\\86150\\Desktop\\NPU\\agent')
from SmartVoyage.config import Config

config = Config()

# ==========================================
# 和风天气相关配置
# ==========================================
API_KEY = config.weather_api_key  # 和风天气API密钥
city_codes = config.weather_city_codes  # 城市及其对应code字典
BASE_URL = config.weather_base_url  # 和风天气接口基础url
TZ = pytz.timezone('Asia/Shanghai')  # 使用上海时区

# ==========================================
# MySQL 数据库配置
# ==========================================
db_config = {
    "host": config.db_host,  # 数据库主机
    "user": config.db_user,  # 用户名
    "password": config.db_password,  # 密码
    "database": config.db_database,  # 数据库名
    "charset": "utf8mb4"  # 字符集
}


def connect_db():
    return mysql.connector.connect(**db_config)


# 数据爬取与解析
def fetch_weather_data(city, location):
    headers = {
        "X-QW-Api-Key": API_KEY,
        "Accept-Encoding": "gzip"
    }
    url = f"{BASE_URL}?location={location}"
    print('url--->', url)
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        if response.headers.get('Content-Encoding') == 'gzip':
            data = gzip.decompress(response.content).decode('utf-8')
        else:
            data = response.text
        return json.loads(data)
    except requests.RequestException as e:
        print(f"请求 {city} 天气数据失败: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"{city} JSON 解析错误: {e}, 响应内容: {response.text[:500]}...")
        return None
    except gzip.BadGzipFile:
        print(f"{city} 数据未正确解压，尝试直接解析: {response.text[:500]}...")
        return json.loads(response.text) if response.text else None


# 验证代码
if __name__ == "__main__":
    weather_data = fetch_weather_data("北京", city_codes["北京"])
    print(weather_data)
    print("解析成功！")

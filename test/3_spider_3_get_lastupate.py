import sys
import requests
import mysql.connector

sys.path.append('c:\\Users\\86150\\Desktop\\NPU\\agent')
from datetime import datetime, timedelta
import schedule
import time
import json
import gzip
import pytz
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
    """建立并返回MySQL数据库连接"""
    return mysql.connector.connect(**db_config)


# 数据爬取与解析功能
def fetch_weather_data(city, location):
    """
    获取指定城市的天气数据

    Args:
        city (str): 城市名称
        location (str): 城市对应的位置代码

    Returns:
        dict: 解析后的JSON天气数据，失败返回None
    """
    headers = {
        "X-QW-Api-Key": API_KEY,  # API认证密钥
        "Accept-Encoding": "gzip"  # 请求使用gzip压缩
    }
    url = f"{BASE_URL}?location={location}"  # 构建完整的API请求URL

    try:
        # 发送HTTP GET请求获取天气数据
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # 如果响应状态码不是200，抛出异常

        # 检查响应内容是否使用gzip压缩
        if response.headers.get('Content-Encoding') == 'gzip':
            # 解压gzip压缩的数据并解码为UTF-8字符串
            data = gzip.decompress(response.content).decode('utf-8')
        else:
            # 直接获取响应文本内容
            data = response.text

        # 将JSON字符串解析为Python字典并返回
        return json.loads(data)

    except requests.RequestException as e:
        # 处理网络请求相关的异常
        print(f"请求 {city} 天气数据失败: {e}")
        return None
    except json.JSONDecodeError as e:
        # 处理JSON解析错误
        print(f"{city} JSON 解析错误: {e}, 响应内容: {response.text[:500]}...")
        return None
    except gzip.BadGzipFile:
        # 处理gzip解压失败的情况
        print(f"{city} 数据未正确解压，尝试直接解析: {response.text[:500]}...")
        return json.loads(response.text) if response.text else None


def get_latest_update_time(cursor, city):
    """
    获取指定城市在数据库中最新的更新时间

    Args:
        cursor: 数据库游标对象
        city (str): 城市名称

    Returns:
        datetime: 最新的更新时间，如果没有记录则返回None
    """
    # 执行SQL查询，获取指定城市的最新更新时间
    cursor.execute("SELECT MAX(update_time) FROM weather_data WHERE city = %s", (city,))
    result = cursor.fetchone()  # 获取查询结果
    print("==================查询结果=================")
    print(result)
    return result[0] if result[0] else None  # 返回更新时间或None


# 验证代码
if __name__ == "__main__":
    # 建立数据库连接
    conn = connect_db()
    cursor = conn.cursor()

    # 获取北京城市的最新更新的时间日期
    print(get_latest_update_time(cursor, '北京'))

    # 关闭数据库连接
    cursor.close()
    conn.close()

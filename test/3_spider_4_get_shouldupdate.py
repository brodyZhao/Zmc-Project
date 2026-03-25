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
        # 处理网络请求相关的异常（如超时、连接错误等）
        print(f"请求 {city} 天气数据失败: {e}")
        return None
    except json.JSONDecodeError as e:
        # 处理JSON解析错误
        print(f"{city} JSON 解析错误: {e}, 响应内容: {response.text[:500]}...")
        return None
    except gzip.BadGzipFile:
        # 处理gzip解压失败的情况（数据可能未压缩）
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
    return result[0] if result[0] else None  # 返回更新时间或None


def should_update_data(latest_time, force_update=False):
    """
    判断是否需要更新天气数据

    Args:
        latest_time (datetime): 上次更新时间
        force_update (bool): 是否强制更新，默认为False

    Returns:
        bool: True表示需要更新，False表示不需要更新
    """
    # 如果强制更新标志为True，则直接返回需要更新
    if force_update:
        return True

    # 如果上次更新时间为None（表示没有数据），则需要更新
    if latest_time is None:
        return True

    # 获取当前时间（使用上海时区）
    current_time = datetime.now(TZ)

    # 判断当前时间与上次更新时间是否超过1天，超过则需要更新，计算天数差
    return (current_time - latest_time) > timedelta(days=1)


# 验证代码
if __name__ == "__main__":
    from datetime import datetime, timedelta
    import pytz

    # 设置时区
    TZ = pytz.timezone('Asia/Shanghai')

    # 模拟一个2天前的更新时间
    latest = datetime.now(TZ) - timedelta(days=2)
    print("========模拟一个两天前的时间==============")
    print(latest)
    # 测试是否需要更新数据
    print(should_update_data(latest))

    # 根据更新判断结果输出相应信息
    if should_update_data(latest):
        print(f"需要更新数据，上次更新时间：{latest}")
    else:
        print("没有数据，需要更新数据！")

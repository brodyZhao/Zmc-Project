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
    return mysql.connector.connect(**db_config)


# 数据爬取与解析
def fetch_weather_data(city, location):
    headers = {
        "X-QW-Api-Key": API_KEY,
        "Accept-Encoding": "gzip"
    }
    url = f"{BASE_URL}?location={location}"
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


def get_latest_update_time(cursor, city):
    cursor.execute("SELECT MAX(update_time) FROM weather_data WHERE city = %s", (city,))
    result = cursor.fetchone()
    return result[0] if result[0] else None


def should_update_data(latest_time, force_update=False):
    if force_update:
        return True
    if latest_time is None:
        return True
    current_time = datetime.now(TZ)
    return (current_time - latest_time) > timedelta(days=1)


def store_weather_data(conn, cursor, city, data):
    if not data or data.get("code") != "200":
        print(f"{city} 数据无效，跳过存储。")
        return

    daily_data = data.get("daily", [])
    update_time = datetime.fromisoformat(data.get("updateTime").replace("+08:00", "+08:00")).replace(tzinfo=TZ)

    for day in daily_data:
        fx_date = datetime.strptime(day["fxDate"], "%Y-%m-%d").date()
        values = (
            city, fx_date,
            day.get("sunrise"), day.get("sunset"),
            day.get("moonrise"), day.get("moonset"),
            day.get("moonPhase"), day.get("moonPhaseIcon"),
            day.get("tempMax"), day.get("tempMin"),
            day.get("iconDay"), day.get("textDay"),
            day.get("iconNight"), day.get("textNight"),
            day.get("wind360Day"), day.get("windDirDay"), day.get("windScaleDay"), day.get("windSpeedDay"),
            day.get("wind360Night"), day.get("windDirNight"), day.get("windScaleNight"), day.get("windSpeedNight"),
            day.get("precip"), day.get("uvIndex"),
            day.get("humidity"), day.get("pressure"),
            day.get("vis"), day.get("cloud"),
            update_time
        )
        insert_query = """
        INSERT INTO weather_data (
            city, fx_date, sunrise, sunset, moonrise, moonset, moon_phase, moon_phase_icon,
            temp_max, temp_min, icon_day, text_day, icon_night, text_night,
            wind360_day, wind_dir_day, wind_scale_day, wind_speed_day,
            wind360_night, wind_dir_night, wind_scale_night, wind_speed_night,
            precip, uv_index, humidity, pressure, vis, cloud, update_time
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            sunrise = VALUES(sunrise), sunset = VALUES(sunset), moonrise = VALUES(moonrise),
            moonset = VALUES(moonset), moon_phase = VALUES(moon_phase), moon_phase_icon = VALUES(moon_phase_icon),
            temp_max = VALUES(temp_max), temp_min = VALUES(temp_min), icon_day = VALUES(icon_day),
            text_day = VALUES(text_day), icon_night = VALUES(icon_night), text_night = VALUES(text_night),
            wind360_day = VALUES(wind360_day), wind_dir_day = VALUES(wind_dir_day), wind_scale_day = VALUES(wind_scale_day),
            wind_speed_day = VALUES(wind_speed_day), wind360_night = VALUES(wind360_night),
            wind_dir_night = VALUES(wind_dir_night), wind_scale_night = VALUES(wind_scale_night),
            wind_speed_night = VALUES(wind_speed_night), precip = VALUES(precip), uv_index = VALUES(uv_index),
            humidity = VALUES(humidity), pressure = VALUES(pressure), vis = VALUES(vis),
            cloud = VALUES(cloud), update_time = VALUES(update_time)
        """
        try:
            cursor.execute(insert_query, values)
            print(f"{city} {fx_date} 数据写入/更新成功: {day.get('textDay')}, 影响行数: {cursor.rowcount}")
        except mysql.connector.Error as e:
            print(f"{city} {fx_date} 数据库错误: {e}")

    conn.commit()
    print(f"{city} 事务提交完成。")


def update_weather(force_update=False):
    conn = connect_db()
    cursor = conn.cursor()

    for city, location in city_codes.items():
        latest_time = get_latest_update_time(cursor, city)
        if should_update_data(latest_time, force_update):
            print(f"开始更新 {city} 天气数据...")
            data = fetch_weather_data(city, location)
            if data:
                store_weather_data(conn, cursor, city, data)
        else:
            print(f"{city} 数据已为最新，无需更新。最新更新时间: {latest_time}")

    cursor.close()
    conn.close()


# 验证代码
if __name__ == "__main__":
    update_weather(force_update=True)

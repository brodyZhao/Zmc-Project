import requests
import mysql.connector
from datetime import datetime
import schedule
import time
import json
import gzip
import pytz
from Agent.SmartVoyage.config import Config

# 从配置文件中加载配置信息
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


# todo:1-创建数据库连接
def connect_db():
    """
    连接MySQL数据库，并返回数据库连接对象。
    :return: mysql.connector MySQL连接
    """
    return mysql.connector.connect(**db_config)


# todo:2-获取天气数据
def fetch_weather_data(city, location):
    """
    从和风天气API根据城市名和城市编码拉取天气数据

    :param city: 城市名称（如 "北京"）
    :param location: 和风天气城市location代码（如 "101010100"）
    :return: dict类型，拉取的天气数据，或None（请求失败时）
    """
    # 设置请求头，包括API密钥和接受gzip压缩
    headers = {
        "X-QW-Api-Key": API_KEY,  # API 密钥
        "Accept-Encoding": "gzip"  # 接受gzip压缩响应
    }
    # 构建请求URL
    url = f"{BASE_URL}?location={location}"
    try:
        # 发起GET请求，超时时间为10秒
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()


        # 如果服务端返回gzip压缩内容，则解压
        if response.headers.get('Content-Encoding') == 'gzip':
            data = gzip.decompress(response.content).decode('utf-8')
            # print('data1--->', data)
        else:
            data = response.text
            # print('data2--->', data)
        return json.loads(data)
    except requests.RequestException as e:
        # 处理网络请求异常
        print(f"请求 {city} 天气数据失败: {e}")
        return None
    except json.JSONDecodeError as e:
        # 处理JSON解析错误
        print(f"{city} JSON 解析错误: {e}, 响应内容: {response.text[:500]}...")
        return None
    except gzip.BadGzipFile:
        # gzip解压失败后，直接尝试解析原始文本内容
        print(f"{city} 数据未正确解压，尝试直接解析: {response.text[:500]}...")
        return json.loads(response.text) if response.text else None


# todo:3-获取最新数据更新时间
def get_latest_update_time(cursor, city):
    """
    查询指定城市weather_data表中最新的数据更新时间
    :param cursor: MySQL游标
    :param city: 城市名称
    :return: 最新的update_time (datetime) 或 None
    """
    # 执行SQL查询，获取指定城市最新的更新时间
    cursor.execute("SELECT MAX(update_time) FROM weather_data WHERE city = %s", (city,))
    # 获取查询结果
    result = cursor.fetchone()
    # print('result--->', result)
    # 返回查询结果，如果结果为空则返回None
    return result[0] if result[0] else None


# todo:4-判断数据是否需要更新
def should_update_data(latest_time, force_update=False):
    """
    判断天气数据是否需要更新
    :param latest_time: 数据库中最近一次更新的时间（datetime）
    :param force_update: 是否强制更新
    :return: bool 是否需要更新
    """

    # 如果设置了强制更新，直接返回True
    if force_update:
        return True
    # 如果没有最新的更新时间记录，说明是首次更新，返回True
    if not latest_time:
        return True

    # 获取当前时间（使用上海时区）
    current_time = datetime.now(TZ)
    # print('current_time--->', current_time)

    # 为latest_time设置时区信息，确保与current_time在同一时区下比较
    # 防止因时区不一致导致的时间比较错误
    latest_time = latest_time.replace(tzinfo=TZ)
    # print('latest_time--->', latest_time)

    # 计算当前时间与最新更新时间之间的差值（以小时为单位）
    # 如果差值大于等于24小时，则需要更新数据，返回True；否则返回False
    return (current_time - latest_time).total_seconds() / 3600 >= 24


# todo:5-存储数据
def store_weather_data(conn, cursor, city, data):
    """
    将指定城市的天气数据存入MySQL数据库。如果(city, fx_date)已存在则更新数据，否则插入新数据。

    :param conn: MySQL连接实例
    :param cursor: MySQL游标实例
    :param city: 城市名称（如"北京"）
    :param data: API返回的天气数据(dict类型)
    """
    # 检查数据是否有效
    if not data or data.get("code") != "200":
        print(f"{city} 数据无效，跳过存储。")
        return

    # 获取每日天气预报数据
    daily_data = data.get("daily", [])
    # print("daily_data--->", daily_data)
    # 将 updateTime 字符串转换为datetime对象，并设置上海时区
    update_time = datetime.fromisoformat(data.get("updateTime").replace("+08:00", "+08:00")).replace(tzinfo=TZ)
    # print("update_time--->", update_time)

    # 遍历每日天气数据并存储到数据库
    for day in daily_data:
        fx_date = datetime.strptime(day["fxDate"], "%Y-%m-%d").date()
        # print("fx_date--->", fx_date)
        # 按照表定义顺序准备SQL插入参数
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
        # SQL插入/更新语句: 若city和fx_date主键已存在则更新，否则插入
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
            print(f"{city} {fx_date} 数据插入/更新成功: {day.get('textDay')}, 影响行数: {cursor.rowcount}")
        except mysql.connector.Error as e:
            print(f"{city} {fx_date} 数据库错误: {e}")

    conn.commit()
    print(f"{city} 事务提交完成。")


# todo:6-更新数据
def update_weather(force_update=False):
    """
    遍历city_codes，获取并更新所有城市的天气数据到数据库
    :param force_update: 是否强制更新，默认False（True时无视更新时间直接拉取并写入）
    """
    conn = connect_db()
    cursor = conn.cursor()

    # 遍历所有城市及其位置代码
    for city, location in city_codes.items():
        # 获取该城市在数据库中的最新更新时间
        latest_time = get_latest_update_time(cursor, city)
        # 判断是否需要更新数据：根据最新更新时间和是否强制更新来决定
        if should_update_data(latest_time, force_update):
            print(f"开始更新 {city} 天气数据...")
            # 调用API获取天气数据
            data = fetch_weather_data(city, location)
            print("data--->", data)
            # 如果成功获取到数据，则存储到数据库
            if data:
                store_weather_data(conn, cursor, city, data)
        else:
            # 如果不需要更新，打印提示信息
            print(f"{city} 数据已为最新，无需更新。最新更新时间: {latest_time}")

    # 关闭数据库游标和连接
    cursor.close()
    conn.close()


# todo:7-定时任务
def setup_scheduler():
    """
    设置每日定时任务，自动在每天04:00(北京时间)更新
    """
    # 每天凌晨 4:00 北京时间
    schedule.every().day.at("18:08").do(update_weather)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    # 立即执行一次更新
    update_weather()
    # 启动定时任务服务
    setup_scheduler()

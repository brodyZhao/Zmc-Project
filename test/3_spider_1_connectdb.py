import mysql.connector
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
    """
    连接MySQL数据库，并返回数据库连接对象。
    :return: mysql.connector MySQL连接
    """
    return mysql.connector.connect(**db_config)


if __name__ == '__main__':
    conn = connect_db()
    print(conn.is_connected())
    print("数据库连接成功！")
    conn.close()

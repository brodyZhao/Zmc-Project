import sys
# mcp_ticket_server.py
# 功能描述：
# 本模块用于提供票务数据库查询接口，仅支持SELECT查询，返回标准JSON格式结果。
# 特点：只读查询、异常捕获处理、支持日期和Decimal的JSON序列化，不支持票务预订，仅做查询展示。
# 主要表结构支持：train_tickets、flight_tickets、concert_tickets

import mysql.connector  # 导入MySQL数据库连接器，用于连接和操作MySQL数据库
import logging  # 导入日志模块，用于记录运行信息和异常信息
import json  # 导入JSON模块，用于数据序列化与传输

sys.path.append('c:\\Users\\86150\\Desktop\\NPU\\agent')
from datetime import date, datetime, timedelta  # 导入时间相关类型
from decimal import Decimal  # 导入高精度数字类型Decimal，防止浮点精度误差
from SmartVoyage.config import Config

# ================= 日志配置区 =================
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 创建配置对象
config = Config()


# ================= JSON序列化辅助类 =================
class DateEncoder(json.JSONEncoder):
    """
    自定义JSON编码器，支持date, datetime, timedelta, Decimal等类型的转换。

    用于json.dumps的cls参数，实现自动转换数据库查询结果中的复杂对象。

    参数 obj: 待序列化对象
    返回: 可被JSON序列化的对象
    """

    def default(self, obj):
        # 判断是否为date或datetime对象
        if isinstance(obj, (date, datetime)):
            # 如果是datetime对象，格式为 'YYYY-MM-DD HH:MM:SS'
            # 如果是date对象，格式为 'YYYY-MM-DD'
            return (
                obj.strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(obj, datetime)
                else obj.strftime("%Y-%m-%d")
            )
        # 判断是否为timedelta对象，转为字符串（如 '1 day, 2:30:00'）
        if isinstance(obj, timedelta):
            return str(obj)
        # 判断是否为Decimal对象，转为浮点数
        if isinstance(obj, Decimal):
            return float(obj)
        # 其他无法识别类型，使用父类默认方法处理
        return super().default(obj)


# ================= 票务服务核心类 =================
class TicketService:
    """
    票务服务类。
    封装数据库连接与只读查询逻辑。

    属性:
        conn (mysql.connector.connection.MySQLConnection): 数据库连接对象

    方法:
        execute_query(sql: str) -> str: 执行只读SELECT的SQL查询，返回JSON字符串
    """

    def __init__(self):
        """
        初始化TicketService实例与数据库连接。
        """
        self.conn = mysql.connector.connect(host=config.db_host,
                                            user=config.db_user,
                                            password=config.db_password,
                                            database=config.db_database)

    def execute_query(self, sql: str) -> str:
        """
        执行SQL只读查询(支持SELECT等)，自动处理常见时间和数字类型为JSON字符串。

        参数:
            sql (str): 待查询的SQL语句（强烈建议限制只支持SELECT，切勿用于UPDATE/DELETE/INSERT等操作）

        返回:
            str: 查询结果的JSON字符串。结构为：
                - status=success, data=[结果列表]
                - status=no_data, message=无数据提示
                - status=error, message=错误信息

        示例:
            execute_query('SELECT * FROM train_tickets WHERE departure_city="北京"')
        """
        try:
            # 创建游标，设置为返回字典格式，方便自定义序列化字段类型
            cursor = self.conn.cursor(dictionary=True)  # 返回字典格式
            # 执行SQL查询
            cursor.execute(sql)
            # 获取所有查询结果
            results = cursor.fetchall()
            # 关闭游标释放资源
            cursor.close()
            # 遍历结果，对每个字段中的特殊类型（如 datetime, date, timedelta, Decimal）做转换
            for result in results:
                for key, value in result.items():
                    # 如果value是特殊类型，则用定制方法编码
                    if isinstance(value, (date, datetime, timedelta, Decimal)):
                        result[key] = self.default_encoder(value)
            # 如果有查询结果，封装为status=success
            if results:
                return json.dumps(
                    {"status": "success", "data": results},
                    cls=DateEncoder,  # 传递自定义日期编码类
                    ensure_ascii=False,
                )
            else:
                # 无结果，返回对应提示
                return json.dumps(
                    {
                        "status": "no_data",
                        "message": "未找到票务数据，请确认查询条件。",
                    },
                    ensure_ascii=False,
                )
        except Exception as e:
            # 捕获异常并记录日志，返回错误提示
            logger.error(f"票务查询错误: {str(e)}")
            return json.dumps(
                {"status": "error", "message": str(e)}, ensure_ascii=False
            )

    def default_encoder(self, obj):
        """
        JSON兼容类型转换函数，针对单个对象。

        参数:
            obj: 任意待转换对象

        返回:
            适合JSON序列化的对象（字符串、浮点数等）
        """
        # 如果是datetime对象，转为字符串 "YYYY-MM-DD HH:MM:SS"
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        # 如果是date对象，转为字符串 "YYYY-MM-DD"
        if isinstance(obj, date):
            return obj.strftime("%Y-%m-%d")
        # 如果是timedelta对象，转为字符串形式（如 "2 days, 0:00:00"）
        if isinstance(obj, timedelta):
            return str(obj)
        # 如果是Decimal对象，转为float类型
        if isinstance(obj, Decimal):
            return float(obj)
        # 其他类型保持原样
        return obj


if __name__ == '__main__':
    service = TicketService()
    print(service.conn.is_connected())
    # 测试查询
    sql = "SELECT id, departure_city, arrival_city, departure_time, arrival_time, train_number, seat_type, price, remaining_seats FROM train_tickets WHERE departure_city = '北京' AND arrival_city = '上海' AND DATE(departure_time) = '2025-10-12' AND seat_type = '商务座'"
    print(service.execute_query(sql))
    service.conn.close()

import sys
# mcp_ticket_server.py
# 功能描述：
# 本模块用于提供票务数据库查询接口，仅支持SELECT查询，返回标准JSON格式结果。
# 特点：只读查询、异常捕获处理、支持日期和Decimal的JSON序列化，不支持票务预订，仅做查询展示。
# 主要表结构支持：train_tickets、flight_tickets、concert_tickets

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


if __name__ == '__main__':
    encoder = DateEncoder()
    print(encoder.default(datetime(2025, 8, 11, 8, 0)))
    print(encoder.default(date(2025, 8, 11)))
    print(encoder.default(timedelta(days=1)))
    print(encoder.default(Decimal('123.45')))  # Decimal 是一种在金融计算中常用的数据类型，可以提供更高的精度，避免浮点数计算中的误差。

    """
    它定义了一个名为 DateEncoder 的自定义 JSON 编码器。
    这是为了解决在将数据库查询结果（其中可能包含日期、时间、时间间隔或 Decimal 类型的数据）
    转换为标准的 JSON 格式时出现的兼容性问题。
    """

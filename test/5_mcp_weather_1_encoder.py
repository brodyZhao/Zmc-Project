import sys
# mcp_weather_server.py
# 功能说明：
#   提供天气数据库查询接口，仅允许SELECT查询，输出标准JSON结果。
#   特点：只读查询、异常捕获处理、安全JSON序列化、用于MCP工具调用。

import logging  # 导入日志模块
import json  # 导入JSON序列化模块

sys.path.append('c:\\Users\\86150\\Desktop\\NPU\\agent')
from SmartVoyage.config import Config  # 全局配置类

# ================== 日志配置 ==================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 实例化配置对象
config = Config()


# ================== 自定义JSON编码器 ==================
class DateEncoder(json.JSONEncoder):
    """
    自定义JSON编码器，支持date, datetime, timedelta, Decimal等类型的转换。

    用法：用于json.dumps的cls参数，实现自动转换数据库查询结果中的复杂对象。

    参数:
        obj: 待序列化的各类对象
    返回:
        可被JSON序列化的对象
    """

    def default(self, obj):
        """
        重载JSONEncoder的default方法，用于序列化特殊对象类型。
        支持date、datetime、timedelta和Decimal类型的自动转换输出。

        参数:
            obj: 待序列化的单个对象

        返回:
            可被JSON安全序列化的对象（字符串或浮点数等）
        """
        # 序列化日期和时间类型
        if isinstance(obj, (date, datetime)):
            # 如果是datetime对象，格式为 'YYYY-MM-DD HH:MM:SS'
            # 如果是date对象，格式为 'YYYY-MM-DD'
            return (
                obj.strftime('%Y-%m-%d %H:%M:%S')
                if isinstance(obj, datetime)
                else obj.strftime('%Y-%m-%d')
            )
        # 序列化timedelta对象为字符串（如 '1 day, 2:30:00'）
        if isinstance(obj, timedelta):
            return str(obj)
        # 序列化Decimal对象为float以便JSON兼容
        if isinstance(obj, Decimal):
            return float(obj)
        # 对于其他类型，调用父类默认处理逻辑
        return super().default(obj)


if __name__ == '__main__':
    from datetime import datetime, date, timedelta
    from decimal import Decimal

    encoder = DateEncoder()
    print(encoder.default(datetime(2025, 8, 11, 8, 0)))
    print(type(encoder.default(datetime(2025, 8, 11, 8, 0))))
    print("========================================")
    print(datetime(2025, 8, 11, 8, 0))
    print(type(datetime(2025, 8, 11, 8, 0)))

    print(encoder.default(date(2025, 8, 11)))
    print(encoder.default(timedelta(days=1)))
    print(encoder.default(Decimal('123.45')))

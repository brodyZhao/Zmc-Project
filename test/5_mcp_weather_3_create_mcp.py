import sys
# mcp_weather_server.py
# 功能说明：
#   提供天气数据库查询接口，仅允许SELECT查询，输出标准JSON结果。
#   特点：只读查询、异常捕获处理、安全JSON序列化、用于MCP工具调用。

import mysql.connector  # 导入MySQL数据库连接器
import logging  # 导入日志模块
import json  # 导入JSON序列化模块

sys.path.append('c:\\Users\\86150\\Desktop\\NPU\\agent')
from datetime import date, datetime, timedelta  # 时间和日期相关类型
from decimal import Decimal  # 精确十进制类型
from python_a2a.mcp import FastMCP  # MCP工具服务器框架类
import uvicorn  # ASGI服务器
from python_a2a.mcp import create_fastapi_app  # 创建FastAPI应用
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


# ================== 天气服务核心类 ==================
class WeatherService:
    """
    天气服务类
    封装数据库连接与只读查询逻辑，用于提供天气数据SELECT查询。

    属性:
        conn (mysql.connector.connection.MySQLConnection): 数据库连接对象

    方法:
        execute_query(sql: str) -> str
            执行只读SELECT的SQL查询，返回JSON序列化标准结果
    """

    def __init__(self):
        """
        初始化WeatherService实例及数据库连接
        数据库配置来源：config对象
        """
        self.conn = mysql.connector.connect(
            host=config.db_host,
            user=config.db_user,
            password=config.db_password,
            database=config.db_database
        )

    def execute_query(self, sql: str) -> str:
        """
        执行SQL只读查询（支持SELECT），自动处理特殊类型并JSON返回。

        参数:
            sql (str): 只读查询SQL语句，如：
                'SELECT * FROM weather_data WHERE city = "北京"'
        返回:
            str: 查询结果的JSON字符串。格式为：
                - 成功：{"status":"success", "data":[数据列表]}
                - 无数据：{"status":"no_data", "message":"未找到天气数据，请确认城市和日期。"}
                - 错误：{"status":"error", "message":错误信息}
        """
        try:
            cursor = self.conn.cursor(dictionary=True)  # 创建字典格式游标，便于字段处理
            cursor.execute(sql)  # 执行传入的SQL查询
            results = cursor.fetchall()  # 获取所有查询结果（列表，每行为字典）
            cursor.close()  # 关闭游标释放数据库资源
            # 对每个结果字段做特殊类型处理（如日期、时间、Decimal等）
            for result in results:
                for key, value in result.items():
                    if isinstance(value, (date, datetime, timedelta, Decimal)):
                        result[key] = self.default_encoder(value)
            # 如果结果非空，打包为成功信息
            if results:
                return json.dumps(
                    {"status": "success", "data": results},
                    cls=DateEncoder,  # 使用自定义JSON编码器（处理时间/数字类型）
                    ensure_ascii=False  # 中文不转义，便于阅读
                )
            else:
                # 无查询结果，返回“未找到数据”提示
                return json.dumps(
                    {
                        "status": "no_data",
                        "message": "未找到天气数据，请确认城市和日期。"
                    },
                    ensure_ascii=False
                )
        except Exception as e:
            # 捕获异常并记录错误日志
            logger.error(f"天气查询错误: {str(e)}")
            # 返回异常信息响应
            return json.dumps(
                {"status": "error", "message": str(e)},
                ensure_ascii=False
            )

    def default_encoder(self, obj):
        """
        用于单个对象的JSON兼容类型转换

        参数:
            obj: 需转换的对象
        返回:
            适宜JSON序列化的对象（字符串、float等）
        """
        # 如果是datetime对象，格式化为 "YYYY-MM-DD HH:MM:SS" 字符串
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        # 如果是date对象，格式化为 "YYYY-MM-DD" 字符串
        if isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        # 如果是timedelta对象，转为字符串（如 "1 day, 2:30:00"）
        if isinstance(obj, timedelta):
            return str(obj)
        # 如果是Decimal对象，转换为float浮点数
        if isinstance(obj, Decimal):
            return float(obj)
        # 其它类型保持原样返回
        return obj


# ================== MCP服务器定义与启动 ==================
def create_weather_mcp_server():
    """
    启动天气MCP服务器主函数

    作用：
        - 注册天气数据查询工具（只读查询接口，自动JSON序列化）
        - 启动FastAPI服务于指定端口
        - 日志显示所有工具信息

    参数:
        无
    返回:
        无（阻塞、标准服务器运行）
    """
    # 初始化FastMCP对象，进行元信息登记
    weather_mcp = FastMCP(
        name="WeatherTools",
        description="天气查询工具，基于 weather_data 表。",
        version="1.0.0"
    )

    # 实例化服务
    service = WeatherService()

    # 注册MCP工具：天气SQL查询工具
    @weather_mcp.tool(
        name="query_weather",
        description=(
                "查询天气数据，输入 SQL，如 "
                '\'SELECT * FROM weather_data WHERE city = "北京" AND fx_date = "2025-07-30"\''
        )
    )
    def query_weather(sql: str) -> str:
        """
        天气SQL查询工具

        参数:
            sql (str): 天气表SELECT SQL, 如：
                'SELECT * FROM weather_data WHERE city="北京" AND fx_date="2025-07-30"'
        返回:
            str: JSON格式结果字符串
        """
        logger.info(f"执行天气查询: {sql}")
        return service.execute_query(sql)

    # 输出服务器及工具信息
    logger.info("=== 天气MCP服务器信息 ===")
    logger.info(f"名称: {weather_mcp.name}")
    logger.info(f"描述: {weather_mcp.description}")
    tools = weather_mcp.get_tools()
    for tool in tools:
        logger.info(f"- {tool['name']}: {tool['description']}")

    # 启动FastAPI服务器（端口6001）
    port = 6001
    app = create_fastapi_app(weather_mcp)
    logger.info(f"启动天气MCP服务器于 http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)


# ================== 脚本启动入口 ==================
if __name__ == "__main__":
    create_weather_mcp_server()

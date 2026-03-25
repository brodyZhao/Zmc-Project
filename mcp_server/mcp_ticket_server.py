# 功能描述：
# 本模块用于提供票务数据库查询接口，仅支持SELECT查询，返回标准JSON格式结果。
# 特点：只读查询、异常捕获处理、支持日期和Decimal的JSON序列化，不支持票务预订，仅做查询展示。
# 主要表结构支持：train_tickets、flight_tickets、concert_tickets

import mysql.connector  # 导入MySQL数据库连接器，用于连接和操作MySQL数据库
import logging  # 导入日志模块，用于记录运行信息和异常信息
import json  # 导入JSON模块，用于数据序列化与传输
import sys
from datetime import date, datetime, timedelta  # 导入时间相关类型
from decimal import Decimal  # 导入高精度数字类型Decimal，防止浮点精度误差
from python_a2a.mcp import FastMCP
import uvicorn  # 导入ASGI服务器，用于FastAPI应用可执行
from python_a2a.mcp import create_fastapi_app  # 创建FastAPI应用

sys.path.append('c:\\Users\\86150\\Desktop\\NPU\\agent')
from SmartVoyage.config import Config

from SmartVoyage.utils.format import DateEncoder, default_encoder

# ================= 日志配置区 =================
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 创建配置对象
config = Config()


# ================= 票务服务核心类 =================
class TicketService(object):
    """
    票务服务类。
    封装数据库连接与只读查询逻辑。
    属性:
        conn (mysql.connector.connection.MySQLConnection): 数据库连接对象
    方法:
        _get_connection(self) -> conn: 数据库连接对象
        execute_query(sql: str) -> str: 执行只读SELECT的SQL查询，返回JSON字符串
    """

    def __init__(self):
        """初始化TicketService实例（不立即创建连接）"""
        self.db_config = {
            "host": config.db_host,
            "user": config.db_user,
            "password": config.db_password,
            "database": config.db_database,
            "charset": "utf8mb4",
            "autocommit": True,
        }

    def _get_connection(self):
        """获取数据库连接（每次查询时创建新连接）"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            return conn
        except Exception as e:
            logger.error(f"数据库连接失败: {str(e)}")
            raise

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
            # 创建数据库连接对象
            conn = self._get_connection()
            # 创建游标，设置为返回字典格式，方便自定义序列化字段类型
            cursor = conn.cursor(dictionary=True)  # 返回字典格式
            # 执行SQL查询
            cursor.execute(sql)
            # 获取所有查询结果
            results = cursor.fetchall()
            # print('results1--->', results)
            # 关闭游标释放资源
            cursor.close()
            # 释放数据库连接
            conn.close()
            # 遍历结果，对每个字段中的特殊类型（如 datetime, date, timedelta, Decimal）做转换
            for result in results:
                for key, value in result.items():
                    # 如果value是特殊类型，则用定制方法编码
                    if isinstance(value, (date, datetime, timedelta, Decimal)):
                        result[key] = default_encoder(value)
            # print('results2--->', results)
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


# ================= MCP服务器定义与启动 =================
def create_ticket_mcp_server():
    """
    启动票务MCP服务器主函数。
    功能说明：
        - 注册票务查询工具，只读数据库查询接口
        - 自动启动FastAPI服务器，监听指定端口
        - 日志输出服务基本信息
    """
    # 创建FastMCP对象，注册票务相关元信息
    ticket_mcp = FastMCP(
        name="TicketTools",
        description="票务查询工具，基于 train_tickets, flight_tickets, concert_tickets 表。只支持查询。",
        version="1.0.0"
    )

    # 实例化TicketService作为SQL查询执行服务
    service = TicketService()

    # 注册MCP工具：票务SQL查询工具
    @ticket_mcp.tool(
        name="query_tickets",
        description=(
                "查询票务数据，输入SQL，如 "
                '\'SELECT * FROM train_tickets WHERE departure_city = "北京" AND arrival_city = "上海"\''
        ),
    )
    def query_tickets(sql: str) -> str:
        """
        票务SQL查询接口工具。
        参数:
            sql (str): 查询SQL语句，建议仅支持SELECT等只读操作
        返回:
            str: JSON格式的查询结果
        """
        # 记录日志，输出SQL
        logger.info(f"执行票务查询: {sql}")
        # 调用服务层执行SQL并返回JSON字符串
        return service.execute_query(sql)

    # 日志打印服务器基本信息与所有可用工具简要信息
    logger.info("=== 票务MCP服务器信息 ===")
    logger.info(f"名称: {ticket_mcp.name}")
    logger.info(f"描述: {ticket_mcp.description}")

    # 运行服务器
    port = 8001
    app = create_fastapi_app(ticket_mcp)
    logger.info(f"启动票务MCP服务器于 http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)


# ============ 脚本直接启动入口 ============
if __name__ == "__main__":
    # service = TicketService()
    # # service._get_connection(): 创建conn数据库连接对象
    # # is_connected(): 判断数据库是否连接成功
    # print(service._get_connection().is_connected())
    # # 测试查询
    # sql = "SELECT * FROM train_tickets WHERE departure_city='北京' AND DATE(departure_time) = '2025-09-13'"
    # # 调用对象execute_query方法
    # print(service.execute_query(sql))
    # service._get_connection().close()

    create_ticket_mcp_server()

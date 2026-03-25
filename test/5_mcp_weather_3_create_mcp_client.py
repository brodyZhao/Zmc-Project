import asyncio
import json
import logging
from python_a2a.mcp import MCPClient  # 引入MCPClient，用于与MCP服务器交互

# 配置日志输出格式和日志级别
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_weather_mcp():
    # 天气MCP服务监听端口
    port = 6001  
    # 创建MCPClient对象，连接本地MCP天气服务
    client = MCPClient(f"http://localhost:{port}")
    try:
        # ============ 获取MCP工具列表 ============
        tools = await client.get_tools()
        logger.info("天气 MCP 可用工具：")
        for tool in tools:
            # 打印每个可用工具的名称和描述
            logger.info(f"- {tool.get('name', '未知')}: {tool.get('description', '无描述')}")

        # ============ 测试1: 查询指定日期天气 ============
        sql = "SELECT * FROM weather_data WHERE city = '北京' AND fx_date = '2025-11-12'"
        # 通过MCP工具执行SQL查询
        result = await client.call_tool("query_weather", sql=sql)
        logger.info(f"指定日期天气查询结果：{result}")
        # 解析结果为Python对象以便日志打印
        result_data = json.loads(result) if isinstance(result, str) else result
        logger.info(f"指定日期天气结果：{result_data}")

        # ============ 测试2: 查询未来5天天气，限制返回2条 ============
        sql_range = "SELECT * FROM weather_data WHERE city = '北京' AND fx_date BETWEEN '2025-11-12' AND '2025-11-17' limit 2"
        # 执行MCP工具进行SQL范围查询
        result_range = await client.call_tool("query_weather", sql=sql_range)
        logger.info(f"天气范围查询结果：{result_range}")
        # 处理返回结果
        result_range_data = json.loads(result_range) if isinstance(result_range, str) else result_range
        logger.info(f"天气范围查询结果：{result_range_data}")

    except Exception as e:
        # 捕获并输出测试过程中的所有异常
        logger.error(f"天气 MCP 测试出错：{str(e)}", exc_info=True)
    finally:
        # 无论异常与否，都关闭MCP客户端连接
        await client.close()


async def main():
    # 运行天气MCP测试主流程
    await test_weather_mcp()


if __name__ == "__main__":
    # 程序入口：异步运行主函数
    asyncio.run(main())

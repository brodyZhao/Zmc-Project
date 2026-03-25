import asyncio
import json

from python_a2a.mcp import MCPClient

async def test_ticket_mcp():
    try:
        client = MCPClient("http://localhost:8001")

        try:
            result_flights = await client.call_tool(
                "query_tickets",
                sql="SELECT * FROM flight_tickets WHERE departure_city = '上海' AND arrival_city = '北京' AND DATE(departure_time) = '2025-10-28' AND cabin_type = '公务舱'"
            )
            result_flights_data = json.loads(result_flights) if isinstance(result_flights, str) else result_flights
            print(f"机票查询结果：{result_flights_data}")

            result_trains = await client.call_tool(
                "query_tickets",
                sql="SELECT * FROM train_tickets WHERE departure_city = '北京' AND arrival_city = '上海' AND DATE(departure_time) = '2025-09-13' AND seat_type = '二等座'"
            )
            result_trains_data = json.loads(result_trains) if isinstance(result_trains, str) else result_trains
            print(f"火车票查询结果：{result_trains_data}")

            result_concerts = await client.call_tool(
                "query_tickets",
                sql="SELECT * FROM concert_tickets WHERE city = '北京' AND artist = '刀郎' AND DATE(start_time) = '2025-10-31' AND ticket_type = '看台'"
            )
            result_concerts_data = json.loads(result_concerts) if isinstance(result_concerts, str) else result_concerts
            print(f"演唱会票查询结果：{result_concerts_data}")

        except Exception as e:
            print(f"票务 MCP 测试出错：{str(e)}")
    except Exception as e:
        print(f"连接或会话初始化时发生错误: {e}")
        print("请确认服务端脚本已启动并运行在 http://localhost:8001")


if __name__ == "__main__":
    asyncio.run(test_ticket_mcp())

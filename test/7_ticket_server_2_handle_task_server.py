#!/usr/bin/env_log.log python
"""
Ticket Query A2A Server with LangChain SQL Generation
优化：处理带代码块的LLM输出，正确解析type和SQL；返回用户友好文本结果（参考weather_server.py逻辑）。
"""

import json
import asyncio
import re

sys.path.append('c:\\Users\\86150\\Desktop\\NPU\\agent')
from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState
from python_a2a.mcp import MCPClient
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import colorlog
import logging
from SmartVoyage.config import Config
from datetime import datetime, timedelta
import pytz

# 设置彩色日志
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
    log_colors={'INFO': 'green', 'ERROR': 'red'}
))
logger = colorlog.getLogger()
logger.addHandler(handler)
logger.setLevel(colorlog.INFO)

def initialize_llm():
    """初始化 LLM"""
    conf = Config()
    try:
        return ChatOpenAI(
            model=conf.model_name,
            api_key=conf.api_key,
            base_url=conf.api_url,
            temperature=0.7,
            streaming=True,
        )
    except Exception as e:
        logger.error(f"LLM 初始化失败: {str(e)}")
        raise

def main():
    # 定义数据库 schema
    database_schema_string = """
    CREATE TABLE IF NOT EXISTS train_tickets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        departure_city VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
        arrival_city VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
        departure_time DATETIME NOT NULL,
        arrival_time DATETIME NOT NULL,
        train_number VARCHAR(20) NOT NULL,
        seat_type VARCHAR(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
        total_seats INT NOT NULL,
        remaining_seats INT NOT NULL,
        price DECIMAL(10, 2) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY unique_train (departure_time, train_number)
    );

    CREATE TABLE IF NOT EXISTS flight_tickets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        departure_city VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
        arrival_city VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
        departure_time DATETIME NOT NULL,
        arrival_time DATETIME NOT NULL,
        flight_number VARCHAR(20) NOT NULL,
        cabin_type VARCHAR(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
        total_seats INT NOT NULL,
        remaining_seats INT NOT NULL,
        price DECIMAL(10, 2) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY unique_flight (departure_time, flight_number)
    );

    CREATE TABLE IF NOT EXISTS concert_tickets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        artist VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
        city VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
        venue VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
        start_time DATETIME NOT NULL,
        end_time DATETIME NOT NULL,
        ticket_type VARCHAR(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
        total_seats INT NOT NULL,
        remaining_seats INT NOT NULL,
        price DECIMAL(10, 2) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY unique_concert (start_time, artist, ticket_type)
    );
    """

    # 优化 SQL 提示模板：添加缺失字段到SELECT（如train_number, flight_number, artist）
    sql_prompt = ChatPromptTemplate.from_template(
        """
系统提示：你是一个专业的票务SQL生成器，根据对话历史：
1. 分类查询类型（train: 火车/高铁, flight: 机票, concert: 演唱会），输出：{{"type": "train/flight/concert"}}
2. 根据分类，生成对应表的 SELECT 语句，仅查询指定字段：
   - train_tickets: id, departure_city, arrival_city, departure_time, arrival_time, train_number, seat_type, price, remaining_seats
   - flight_tickets: id, departure_city, arrival_city, departure_time, arrival_time, flight_number, cabin_type, price, remaining_seats
   - concert_tickets: id, artist, city, venue, start_time, end_time, ticket_type, price, remaining_seats
3. 如果无法分类或缺少必要信息，输出：{{"status": "input_required", "message": "请提供票务类型（如火车票、机票、演唱会）和必要信息（如城市、日期）。"}} 
4. 无结果不编造，输出纯 SQL。
5. 不要包含 ```json 或 ```sql

schema：
{schema}

示例：
- 对话: user: 火车票 北京 上海 2025-07-31 硬卧
  输出: 
  {{"type": "train"}}
  SELECT id, departure_city, arrival_city, departure_time, arrival_time, train_number, seat_type, price, remaining_seats FROM train_tickets WHERE departure_city = '北京' AND arrival_city = '上海' AND DATE(departure_time) = '2025-07-31' AND seat_type = '硬卧'
- 对话: user: 机票 上海 广州 2025-09-11 头等舱
  输出: 
  {{"type": "flight"}}
  SELECT id, departure_city, arrival_city, departure_time, arrival_time, flight_number, cabin_type, price, remaining_seats FROM flight_tickets WHERE departure_city = '上海' AND arrival_city = '广州' AND DATE(departure_time) = '2025-09-11' AND cabin_type = '头等舱'
- 对话: user: 演唱会 北京 刀郎 2025-08-23 看台
  输出: 
  {{"type": "concert"}}
  SELECT id, artist, city, venue, start_time, end_time, ticket_type, price, remaining_seats FROM concert_tickets WHERE city = '北京' AND artist = '刀郎' AND DATE(start_time) = '2025-08-23' AND ticket_type = '看台'
- 对话: user: 火车票
  输出: 
  {{"type": "train"}}
  SELECT id, departure_city, arrival_city, departure_time, arrival_time, train_number, seat_type, price, remaining_seats FROM train_tickets WHERE DATE(departure_time) = '2025-07-31' ORDER BY price ASC LIMIT 5
- 对话: user: 你好
  输出: {{"status": "input_required", "message": "请提供票务类型（如火车票、机票、演唱会）和必要信息（如城市、日期）。"}} 

对话历史: {conversation}
当前日期: {current_date} (Asia/Shanghai)
        """
    )

    # Agent 卡片定义
    agent_card = AgentCard(
        name="Ticket Query Assistant",
        description="基于 LangChain 提供票务查询服务的助手",
        url="http://localhost:5006",
        version="1.0.4",
        capabilities={"streaming": True, "memory": True},
        skills=[
            AgentSkill(
                name="execute ticket query",
                description="根据客户端提供的输入执行票务查询，返回数据库结果，支持自然语言输入",
                examples=["火车票 北京 上海 2025-07-31 硬卧", "机票 北京 上海 2025-07-31 经济舱", "演唱会 北京 刀郎 2025-08-23 看台"]
            )
        ]
    )

    # 票务查询服务器类
    class TicketQueryServer(A2AServer):
        def __init__(self):
            super().__init__(agent_card=agent_card)
            self.llm = initialize_llm()
            self.sql_prompt = sql_prompt
            self.schema = database_schema_string

        def generate_sql_query(self, conversation: str) -> dict:
            """根据对话历史生成 SQL 或追问 JSON"""
            try:
                current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
                chain = self.sql_prompt | self.llm
                # 调用 LLM生成sql,增加当前的current_date目的是解决时间问题，有可能用户会说"明天"  ，conversation就是用户的输入，即query
                output = chain.invoke({"schema": self.schema, "conversation": conversation, "current_date": current_date}).content.strip()
                logger.info(f"原始 LLM 输出: {output}")

                # 解析 LLM 输出，处理可能的代码块标记
                lines = output.split('\n')
                type_line = lines[0].strip()
                if type_line.startswith('```json'):
                    type_line = lines[1].strip()
                    sql_lines = lines[3:-1] if lines[-1].strip() == '```' else lines[3:]
                else:
                    sql_lines = lines[1:] if len(lines) > 1 else []

                # 提取 type 和 SQL
                if type_line.startswith('{"type":'):
                    query_type = json.loads(type_line)["type"]
                    sql_query = ' '.join([line.strip() for line in sql_lines if line.strip() and not line.startswith('```')])
                    logger.info(f"分类类型: {query_type}, 生成的 SQL: {sql_query}")
                    return {"status": "sql", "type": query_type, "sql": sql_query}
                elif type_line.startswith('{"status": "input_required"'):
                    return json.loads(type_line)
                else:
                    logger.error(f"无效的 LLM 输出格式: {output}")
                    return {"status": "input_required", "message": "无法解析查询类型或SQL，请提供更明确的信息。"}
            except Exception as e:
                logger.error(f"SQL 生成失败: {str(e)}")
                return {"status": "input_required", "message": "查询无效，请提供票务相关信息。"}

        def handle_task(self, task):
            """处理任务：提取输入，生成 SQL，调用 MCP，返回用户友好文本结果（参考weather_server.py逻辑）"""
            message_data = task.message or {}
            content = message_data.get("content", {})
            conversation = content.get("text", "") if isinstance(content, dict) else ""
            logger.info(f"对话历史: {conversation}")

            try:
                # 生成 SQL
                gen_result = self.generate_sql_query(conversation)
                # 处理结果,根据大模型生成的结果进行不同处理
                if gen_result["status"] == "input_required":
                    task.status = TaskStatus(
                        state=TaskState.INPUT_REQUIRED,
                        message={"role": "agent", "content": {"text": gen_result["message"]}}
                    )
                    return task
                # 生成可用的sql以及对应sql的对应应用场景
                sql_query = gen_result["sql"]
                query_type = gen_result["type"]
                logger.info(f"执行 SQL 查询: {sql_query} (类型: {query_type})")

                # 调用 MCP，线程安全异步执行，初始化mcp客户端
                client = MCPClient("http://localhost:6002")
                loop = asyncio.get_event_loop_policy().new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    ticket_result = loop.run_until_complete(client.call_tool("query_tickets", sql=sql_query))
                finally:
                    loop.close()
                # 处理结果,处理mcp返回的json数据
                response = json.loads(ticket_result) if isinstance(ticket_result, str) else ticket_result
                logger.info(f"MCP 返回: {response}")

                # 处理无结果
                if response.get("status") == "no_data":
                    response_text = f"{response['message']} 如果需要其他日期，请补充。"
                else:
                    data = response.get("data", [])
                    response_text = ""
                    for d in data:
                        if query_type == "train":
                            response_text += f"{d['departure_city']} 到 {d['arrival_city']} {d['departure_time']}: 车次 {d['train_number']}，{d['seat_type']}，票价 {d['price']}元，剩余 {d['remaining_seats']} 张\n"
                        elif query_type == "flight":
                            response_text += f"{d['departure_city']} 到 {d['arrival_city']} {d['departure_time']}: 航班 {d['flight_number']}，{d['cabin_type']}，票价 {d['price']}元，剩余 {d['remaining_seats']} 张\n"
                        elif query_type == "concert":
                            response_text += f"{d['city']} {d['start_time']}: {d['artist']} 演唱会，{d['ticket_type']}，场地 {d['venue']}，票价 {d['price']}元，剩余 {d['remaining_seats']} 张\n"

                    if not response_text:
                        response_text = "无结果。如果需要其他日期，请补充。"

                task.artifacts = [{"parts": [{"type": "text", "text": response_text.strip()}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
            except Exception as e:
                logger.error(f"查询失败: {str(e)}")
                task.artifacts = [{"parts": [{"type": "text", "text": f"查询失败: {str(e)} 请重试或提供更多细节。"}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)

            return task

    # 创建并运行服务器
    ticket_server = TicketQueryServer()

    print("\n=== 服务器信息 ===")
    print(f"名称: {ticket_server.agent_card.name}")
    print(f"描述: {ticket_server.agent_card.description}")
    print("\n技能:")
    for skill in ticket_server.agent_card.skills:
        print(f"- {skill.name}: {skill.description}")

    run_server(ticket_server, host="0.0.0.0", port=5006)

if __name__ == "__main__":
    import sys
    try:
        main()
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n✅ 程序被用户中断")
        sys.exit(0)
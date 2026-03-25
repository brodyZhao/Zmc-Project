#!/usr/bin/env_log.log python
"""
Ticket Query A2A Server with LangChain SQL Generation
优化：处理带代码块的LLM输出，正确解析type和SQL；返回用户友好文本结果（参考weather_server.py逻辑）。
"""

import json
import asyncio
import re
from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState
from python_a2a.mcp import MCPClient
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import colorlog
from config import Config
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
llm=initialize_llm()

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



def generate_sql_query(conversation: str) -> dict:
    """根据对话历史生成 SQL 或追问 JSON"""
    try:
        current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
        chain = sql_prompt | llm
        output = chain.invoke({"schema": database_schema_string, "conversation": conversation, "current_date": current_date}).content.strip()
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

if __name__ == '__main__':
    response=generate_sql_query("火车票 北京 上海 2025-09-14 二等座")
    print(response)



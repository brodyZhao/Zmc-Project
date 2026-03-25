"""
本模块主要功能：票务查询A2A服务器，基于LangChain和大模型自动生成SQL查询，实现智能票务信息检索服务。
特点：
- 支持多轮自然语言票务查询，自动用Schema生成SQL语句
- 能自动处理大模型输出中的代码块、识别TYPE和SQL
- 查询结果转换为用户友好的文本描述
- 接口和结果友好兼容A2A协议（实现方式参考weather_server.py）
"""

import json  # 导入JSON模块，用于解析和生成JSON数据
import asyncio  # 导入asyncio模块，用于异步编程和事件循环管理
import re  # 导入re模块，用于正则表达式处理（虽未直接使用，但导入以备）
import sys
from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, \
    TaskState  # 从python_a2a导入A2A服务器核心类和函数，用于构建代理服务器
from python_a2a.mcp import MCPClient
from langchain_openai import ChatOpenAI  # 从langchain_openai导入ChatOpenAI，用于创建OpenAI兼容的聊天模型
from langchain_core.prompts import ChatPromptTemplate  # 从langchain_core.prompts导入ChatPromptTemplate，用于构建提示模板
import colorlog  # 导入colorlog模块，用于彩色日志输出

sys.path.append('c:\\Users\\86150\\Desktop\\NPU\\agent')
from SmartVoyage.config import Config  # 从自定义模块导入Config类，用于加载配置参数如API密钥
from datetime import datetime  # 从datetime导入datetime和timedelta，用于日期时间计算
import pytz  # 导入pytz模块，用于时区处理

# 设置彩色日志
# 创建日志流处理器，将日志信息输出到标准输出（控制台）
handler = colorlog.StreamHandler()

# 设置日志格式：带有颜色、时间戳、日志级别和消息内容
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
    log_colors={'INFO': 'green', 'ERROR': 'red'}  # 指定不同日志级别的颜色

))

# 获取全局日志记录器
logger = colorlog.getLogger()

# 将流处理器添加到日志记录器（使日志输出生效）
logger.addHandler(handler)

# 设置日志输出级别为INFO，仅输出INFO及以上级别的日志信息
logger.setLevel(colorlog.INFO)

# 实例化配置类对象
conf = Config()

# 实例化聊天模型对象
llm = ChatOpenAI(
    model=conf.model_name,
    api_key=conf.api_key,
    base_url=conf.api_url,
    temperature=0.7,
    streaming=True)

# =========================
# 1. 数据库schema定义
# =========================
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

# =========================
# 2. SQL生成Prompt模板
# =========================
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


# =========================
# 4. AgentCard定义
# =========================
agent_card = AgentCard(
    name="Ticket Query Assistant",  # 代理助手名称
    description="基于 LangChain 提供票务查询服务的助手",
    url="http://localhost:5006",
    version="1.0.4",
    capabilities={"streaming": True, "memory": True},  # streaming: 是否支持流式输出, memory: 是否具备对话记忆
    skills=[
        AgentSkill(
            name="execute ticket query",  # 技能名称
            description="根据客户端提供的输入执行票务查询，返回数据库结果，支持自然语言输入。",
            examples=[
                "火车票 北京 上海 2025-07-31 硬卧",  # 火车票例
                "机票 北京 上海 2025-07-31 经济舱",  # 机票例
                "演唱会 北京 刀郎 2025-08-23 看台"  # 演唱会例
            ]
        )
    ]
)


# =========================
# 5. 票务查询服务器主类
# =========================
class TicketQueryServer(A2AServer):
    def __init__(self):
        """
        初始化票务查询服务器
        ---
        参数:
            self: TicketQueryServer 实例
        属性初始化:
            self.llm        : LLM实例，用于生成SQL
            self.sql_prompt : SQL生成prompt
            self.schema     : 查询的数据库schema（字符串）
        """
        super().__init__(agent_card=agent_card)
        self.llm = llm
        self.sql_prompt = sql_prompt
        self.schema = database_schema_string

    def generate_sql_query(self, conversation: str) -> dict:
        """
        根据对话历史生成SQL或追问JSON
        ---
        参数:
            conversation : str
                对话历史, 一段自然语言，用户输入的票务查询需求
        返回:
            dict
                SQL生成结构，形式如下:
                    - {"status": "sql", "type": <train/flight/concert>, "sql": <SQL查询语句>}
                    - 或 {"status": "input_required", "message": <string>}
        错误处理:
            返回 {"status": "input_required", "message": ...}（发生异常或LLM输出不合格式时）
        """
        # 生成SQL查询的核心方法
        try:
            # 获取当前日期（用于SQL prompt上下文，时区为北京时间）
            current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
            # 构建LangChain chain，组合prompt与llm
            chain = self.sql_prompt | self.llm
            # 调用chain，传入schema、对话、当前日期
            output = chain.invoke({
                "schema": self.schema,
                "conversation": conversation,
                "current_date": current_date
            }).content.strip()
            # logger.info(f"原始 LLM 输出: {output}")

            # 解析 LLM 返回：兼容带代码块和非代码块（llm输出有时包裹```json和```）
            lines = output.split('\n')
            # logger.info(f"分割输出{lines}")
            type_line = lines[0].strip()
            logger.info(f"LLM 输出类型行: {type_line}")

            # 如果大模型输出的格式不是要求格式, 需要进行以下处理
            if type_line.startswith('```json'):
                # LLM输出以```json开头：第2行为类型说明，SQL代码为第4行及以后
                type_line = lines[1].strip()
                # logger.info(f"LLM 输出类型行: {type_line}")
                # 代码结尾如果带```，去掉这一行
                sql_lines = lines[3:-1] if lines[-1].strip() == '```' else lines[3:]
            else:
                # 普通输出：第1行为类型，第2行及之后为SQL/追问消息
                sql_lines = lines[1:] if len(lines) > 1 else []
                # logger.info(f"SQL 输出: {sql_lines}")

            # 判断输出对象类型
            if type_line.startswith('{"type":'):
                # json对象，解析类型
                query_type = json.loads(type_line)["type"]
                # logger.info(f"分类类型: {query_type}")

                # 拼接SQL语句（去除空行和换行符、去除可能的代码块分隔符）
                sql_query = ' '.join([
                    line.strip() for line in sql_lines
                    if line.strip() and not line.startswith('```')
                ])
                logger.info(f"分类类型: {query_type}, 生成的 SQL: {sql_query}")
                return {"status": "sql", "type": query_type, "sql": sql_query}
            elif type_line.startswith('{"status": "input_required"'):
                # 追问型，用于缺参数信息
                # logger.info(f"追问类型: {type_line}")
                return json.loads(type_line)
            else:
                # 其它异常情况，无法解析
                logger.error(f"无效的 LLM 输出格式: {output}")
                return {"status": "input_required", "message": "无法解析查询类型或SQL，请提供更明确的信息。"}
        except Exception as e:
            # LLM生成或输出解析失败，返回需要补充信息的结构
            logger.error(f"SQL 生成失败: {str(e)}")
            return {"status": "input_required", "message": "查询无效，请提供票务相关信息。"}

    def handle_task(self, task):
        """
        处理接收到的查询任务
        ---
        参数:
            task : (A2A Task对象)
                代理A2A框架传入的任务对象，包含用户查询信息。
        流程:
            1. 提取对话内容
            2. 调用 generate_sql_query 生成SQL
            3. 若需追问，任务状态改为INPUT_REQUIRED并返回消息
            4. 查询MCP(数据库后端)：根据SQL查票/演唱会
            5. 组织用户友好返回文本
            6. 设置任务产物并完成
        返回:
            修改后的task对象（含响应产物和状态）
        错误情况:
            产生友好错误信息，设置在 artifacts，并完成任务。
        """
        # 从A2A任务对象中提取用户消息内容（可能为空）
        message_data = task.message or {}
        logger.info(f"用户消息: {message_data}")
        content = message_data.get("content", {})
        logger.info(f"用户消息内容: {content}")
        conversation = content.get("text", "") if isinstance(content, dict) else ""
        logger.info(f"对话历史: {conversation}")

        try:
            # 第一步：调用SQL生成逻辑
            gen_result = self.generate_sql_query(conversation)
            logger.info(f"SQL 生成结果: {gen_result}")
            if gen_result["status"] == "input_required":
                # 需要用户补充信息，设置为待补充状态并返回
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={"role": "agent", "content": {"text": gen_result["message"]}}
                )
                return task

            # 获得SQL和查询类型
            sql_query = gen_result["sql"]
            query_type = gen_result["type"]
            logger.info(f"执行 SQL 查询: {sql_query} (类型: {query_type})")

            # 初始化MCPClient对象，连接票务MCP服务
            client = MCPClient("http://localhost:8001")  # MCP票务数据库工具
            # 创建独立的事件循环(防止协程阻塞/跨线程问题)
            loop = asyncio.get_event_loop_policy().new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                # 调用query_tickets工具，执行实际SQL查询
                ticket_result = loop.run_until_complete(
                    client.call_tool("query_tickets", sql=sql_query)
                )
                logger.info(f"MCP查询结果: {ticket_result}")
            finally:
                loop.close()

            # MCP响应结构示例
            # response: {"status": "ok"|"no_data", "message": "...", "data": [dict, ...]}
            response = json.loads(ticket_result) if isinstance(ticket_result, str) else ticket_result
            logger.info(f"MCP 返回: {response}")

            # 第三步：组织用户友好返回
            if response.get("status") == "no_data":
                # 没查到数据，直接用MCP返回的message
                response_text = f"{response['message']} 如果需要其他日期，请补充。"
            else:
                data = response.get("data", [])
                response_text = ""
                for d in data:
                    if query_type == "train":
                        # 火车票格式拼接, 显示主要字段
                        response_text += (
                            f"{d['departure_city']} 到 {d['arrival_city']} {d['departure_time']}: "
                            f"车次 {d['train_number']}，{d['seat_type']}，票价 {d['price']}元，剩余 {d['remaining_seats']} 张\n"
                        )
                    elif query_type == "flight":
                        # 机票格式拼接
                        response_text += (
                            f"{d['departure_city']} 到 {d['arrival_city']} {d['departure_time']}: "
                            f"航班 {d['flight_number']}，{d['cabin_type']}，票价 {d['price']}元，剩余 {d['remaining_seats']} 张\n"
                        )
                    elif query_type == "concert":
                        # 演唱会格式拼接
                        response_text += (
                            f"{d['city']} {d['start_time']}: {d['artist']} 演唱会，{d['ticket_type']}，场地 {d['venue']}，票价 {d['price']}元，剩余 {d['remaining_seats']} 张\n"
                        )
                # 如果没有结果条目，显示无结果
                if not response_text:
                    response_text = "无结果。如果需要其他日期，请补充。"

            # 设置产物供A2A框架协议返回
            task.artifacts = [{"parts": [{"type": "text", "text": response_text.strip()}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)
        except Exception as e:
            # 捕获全流程异常，产物返回错误提示文本
            logger.error(f"查询失败: {str(e)}")
            task.artifacts = [{"parts": [{"type": "text", "text": f"查询失败: {str(e)} 请重试或提供更多细节。"}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)

        return task


if __name__ == "__main__":
    # 实例化agent server对象
    ticket_server = TicketQueryServer()
    # # 调用生成SQL逻辑的方法
    # ticket_server.generate_sql_query("查询北京到上海的火车票")

    print("\n=== 服务器信息 ===")
    print(f"名称: {ticket_server.agent_card.name}")
    print(f"描述: {ticket_server.agent_card.description}")
    print("\n技能:")
    for skill in ticket_server.agent_card.skills:
        print(f"- {skill.name}: {skill.description}")

    run_server(ticket_server, host="0.0.0.0", port=5006)

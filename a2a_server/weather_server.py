"""
本模块主要功能：天气Agent服务器，利用LLM生成天气数据库的SQL查询，支持追问（输入槽缺失时追问）与默认查询能力。
特点：动态日期推断、异常容错、线程安全异步MCP工具服务调用、逐步对话记忆。
"""

import json  # 用于解析/生成JSON数据
import asyncio  # 支持异步协作与事件循环管理
import sys
from python_a2a import (
    A2AServer,
    run_server,
    AgentCard,
    AgentSkill,
    TaskStatus,
    TaskState,
)  # 导入A2A代理与任务相关核心类/方法
from python_a2a.mcp import MCPClient  # MCP工具服务客户端
from langchain_openai import ChatOpenAI  # OpenAI聊天模型（LangChain适配）
from langchain_core.prompts import ChatPromptTemplate  # LangChain聊天提示模板
import colorlog  # 彩色日志输出库

sys.path.append('c:\\Users\\86150\\Desktop\\NPU\\agent')
from SmartVoyage.config import Config  # 配置项载入（API KEY/模型/地址等）
from datetime import datetime, timedelta  # 日期时间工具
import pytz  # 时区处理

# ==============================
# 日志配置区
# ==============================
handler = colorlog.StreamHandler()  # 构造日志流处理器
handler.setFormatter(
    colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
        log_colors={
            "INFO": "green",
            "ERROR": "red",
        },
    )
)
logger = colorlog.getLogger()
logger.addHandler(handler)
logger.setLevel(colorlog.INFO)  # 只记录INFO及以上消息

# ========== 1. 初始化大模型/配置 ==========
conf = Config()  # 载入配置项（模型名称、API KEY、API基础URL等）

llm = ChatOpenAI(
    model=conf.model_name,
    api_key=conf.api_key,
    base_url=conf.api_url,
    temperature=0,  # 输出确定性，调整向零
    streaming=True,  # 启用流式模式
)

# ========== 2. 数据库schema字符串 ==========
database_schema_string = """
CREATE TABLE IF NOT EXISTS weather_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    city VARCHAR(50) NOT NULL COMMENT '城市名称',
    fx_date DATE NOT NULL COMMENT '预报日期',
    sunrise TIME COMMENT '日出时间',
    sunset TIME COMMENT '日落时间',
    moonrise TIME COMMENT '月升时间',
    moonset TIME COMMENT '月落时间',
    moon_phase VARCHAR(20) COMMENT '月相名称',
    moon_phase_icon VARCHAR(10) COMMENT '月相图标代码',
    temp_max INT COMMENT '最高温度',
    temp_min INT COMMENT '最低温度',
    icon_day VARCHAR(10) COMMENT '白天天气图标代码',
    text_day VARCHAR(20) COMMENT '白天天气描述',
    icon_night VARCHAR(10) COMMENT '夜间天气图标代码',
    text_night VARCHAR(20) COMMENT '夜间天气描述',
    wind360_day INT COMMENT '白天风向360角度',
    wind_dir_day VARCHAR(20) COMMENT '白天风向',
    wind_scale_day VARCHAR(10) COMMENT '白天风力等级',
    wind_speed_day INT COMMENT '白天风速 (km/h)',
    wind360_night INT COMMENT '夜间风向360角度',
    wind_dir_night VARCHAR(20) COMMENT '夜间风向',
    wind_scale_night VARCHAR(10) COMMENT '夜间风力等级',
    wind_speed_night INT COMMENT '夜间风速 (km/h)',
    precip DECIMAL(5,1) COMMENT '降水量 (mm)',
    uv_index INT COMMENT '紫外线指数',
    humidity INT COMMENT '相对湿度 (%)',
    pressure INT COMMENT '大气压强 (hPa)',
    vis INT COMMENT '能见度 (km)',
    cloud INT COMMENT '云量 (%)',
    update_time DATETIME COMMENT '数据更新时间',
    UNIQUE KEY unique_city_date (city, fx_date)
) ENGINE=INNODB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='天气数据表';
    """

# ========== 3. LLM SQL生成PROMPT模板 ==========
# 用于LangChain SQL生成提醒上下文，用于多轮对话槽位抽取
sql_prompt = ChatPromptTemplate.from_template(
    """
系统提示：你是一个专业的天气SQL生成器，仅基于weather_data表生成SELECT语句。
- 无结果不编造。
- 输出纯SQL

schema：
{schema}

示例：
- 对话: user: 北京 2025-07-30
输出: SELECT city, fx_date, temp_max, temp_min, text_day, text_night, humidity, wind_dir_day, precip FROM weather_data WHERE city = '北京' AND fx_date = '2025-07-30'
- 对话: user: 上海未来3天
输出: SELECT city, fx_date, temp_max, temp_min, text_day, text_night, humidity, wind_dir_day, precip FROM weather_data WHERE city = '上海' AND fx_date BETWEEN '2025-07-30' AND '2025-08-01' ORDER BY fx_date
- 对话: user: 你好
输出: {{"status": "input_required", "message": "请提供城市和日期，例如 '北京 2025-07-30'。"}}
- 对话: user: 今天有什么好吃的
输出: {{"status": "input_required", "message": "请提供天气相关查询，包括城市和日期。"}}
- 对话: user: 今天\nassistant: 请提供城市。\nuser: 北京
输出: SELECT city, fx_date, temp_max, temp_min, text_day, text_night, humidity, wind_dir_day, precip FROM weather_data WHERE city = '北京' AND fx_date = '2025-07-30'
- 对话: user: 北京明天\nassistant: [result]\nuser: 明天呢
输出: {{"status": "input_required", "message": "请澄清'明天'的具体含义，或提供日期。"}}
- 对话: user: 北京明天
输出: SELECT city, fx_date, temp_max, temp_min, text_day, text_night, humidity, wind_dir_day, precip FROM weather_data WHERE city = '北京' AND fx_date = '2025-07-31'
- 对话: user: 北京明天\nuser: 后天呢
输出: SELECT city, fx_date, temp_max, temp_min, text_day, text_night, humidity, wind_dir_day, precip FROM weather_data WHERE city = '北京' AND fx_date = '2025-08-01'

对话历史: {conversation}
当前日期: {current_date} (Asia/Shanghai)
    """
)

# ========== 4. agent元数据卡片 ==========
agent_card = AgentCard(
    name="Weather Query Assistant",  # 代理助手名称
    description="基于LangChain提供天气查询服务的助手",  # 助手功能简介
    url="http://localhost:5005",  # 服务URL地址
    version="1.0.0",  # 版本号
    capabilities={  # 能力说明
        "streaming": True,  # 是否支持流式输出
        "memory": True  # 是否具备对话记忆
    },
    skills=[
        AgentSkill(
            name="execute weather query",  # 技能名称
            description="执行天气查询，返回天气数据库结果，支持自然语言输入",  # 技能描述
            examples=[
                "北京 2025-07-30 天气",
                "上海未来5天",
                "今天天气如何",
            ],  # 技能调用示例
        )
    ],
)


# ========== 5.天气查询主服务类 ==========

class WeatherQueryServer(A2AServer):
    """
    天气查询A2A服务器
    继承A2AServer，自动兼容标准A2A协议和任务分派
    属性:
        llm (ChatOpenAI): 聊天大模型实例
        sql_prompt (ChatPromptTemplate): SQL生成prompt模板
        schema (str): 数据库schema描述字符串
    """

    def __init__(self):
        """
        WeatherQueryServer构造函数
        初始化agent信息/大模型/Prompt/Schema
        """
        super().__init__(agent_card=agent_card)
        self.llm = llm
        self.sql_prompt = sql_prompt
        self.schema = database_schema_string

    def generate_sql_query(self, conversation: str) -> dict:
        """
        基于人机对话历史生成SQL查询语句或追问消息

        参数:
            conversation (str): 用户与机器人的多轮对话文本
        返回:
            dict:
              - 若槽位齐全，返回{'status': 'sql', 'sql': SQL语句字符串}
              - 若槽位缺失，返回{'status': 'input_required', 'message': 追问文本}
        """
        try:
            # 获取当前日期，时区为Asia/Shanghai，用于SQL生成逻辑
            current_date = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d")
            # 构建Prompt到大模型的处理链
            chain = self.sql_prompt | self.llm
            # 调用chain.invoke方法，把conversation和当前日期传入模型
            output = chain.invoke({
                "schema": self.schema,
                "conversation": conversation,
                "current_date": current_date
            }).content.strip()
            # logger.info(f"SQL生成结果1: {output}")
            # 如果模型返回的是JSON格式（输入槽位不全时追问），则解包
            if output.startswith("{"):
                # logger.info(f"SQL生成结果2: {json.loads(output)}")
                return json.loads(output)
            # 否则直接按SQL查询语句返回
            return {"status": "sql", "sql": output}
        except Exception as e:
            logger.error(f"SQL生成失败: {str(e)}")
            # 如果出错，通知用户输入无效
            return {
                "status": "input_required",
                "message": "查询无效，请提供城市和日期。",
            }

    def handle_task(self, task):
        """
        处理A2A任务主入口——解析输入、生成SQL/追问、MCP查询、格式化输出
        参数:
            task (A2ATask): 输入A2A任务对象
        返回:
            task (A2ATask): 处理后任务对象（含产物、状态）
        """
        # 获取消息体，兼容空输入
        message_data = task.message or {}
        content = message_data.get("content", {})
        conversation = content.get("text", "") if isinstance(content, dict) else ""
        logger.info(f"对话历史: {conversation}")

        try:
            # ============== SQL生成阶段 ==============
            gen_result = self.generate_sql_query(conversation)
            logger.info(f"SQL生成结果: {gen_result}")
            if gen_result["status"] == "input_required":
                # 若模型需要更多槽位信息（如缺少日期城市），设置INPUT_REQUIRED, 触发补充追问
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={
                        "role": "agent",
                        "content": {"text": gen_result["message"]},
                    },
                )
                return task

            # ============== 执行MCP SQL查询阶段 ==============
            sql_query = gen_result["sql"]
            logger.info(f"生成的SQL查询: {sql_query}")

            # 初始化MCPClient对象，连接天气MCP服务
            client = MCPClient("http://localhost:6001")  # MCP天气数据库工具
            # 创建独立的事件循环(防止协程阻塞/跨线程问题)
            loop = asyncio.get_event_loop_policy().new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                # 调用query_weather工具，执行实际SQL查询
                weather_result = loop.run_until_complete(
                    client.call_tool("query_weather", sql=sql_query)
                )
                logger.info(f"MCP查询结果: {weather_result}")
            finally:
                loop.close()
            # 解析MCP返回的响应数据
            response = json.loads(weather_result) if isinstance(weather_result, str) else weather_result
            logger.info(f"MCP 响应: {response}")
            if response.get("status") == "no_data":
                # 查询无数据，提示“未找到天气数据...”
                response_text = f"{response['message']} 如果需要其他日期，请补充。"
                logger.info(f'response_text: {response_text}')
            else:
                data = response.get("data", [])
                logger.info(f"查询结果: {data}")
                # 拼接多条天气查询结果为多行人类可读文本
                response_text = "\n".join(
                    [
                        f"{d['city']} {d['fx_date']}: {d['text_day']}（夜间 {d['text_night']}），温度 {d['temp_min']}-{d['temp_max']}°C，湿度 {d['humidity']}%，风向 {d['wind_dir_day']}，降水 {d['precip']}mm"
                        for d in data
                    ]
                )
            # 产物写入A2ATask.artifacts，供A2A协议回复用
            task.artifacts = [
                {"parts": [{"type": "text", "text": response_text}]}
            ]
            task.status = TaskStatus(state=TaskState.COMPLETED)

        except Exception as e:
            # 捕获全流程异常，产物返回错误提示文本
            logger.error(f"查询失败: {str(e)}")
            task.artifacts = [
                {
                    "parts": [
                        {
                            "type": "text",
                            "text": f"查询失败: {str(e)} 请重试或提供更多细节。",
                        }
                    ]
                }
            ]
            task.status = TaskStatus(state=TaskState.COMPLETED)
        return task


if __name__ == "__main__":
    weather_server = WeatherQueryServer()
    # # 调用generate_sql_query方法进行测试
    # weather_server.generate_sql_query("帮我查询北京今天的天气")

    print("\n=== 服务器信息 ===")
    print(f"名称: {weather_server.agent_card.name}")
    print(f"描述: {weather_server.agent_card.description}")
    print("\n技能:")
    for skill in weather_server.agent_card.skills:
        print(f"- {skill.name}: {skill.description}")

    # 启动A2A服务器，绑定0.0.0.0:5005端口
    run_server(
        weather_server, host="0.0.0.0", port=5005
    )

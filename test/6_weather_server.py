#!/usr/bin/env_log.log python
"""
Weather Query A2A Server with LangChain SQL Generation
"""
# 功能：天气Agent服务器，使用LLM生成SQL查询天气数据，支持追问和默认查询。鲁棒性：动态日期，异常处理，线程安全异步调用。

import json
import asyncio

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

def main():
    # 初始化LLM
    conf = Config()
    llm = ChatOpenAI(
        model=conf.model_name,
        api_key=conf.api_key,
        base_url=conf.api_url,
        temperature=0,
        streaming=True,
    )

    # 数据库 schema
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

    # 优化Prompt：基于整个对话历史提取槽位，如果缺少则追问，不默认查询多个城市，不得杜撰
    sql_prompt = ChatPromptTemplate.from_template(
        """
系统提示：你是一个专业的天气SQL生成器，仅基于weather_data表生成SELECT语句。
- 无结果不编造。
- 输出纯SQL

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

    # Agent卡片定义
    agent_card = AgentCard(
        name="Weather Query Assistant",
        description="基于LangChain提供天气查询服务的助手",
        url="http://localhost:5005",
        version="1.0.0",
        capabilities={"streaming": True, "memory": True},
        skills=[
            AgentSkill(
                name="execute weather query",
                description="执行天气查询，返回天气数据库结果，支持自然语言输入",
                examples=["北京 2025-07-30 天气", "上海未来5天", "今天天气如何"]
            )
        ]
    )

    # 天气查询服务器类
    class WeatherQueryServer(A2AServer):
        def __init__(self):
            super().__init__(agent_card=agent_card)
            self.llm = llm
            self.sql_prompt = sql_prompt
            self.schema = database_schema_string

        def generate_sql_query(self, conversation: str) -> dict:
            # 生成SQL或追问JSON
            try:
                current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
                chain = self.sql_prompt | self.llm
                output = chain.invoke({"conversation": conversation, "current_date": current_date}).content.strip()
                if output.startswith('{'):
                    return json.loads(output)
                return {"status": "sql", "sql": output}
            except Exception as e:
                logger.error(f"SQL生成失败: {str(e)}")
                return {"status": "input_required", "message": "查询无效，请提供城市和日期。"}

        def handle_task(self, task):
            # 处理任务：提取输入，生成SQL，调用MCP，格式化结果
            message_data = task.message or {}
            content = message_data.get("content", {})
            conversation = content.get("text", "") if isinstance(content, dict) else ""
            logger.info(f"对话历史: {conversation}")

            try:
                gen_result = self.generate_sql_query(conversation)
                if gen_result["status"] == "input_required":
                    # 追问逻辑
                    task.status = TaskStatus(state=TaskState.INPUT_REQUIRED, message={"role": "agent", "content": {"text": gen_result["message"]}})
                    return task

                sql_query = gen_result["sql"]
                logger.info(f"生成的SQL查询: {sql_query}")

                # 调用MCP，线程安全异步执行
                client = MCPClient("http://localhost:6001")
                loop = asyncio.get_event_loop_policy().new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    weather_result = loop.run_until_complete(client.call_tool("query_weather", sql=sql_query))
                finally:
                    loop.close()

                response = json.loads(weather_result) if isinstance(weather_result, str) else weather_result
                if response.get("status") == "no_data":
                    response_text = f"{response['message']} 如果需要其他日期，请补充。"
                else:
                    data = response.get("data", [])
                    response_text = "\n".join([f"{d['city']} {d['fx_date']}: {d['text_day']}（夜间 {d['text_night']}），温度 {d['temp_min']}-{d['temp_max']}°C，湿度 {d['humidity']}%，风向 {d['wind_dir_day']}，降水 {d['precip']}mm" for d in data])

                task.artifacts = [{"parts": [{"type": "text", "text": response_text}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
            except Exception as e:
                logger.error(f"查询失败: {str(e)}")
                task.artifacts = [{"parts": [{"type": "text", "text": f"查询失败: {str(e)} 请重试或提供更多细节。"}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)

            return task

    # 创建并运行服务器
    weather_server = WeatherQueryServer()

    print("\n=== 服务器信息 ===")
    print(f"名称: {weather_server.agent_card.name}")
    print(f"描述: {weather_server.agent_card.description}")
    print("\n技能:")
    for skill in weather_server.agent_card.skills:
        print(f"- {skill.name}: {skill.description}")

    run_server(weather_server, host="0.0.0.0", port=5005)

if __name__ == "__main__":
    import sys
    try:
        main()
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n✅ 程序被用户中断")
        sys.exit(0)
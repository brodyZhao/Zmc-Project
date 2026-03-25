#!/usr/bin/env_log.log python  # Shebang行，指定Python解释器（可能为自定义路径）
"""
Weather Query A2A Server with LangChain SQL Generation
"""  # 模块文档字符串，描述服务器功能
# 功能：天气Agent服务器，使用LLM生成SQL查询天气数据，支持追问和默认查询。鲁棒性：动态日期，异常处理，线程安全异步调用。

import json  # 导入JSON模块，用于解析和生成JSON数据
import asyncio  # 导入asyncio模块，用于异步编程和事件循环管理

sys.path.append('c:\\Users\\86150\\Desktop\\NPU\\agent')
from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState  # 从python_a2a导入A2A服务器核心类和函数，用于构建代理服务器
from python_a2a.mcp import MCPClient  # 从python_a2a.mcp导入MCPClient，用于调用MCP工具服务
from langchain_openai import ChatOpenAI  # 从langchain_openai导入ChatOpenAI，用于创建OpenAI兼容的聊天模型
from langchain_core.prompts import ChatPromptTemplate  # 从langchain_core.prompts导入ChatPromptTemplate，用于构建提示模板
import colorlog  # 导入colorlog模块，用于彩色日志输出
import logging  # 导入logging模块，作为colorlog的基础日志系统
from SmartVoyage.config import Config  # 从自定义模块导入Config类，用于加载配置参数如API密钥
from datetime import datetime, timedelta  # 从datetime导入datetime和timedelta，用于日期时间计算
import pytz  # 导入pytz模块，用于时区处理

# 设置彩色日志
handler = colorlog.StreamHandler()  # 创建流处理器，用于将日志输出到标准输出
handler.setFormatter(colorlog.ColoredFormatter(  # 为处理器设置彩色格式化器
    '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',  # 指定日志格式：颜色、时间、级别、消息
    log_colors={'INFO': 'green', 'ERROR': 'red'}  # 定义日志级别的颜色映射：INFO绿色，ERROR红色
))  # 格式化器设置结束
logger = colorlog.getLogger()  # 获取根日志记录器
logger.addHandler(handler)  # 添加处理器到日志记录器
logger.setLevel(colorlog.INFO)  # 设置日志级别为INFO，仅记录INFO及以上级别

def main():  # 定义主函数，包含服务器初始化和运行逻辑
    # 初始化LLM
    conf = Config()  # 实例化Config对象，加载配置
    llm = ChatOpenAI(  # 创建ChatOpenAI模型实例
        model=conf.model_name,  # 使用配置中的模型名称
        api_key=conf.api_key,  # 使用配置中的API密钥
        base_url=conf.api_url,  # 使用配置中的API基础URL
        temperature=0,  # 设置温度为0，确保输出确定性
        streaming=True,  # 启用流式响应
    )  # LLM初始化结束

    # 数据库 schema
    database_schema_string = """  # 定义天气数据表的SQL schema字符串，用于Prompt上下文
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
    """  # schema字符串结束

    # 优化Prompt：基于整个对话历史提取槽位，如果缺少则追问，不默认查询多个城市，不得杜撰
    sql_prompt = ChatPromptTemplate.from_template(  # 从模板创建ChatPromptTemplate，用于SQL生成
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
        """  # Prompt模板字符串结束，包含系统提示、示例和占位符
    )  # sql_prompt创建结束

    # Agent卡片定义
    agent_card = AgentCard(  # 创建AgentCard实例，定义代理元数据
        name="Weather Query Assistant",  # 设置代理名称
        description="基于LangChain提供天气查询服务的助手",  # 设置代理描述
        url="http://localhost:5005",  # 设置代理URL
        version="1.0.0",  # 设置版本号
        capabilities={"streaming": True, "memory": True},  # 设置能力：支持流式和内存
        skills=[  # 定义技能列表
            AgentSkill(  # 创建第一个AgentSkill实例
                name="execute weather query",  # 技能名称
                description="执行天气查询，返回天气数据库结果，支持自然语言输入",  # 技能描述
                examples=["北京 2025-07-30 天气", "上海未来5天", "今天天气如何"]  # 技能示例
            )  # 技能定义结束
        ]  # 技能列表结束
    )  # agent_card创建结束

    # 天气查询服务器类
    class WeatherQueryServer(A2AServer):  # 定义天气查询服务器类，继承自A2AServer
        def __init__(self):  # 初始化方法
            super().__init__(agent_card=agent_card)  # 调用父类初始化，传入代理卡片
            self.llm = llm  # 保存LLM实例
            self.sql_prompt = sql_prompt  # 保存Prompt模板
            self.schema = database_schema_string  # 保存数据库schema

        def generate_sql_query(self, conversation: str) -> dict:  # 定义生成SQL查询方法，输入对话历史，返回字典
            # 生成SQL或追问JSON
            try:  # 开始异常捕获块
                current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')  # 获取当前日期（Asia/Shanghai时区），格式化为字符串
                chain = self.sql_prompt | self.llm  # 创建LangChain链：Prompt + LLM
                output = chain.invoke({"conversation": conversation, "current_date": current_date}).content.strip()  # 调用链生成输出，剥离空白
                if output.startswith('{'):  # 检查输出是否以JSON开头
                    return json.loads(output)  # 解析并返回JSON
                return {"status": "sql", "sql": output}  # 否则视为SQL，返回SQL状态字典
            except Exception as e:  # 捕获异常
                logger.error(f"SQL生成失败: {str(e)}")  # 记录错误日志
                return {"status": "input_required", "message": "查询无效，请提供城市和日期。"}  # 返回追问JSON

        def handle_task(self, task):  # 定义处理任务方法，输入任务对象
            # 处理任务：提取输入，生成SQL，调用MCP，格式化结果
            message_data = task.message or {}  # 获取任务消息，默认空字典
            content = message_data.get("content", {})  # 从消息中获取内容
            # 处理输入conversation就是客户端发起的任务中的query语句
            conversation = content.get("text", "") if isinstance(content, dict) else ""  # 提取文本对话历史
            logger.info(f"对话历史: {conversation}")  # 记录对话历史日志

            try:  # 开始异常捕获块
                #基于对话生成SQL查询
                gen_result = self.generate_sql_query(conversation)  # 生成SQL或追问结果
                if gen_result["status"] == "input_required":  # 检查是否需要追问
                    # 追问逻辑，这里是指在无法正常生成sql时，
                    task.status = TaskStatus(state=TaskState.INPUT_REQUIRED, message={"role": "agent", "content": {"text": gen_result["message"]}})  # 设置任务状态为输入所需，添加追问消息
                    return task  # 返回任务

                sql_query = gen_result["sql"]  # 提取SQL查询
                logger.info(f"生成的SQL查询: {sql_query}")  # 记录生成的SQL日志

                # 调用MCP，线程安全异步执行
                client = MCPClient("http://localhost:6001")  # 创建MCP客户端，连接天气MCP服务器
                #如果线程中已有一个默认事件循环（通过asyncio.get_event_loop()获取），且其他异步操作正在使用它，handle_task中的asyncio.set_event_loop(loop)会替换默认循环。
                loop = asyncio.get_event_loop_policy().new_event_loop()  # 创建新事件循环，确保线程安全
                try:  # 开始循环管理块
                    # 通过创建新循环并调用set_event_loop，确保client.call_tool的异步操作在独立的、线程安全的事件循环中运行，隔离于其他异步操作。
                    asyncio.set_event_loop(loop)  # 设置当前事件循环
                    weather_result = loop.run_until_complete(client.call_tool("query_weather", sql=sql_query))  # 异步调用MCP工具，传入SQL
                finally:  # 确保循环关闭
                    loop.close()  # 关闭事件循环
                response = json.loads(weather_result) if isinstance(weather_result, str) else weather_result  # 解析MCP响应为字典
                if response.get("status") == "no_data":  # 检查响应状态
                    response_text = f"{response['message']} 如果需要其他日期，请补充。"  # 生成无数据提示文本
                else:  # 有数据情况
                    data = response.get("data", [])  # 提取数据列表
                    response_text = "\n".join([f"{d['city']} {d['fx_date']}: {d['text_day']}（夜间 {d['text_night']}），温度 {d['temp_min']}-{d['temp_max']}°C，湿度 {d['humidity']}%，风向 {d['wind_dir_day']}，降水 {d['precip']}mm" for d in data])  # 格式化每个数据项为友好文本，连接成多行

                task.artifacts = [{"parts": [{"type": "text", "text": response_text}]}]  # 设置任务产物为文本部分
                task.status = TaskStatus(state=TaskState.COMPLETED)  # 设置任务状态为完成
            except Exception as e:  # 捕获异常
                logger.error(f"查询失败: {str(e)}")  # 记录错误日志
                task.artifacts = [{"parts": [{"type": "text", "text": f"查询失败: {str(e)} 请重试或提供更多细节。"}]}]  # 设置错误产物文本
                task.status = TaskStatus(state=TaskState.COMPLETED)  # 设置任务状态为完成
            return task  # 返回处理后的任务

    # 创建并运行服务器
    weather_server = WeatherQueryServer()  # 实例化天气查询服务器

    print("\n=== 服务器信息 ===")  # 打印服务器信息分隔线
    print(f"名称: {weather_server.agent_card.name}")  # 打印代理名称
    print(f"描述: {weather_server.agent_card.description}")  # 打印代理描述
    print("\n技能:")  # 打印技能标题
    for skill in weather_server.agent_card.skills:  # 遍历技能列表
        print(f"- {skill.name}: {skill.description}")  # 打印每个技能的名称和描述

    run_server(weather_server, host="0.0.0.0", port=5005)  # 运行A2A服务器，绑定所有IP，端口5005

if __name__ == "__main__":  # 检查是否为直接运行模块
    import sys  # 导入sys模块，用于系统退出
    try:  # 开始异常捕获块
        main()  # 调用主函数
        sys.exit(0)  # 正常退出
    except KeyboardInterrupt:  # 捕获键盘中断
        print("\n✅ 程序被用户中断")  # 打印中断消息
        sys.exit(0)  # 正常退出
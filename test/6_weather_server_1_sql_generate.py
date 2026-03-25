import sys
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


def generate_sql_query(conversation: str) -> dict:  # 定义生成SQL查询方法，输入对话历史，返回字典
    # 生成SQL或追问JSON
    try:  # 开始异常捕获块
        current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime(
            '%Y-%m-%d')  # 获取当前日期（Asia/Shanghai时区），格式化为字符串
        chain = sql_prompt | llm  # 创建LangChain链：Prompt + LLM
        output = chain.invoke(
            {"conversation": conversation, "current_date": current_date}).content.strip()  # 调用链生成输出，剥离空白
        if output.startswith('{'):  # 检查输出是否以JSON开头
            return json.loads(output)  # 解析并返回JSON
        return {"status": "sql", "sql": output}  # 否则视为SQL，返回SQL状态字典
    except Exception as e:  # 捕获异常
        logger.error(f"SQL生成失败: {str(e)}")  # 记录错误日志
        return {"status": "input_required", "message": "查询无效，请提供城市和日期。"}  # 返回追问JSON



#sql生成
# 验证逻辑
def validate_sql_generation():
    print("=== 验证SQL生成逻辑 ===")
    # 测试场景1：有效对话（北京 明天）
    conversation1 = "user: 北京 明天"
    result1 = generate_sql_query(conversation1)
    print(f"场景1（有效对话）结果: {result1}")
    assert result1["status"] == "sql", "状态应为sql"
    assert "city, fx_date, temp_max, temp_min" in result1["sql"], "SQL未包含预期字段"
    assert "北京" in result1["sql"], "SQL未包含城市"
    assert "2025-09-16" in result1["sql"], "SQL未包含正确日期"

    # 测试场景2：无效对话（你好）
    conversation2 = "user: 你好"
    result2 = generate_sql_query(conversation2)
    print(f"场景2（无效对话）结果: {result2}")
    assert result2["status"] == "input_required", "状态应为input_required"
    assert "请提供城市和日期" in result2["message"], "追问消息错误"

    print("SQL生成验证通过！")

if __name__ == '__main__':
    validate_sql_generation()

    """
    sql字段是LLM（如DeepSeek）通过Prompt中的示例学习到，并
    没有在prompt中设置
    """
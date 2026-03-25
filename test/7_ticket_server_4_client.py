#!/usr/bin/env_log.log python
"""
票务查询客户端测试脚本
参考 douban_A2Aagent_client_noStreaming.py 的实现思路：
- 使用彩色日志记录过程
- 获取助手信息
- 支持交互查询，并使用 LLM 生成总结（参考豆瓣解说员风格）
- 处理正常查询、模糊查询和异常情况
- 专注于票务服务器
"""

import colorlog
import logging
import json
from python_a2a import A2AClient
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# 设置彩色日志
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
    log_colors={'INFO': 'green', 'ERROR': 'red'}
))
logger = colorlog.getLogger()
logger.addHandler(handler)
logger.setLevel(colorlog.INFO)

# 配置类（替换为你的实际配置）
from config import Config

conf = Config()

llm = ChatOpenAI(
    model=conf.model_name,
    api_key=conf.api_key,
    base_url=conf.api_url,
    temperature=0.7)

# 票务总结提示模板（参考豆瓣风格）
ticket_prompt = ChatPromptTemplate.from_template(
    """
    您是一位票务解说员，以生动、引人入胜的风格为用户介绍票务查询结果。基于以下查询结果，生成一段总结：
    - 突出出发/到达城市、时间、类型、价格和剩余票数，提及关键亮点。
    - 使用解说员的语气，例如“欢迎来到票务宝库！今天我们为您精选了...”。
    - 如果结果为空，建议用户尝试其他查询条件。
    - 保持中文叙述，字数控制在 100-150 字。

    查询结果：
    {tickets}

    总结：
    """
)


def main():
    # 初始化票务客户端
    ticket_client = A2AClient("http://localhost:5006")

    # 获取票务代理信息
    try:
        logger.info("获取票务助手信息")
        logger.info(f"名称: {ticket_client.agent_card.name}")
        logger.info(f"描述: {ticket_client.agent_card.description}")
        logger.info(f"版本: {ticket_client.agent_card.version}")
        if ticket_client.agent_card.skills:
            logger.info("支持技能:")
            for skill in ticket_client.agent_card.skills:
                logger.info(f"- {skill.name}: {skill.description}")
                if skill.examples:
                    logger.info(f"  示例: {', '.join(skill.examples)}")
    except Exception as e:
        logger.error(f"无法获取票务助手信息: {str(e)}")

    # 交互循环
    while True:
        user_input = input("输入您的票务查询（输入 'exit' 退出）：")
        if user_input.lower() == 'exit':
            break

        try:
            query = user_input.strip()
            logger.info(f"用户查询 (票务): {query}")

            # 发送查询
            logger.info("正在查询数据...")
            response = ticket_client.ask(query)
            logger.info(f"原始响应: {response}")

            # 生成 LLM 总结
            try:
                summary_chain = ticket_prompt | llm
                summary = summary_chain.invoke({"tickets": response}).content.strip()
                logger.info(f"**票务解说员总结**:\n{summary}")
            except Exception as e:
                error_message = f"生成总结失败: {str(e)}"
                logger.error(error_message)

        except Exception as e:
            error_message = f"查询失败: {str(e)}"
            logger.error(error_message)


if __name__ == "__main__":
    main()

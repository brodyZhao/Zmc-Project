import sys
# router_A2Aagent_Server.py
# 功能：路由Agent服务器，使用LLM进行意图识别和路由决策，支持工作流。

import logging

sys.path.append('c:\\Users\\86150\\Desktop\\NPU\\agent')
from python_a2a import run_server, Message, MessageRole, TextContent, AgentCard
import asyncio
from langchain_openai import ChatOpenAI
from python_a2a import A2AClient, to_a2a_server
from SmartVoyage.config import Config

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 配置
conf = Config()


async def main():
    # 创建LangChain LLM
    llm = ChatOpenAI(
        model=conf.model_name,
        api_key=conf.api_key,
        base_url=conf.api_url,
        temperature=0,
        streaming=True
    )

    # 转换为A2A服务器
    llm_server = to_a2a_server(llm)

    # 设置自定义AgentCard
    llm_server.agent_card = AgentCard(
        name="SmartVoyageRouter",
        description="路由Agent，用于意图识别和任务分发，支持天气、火车、飞机、演唱会查询",
        version="1.0.0",
        url="http://localhost:6666",
    )

    print(f"AgentCard: {llm_server.agent_card.__dict__}")

    # 启动服务器
    run_server(llm_server, port=6666)


if __name__ == '__main__':
    asyncio.run(main())
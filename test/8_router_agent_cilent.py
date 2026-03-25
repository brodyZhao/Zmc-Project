# test_a2a_client.py
# 功能：A2A客户端，连接到router_A2Aagent_Server.py，获取并验证AgentCard信息

import asyncio
import json
import logging
from python_a2a import A2AClient, Message, TextContent, MessageRole, Task

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_agent_card():
    print("=== 同步ask ===")

    # 初始化A2A客户端
    client = A2AClient("http://localhost:6666")
    response=client.ask("你好")
    print( response)



    print("=== 异步task ===")
 # 创建消息
    query="你可以做什么？"
    message = Message(
        content=TextContent(text=query),
        role=MessageRole.USER
    )

    # 创建任务
    task = Task(
        id="task-123",
        message=message.to_dict()
    )

    # 使用 send_task 获取完整 Task 响应
    ticket_result = await client.send_task_async(task)
    print("收到完整结果：")
    print(json.dumps(ticket_result.to_dict(), indent=4, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(test_agent_card())
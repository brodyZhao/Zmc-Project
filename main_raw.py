# 导入必要的模块
# 注意：本文件原本基于Streamlit构建，现在去除Streamlit部分，转换为一个可独立运行的Python脚本
# 用于验证核心逻辑：意图识别、代理路由、响应生成等
# 运行时需确保相关依赖服务（如代理服务器）已启动
# 核心逻辑保持不变，仅将UI交互替换为命令行输入输出
import json  # 用于JSON解析和序列化
from datetime import datetime  # 用于获取当前日期和时间
import pytz  # 用于处理时区信息
import re  # 用于清理和处理响应字符串
import logging  # 用于记录日志信息，便于调试

# 导入自定义模块（假设这些模块已存在于环境中）
from python_a2a import AgentNetwork, A2AClient, AIAgentRouter  # A2A代理网络、客户端和路由器
from langchain_openai import ChatOpenAI  # LangChain的OpenAI聊天模型
from langchain_core.prompts import ChatPromptTemplate  # LangChain的聊天提示模板
from config import Config  # 配置文件类，用于加载API配置

# 设置日志模块
# 日志用于记录关键步骤，便于问题排查
logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器
logger.setLevel(logging.INFO)  # 设置日志级别为INFO
handler = logging.StreamHandler()  # 创建流处理器，将日志输出到控制台
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))  # 设置日志格式，包括时间、级别和消息
logger.addHandler(handler)  # 将处理器添加到日志记录器

# 初始化全局变量，用于模拟会话状态
# 这些变量替换了Streamlit的session_state
messages = []  # 存储对话历史消息列表，每个元素为字典{"role": "user/assistant", "content": "消息内容"}
agent_network = None  # 代理网络实例
router = None  # AI代理路由器实例
llm = None  # 大语言模型实例
agent_urls = {}  # 存储代理的URL信息字典
conversation_history = ""  # 存储整个对话历史字符串，用于意图识别


# 初始化代理网络和相关组件
# 此部分在脚本启动时执行一次，模拟Streamlit的初始化
def initialize_system():
    """
    初始化系统组件，包括代理网络、路由器、LLM和会话状态
    核心逻辑：构建AgentNetwork，添加代理，创建路由器和LLM
    """
    global agent_network, router, llm, agent_urls, conversation_history
    # 创建代理网络实例
    network = AgentNetwork(name="Travel Assistant Network")  # 初始化名为"Travel Assistant Network"的代理网络
    # 添加天气查询代理
    network.add("Weather Query Assistant", "http://localhost:5005")  # 添加天气代理及其URL
    # 添加票务查询代理
    network.add("Ticket Query Assistant", "http://localhost:5006")  # 添加票务代理及其URL
    agent_network = network  # 将网络赋值给全局变量

    # 创建AI代理路由器
    router = AIAgentRouter(
        llm_client=A2AClient("http://localhost:6666"),  # 使用A2A客户端连接路由器LLM服务器
        agent_network=network  # 将代理网络传入路由器
    )

    # 加载配置并创建LLM
    conf = Config()  # 实例化配置类

    llm = ChatOpenAI(
        model=conf.model_name,  # 使用配置中的模型名称
        api_key=conf.api_key,  # 使用配置中的API密钥
        base_url=conf.api_url,  # 使用配置中的API基础URL
        temperature=0  # 设置温度为0，确保输出确定性
    )

    # 存储代理URL信息
    agent_urls = {
        "Weather Query Assistant": "http://localhost:5005",  # 天气代理URL
        "Ticket Query Assistant": "http://localhost:5006"  # 票务代理URL
    }

    # 初始化对话历史为空字符串
    conversation_history = ""


# 定义意图识别提示模板
# 此Prompt用于LLM识别用户意图和提取槽位信息
intent_prompt = ChatPromptTemplate.from_template(
    """
系统提示：您是一个专业的旅行意图识别专家，基于用户查询和对话历史，识别意图并提取槽位。严格遵守规则：
- 支持意图：['weather' (天气查询), 'flight' (机票查询), 'train' (高铁/火车票查询), 'concert' (演唱会票查询), 'attraction' (景点推荐)] 或其组合（如 ['weather', 'flight']）。
- 如果意图超出范围，返回意图 'out_of_scope'。
- 提取槽位：
  - weather: city (城市，多个用逗号分隔), date (日期，支持'今天'/'明天'/'后天'/'未来X天'，转换为YYYY-MM-DD或范围)。
  - flight/train: departure_city (出发城市), arrival_city (到达城市), date (日期), seat_type (座位类型，如'经济舱'/'硬卧')。
  - concert: city (城市), artist (艺人), date (日期), ticket_type (票务类型，如'看台、VIP')。
  - attraction: city (城市), preferences (偏好，如'历史'/'自然')。
- 如果意图为组合，只提取公共槽位，并在后续处理中分别填充。
- 如果槽位缺失，返回 'missing_slots' 列表和追问消息,不得回复空信息。
- 对于weather：如果无city，默认['北京','上海','广州','深圳']；无date，默认今天。
- 输出严格为JSON：{{"intents": ["intent1", "intent2"], "slots": {{"intent1": {{"slot1": "value1"}}, "intent2": {{"slot2": "value2"}}}}, "missing_slots": {{"intent1": ["slot1"]}}, "follow_up_message": "追问消息"}}。不要添加额外文本！
- 当前日期：{current_date} (Asia/Shanghai)。
- 基于整个对话历史填充槽位，优先最新查询。

对话历史：{conversation_history}
用户查询：{query}
    """
)

# 定义天气结果总结提示模板
# 此Prompt用于LLM总结天气查询的原始响应
summarize_weather_prompt = ChatPromptTemplate.from_template(
    """
系统提示：您是一位专业的天气预报员，以生动、准确的风格总结天气信息。基于查询和结果：
- 核心：城市、日期、温度范围、天气描述、湿度、风向、降水。
- 如果结果为空，提示“未找到数据，请确认城市/日期，不得编造。”
- 语气：专业预报，如“根据最新数据，北京2025-07-31的天气预报为...”。
- 保持中文，100-150字。
- 如果查询无关，返回“请提供天气相关查询。”

查询：{query}
结果：{raw_response}
    """
)

# 定义票务结果总结提示模板
# 此Prompt用于LLM总结票务查询的原始响应
summarize_ticket_prompt = ChatPromptTemplate.from_template(
    """
系统提示：您是一位专业的旅行顾问，以热情、精确的风格总结票务信息。基于查询和结果：
- 核心：出发/到达、时间、类型、价格、剩余座位。
- 如果结果为空，提示“未找到数据，请确认条件，不得编造。”
- 语气：顾问式，如“为您推荐北京到上海的机票选项...”。
- 保持中文，100-150字。
- 如果查询无关，返回“请提供票务相关查询。”


查询：{query}
结果：{raw_response}

    """
)

# 定义景点推荐提示模板
# 此Prompt用于LLM直接生成景点推荐内容
attraction_prompt = ChatPromptTemplate.from_template(
    """
系统提示：您是一位旅行专家，基于用户查询生成景点推荐。规则：
- 推荐3-5个景点，包含描述、理由、注意事项。
- 基于槽位：城市、偏好。
- 语气：热情推荐，如“推荐您在北京探索故宫...”。
- 备注：内容生成，仅供参考。
- 保持中文，150-250字。

查询：{query}
槽位：{slots}
    """
)


# 处理用户输入的核心函数
# 此函数模拟Streamlit的输入处理逻辑，包括意图识别、路由和响应生成
def process_user_input(prompt):
    """
    处理用户输入：识别意图、调用代理、生成响应
    核心逻辑：使用LLM进行意图识别，根据意图路由到相应代理或直接生成内容
    """
    global messages, conversation_history, llm
    # 添加用户消息到历史
    messages.append({"role": "user", "content": prompt})  # 将用户输入添加到消息列表
    # logger.info(f"messages: {messages}")
    conversation_history += f"\nUser: {prompt}"  # 更新对话历史
    logger.info(f"conversation_history: {conversation_history}")

    # 获取当前日期（Asia/Shanghai时区）
    current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')  # 格式化为YYYY-MM-DD

    # 意图识别过程
    print("正在分析您的意图...")  # 模拟加载提示
    try:
        # 创建意图识别链：提示模板 + LLM
        chain = intent_prompt | llm  # LangChain链组合
        # 调用LLM进行意图识别
        intent_response = chain.invoke({"conversation_history": conversation_history, "query": prompt,
                                        "current_date": current_date}).content.strip()
        # 记录原始响应日志
        logger.info(f"意图识别原始响应: {intent_response}")
        # 清理响应：移除可能的Markdown代码块标记
        intent_response = re.sub(r'^```json\s*|\s*```$', '', intent_response).strip()
        # 记录清理后响应日志
        logger.info(f"清理后响应: {intent_response}")
        # 解析JSON响应
        intent_output = json.loads(intent_response)
        # logger.info(f"意图输出: {intent_output}")

        # 提取意图、槽位、缺失槽位和追问消息
        intents = intent_output.get("intents", [])
        slots = intent_output.get("slots", {})
        missing_slots = intent_output.get("missing_slots", {})
        follow_up_message = intent_output.get("follow_up_message", "")
        # 记录解析输出日志
        logger.info(f"解析意图输出: {intent_output}")

        # 根据意图输出生成响应
        if "out_of_scope" in intents:
            # 如果意图超出范围，返回通用旅行助手介绍
            response = "您好!我是AI旅行助手SmartVoyage，专注于旅行相关的信息和服务，比如火车票、高铁票、演唱会门票、天气查询、景点推荐等。如果您有任何旅行方面的需求，请随时告诉我，我会尽力为您提供帮助!"
            logger.info(f"通用响应: {response}")
        elif missing_slots:
            # 如果有缺失槽位，使用追问消息
            response = follow_up_message
            logger.info(f"追问消息: {response}")
            conversation_history += f"\nAssistant: {response}"  # 更新历史
            logger.info(f"conversation_history: {conversation_history}")
        else:
            # 处理有效意图
            responses = []  # 存储每个意图的响应列表
            routed_agents = []  # 记录路由到的代理列表
            for intent in intents:
                # 根据意图确定代理名称
                agent_name = "Weather Query Assistant" if intent == "weather" else "Ticket Query Assistant" if intent in [
                    "flight", "train", "concert"] else None
                if intent == "attraction":
                    # 对于景点推荐，直接使用LLM生成
                    chain = attraction_prompt | llm  # 创建生成链
                    rec_response = chain.invoke({"query": prompt, "slots": json.dumps(slots.get(intent, {}),
                                                                                      ensure_ascii=False)}).content.strip()  # 调用LLM生成推荐
                    logger.info(f"景点推荐原始响应: {rec_response}")
                    responses.append(rec_response)  # 添加到响应列表
                elif agent_name:
                    # 对于代理意图，构建查询字符串并调用代理
                    intent_slots = slots.get(intent, {})  # 获取当前意图的槽位
                    logger.info(f"代理名称: {agent_name}")
                    if intent == "weather":
                        # 天气查询：设置默认城市和日期
                        if not intent_slots.get("city"):
                            intent_slots["city"] = "北京,上海,广州,深圳"  # 默认四个城市
                        if not intent_slots.get("date"):
                            intent_slots["date"] = current_date  # 默认今天
                        query_str = f"{intent_slots['city']} {intent_slots['date']}"  # 构建查询字符串
                        logger.info(f"查询字符串: {query_str}")
                    else:
                        # 票务查询：构建通用查询字符串
                        query_str = f"{intent} {intent_slots.get('departure_city', '')} {intent_slots.get('arrival_city', '')} {intent_slots.get('date', current_date)} {intent_slots.get('seat_type', '')}".strip()
                        logger.info(f"查询字符串: {query_str}")
                        if intent == "concert":
                            # 演唱会查询：特殊格式
                            query_str = f"演唱会 {intent_slots.get('city', '')} {intent_slots.get('artist', '')} {intent_slots.get('date', current_date)} {intent_slots.get('ticket_type', '')}".strip()
                            logger.info(f"查询字符串: {query_str}")

                    # 获取代理实例并调用
                    agent = agent_network.get_agent(agent_name)  # 从网络获取代理
                    raw_response = agent.ask(query_str)  # 同步调用代理查询
                    # 记录原始响应日志
                    logger.info(f"{agent_name} 原始响应: {raw_response}")
                    # 根据代理类型总结响应
                    if agent_name == "Weather Query Assistant":
                        chain = summarize_weather_prompt | llm  # 创建天气总结链
                        sum_response = chain.invoke(
                            {"query": query_str, "raw_response": raw_response}).content.strip()  # 生成总结
                        logger.info(f"{agent_name} 总结: {sum_response}")
                    else:
                        chain = summarize_ticket_prompt | llm  # 创建票务总结链
                        sum_response = chain.invoke(
                            {"query": query_str, "raw_response": raw_response}).content.strip()  # 生成总结
                        logger.info(f"{agent_name} 总结: {sum_response}")
                    responses.append(sum_response)  # 添加到响应列表
                    routed_agents.append(agent_name)  # 记录路由代理
                else:
                    # 不支持的意图
                    responses.append("暂不支持此意图。")

            # 组合所有响应
            response = "\n\n".join(responses)  # 用双换行分隔多个响应
            logger.info(f"助手响应: {response}")
            if routed_agents:
                # 如果有路由，添加路由信息
                response = f"**路由至：{', '.join(set(routed_agents))}**\n\n" + response
                logger.info(f"助手路由信息: {response}")
            conversation_history += f"\nAssistant: {response}"  # 更新历史
            # logger.info(f"助手历史: {conversation_history}")

        # 输出助手响应（模拟Streamlit的显示）
        print(f"\n助手回复：\n{response}\n")  # 打印响应
        # 添加到消息历史
        messages.append({"role": "assistant", "content": response})
        # logger.info(f"助手消息历史: {messages}")

    except json.JSONDecodeError as json_err:
        # 处理JSON解析错误
        logger.error(f"意图识别JSON解析失败，响应内容: {intent_response}")
        error_message = f"意图识别JSON解析失败：{str(json_err)}。请重试。"
        print(f"\n助手回复：\n{error_message}\n")  # 打印错误
        messages.append({"role": "assistant", "content": error_message})
    except Exception as e:
        # 处理其他异常
        logger.error(f"处理异常: {str(e)}")
        error_message = f"处理失败：{str(e)}。请重试。"
        print(f"\n助手回复：\n{error_message}\n")  # 打印错误
        messages.append({"role": "assistant", "content": error_message})


# 显示代理卡片信息
# 此函数模拟Streamlit的右侧Agent Card，打印代理详情
def display_agent_cards():
    """
    显示所有代理的卡片信息，包括技能、描述、地址和状态
    核心逻辑：遍历代理网络，获取并打印卡片内容
    """
    print("\n🛠️ Agent Cards:")
    for agent_name in agent_network.agents.keys():
        # 获取代理卡片
        agent_card = agent_network.get_agent_card(agent_name)
        agent_url = agent_urls.get(agent_name, "未知地址")  # 获取URL
        print(f"\n--- Agent: {agent_name} ---")
        print(f"技能: {agent_card.skills}")  # 打印技能
        print(f"描述: {agent_card.description}")  # 打印描述
        print(f"地址: {agent_url}")  # 打印地址
        print(f"状态: 在线")  # 固定状态为在线


# 主函数：脚本入口
# 初始化系统并进入交互循环
if __name__ == "__main__":
    # 初始化系统
    initialize_system()  # 调用初始化函数
    print("🤖 基于A2A的SmartVoyage旅行智能助手")  # 打印标题
    print("欢迎体验智能对话！输入问题，按回车提交；输入'quit'退出；输入'cards'查看代理卡片。")  # 打印说明

    # 显示初始代理卡片
    display_agent_cards()  # 调用显示函数

    # 交互循环：模拟Streamlit的连续输入
    while True:
        # 获取用户输入
        prompt = input("\n请输入您的问题: ").strip()  # 从命令行读取输入
        if prompt.lower() == 'quit':  # 退出条件
            print("感谢使用SmartVoyage！再见！")  # 退出消息
            break
        elif prompt.lower() == 'cards':  # 查看卡片条件
            display_agent_cards()  # 重新显示卡片
            continue
        elif not prompt:  # 空输入跳过
            continue
        else:
            # 处理输入
            process_user_input(prompt)  # 调用核心处理函数

    # 脚本结束时打印页脚信息
    print("\n---")
    print("Powered by 云上营商程序员 | 基于Agent2Agent的旅行助手系统 v2.0")  # 页脚

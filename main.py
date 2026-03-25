import streamlit as st
from python_a2a import AgentNetwork, A2AClient, AIAgentRouter
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from config import Config
import json
from datetime import datetime
import pytz
import re  # 用于清理响应文本
import logging  # 用于日志调试

# 日志设置 用于输出系统关键信息和调试日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# 页面主配置
# page_title: 页面标题
# layout: 页面布局宽度
# page_icon: 显示的 Emoji 图标
st.set_page_config(page_title="基于A2A的SmartVoyage旅行助手系统", layout="wide", page_icon="🤖")

# 高端自定义CSS，主要美化整体页面风格，优化可读性与对比度
st.markdown("""
<style>
body {
    font-family: 'Arial', sans-serif;
}
.stApp {
    background: linear-gradient(135deg, #1e1b4b 0%, #3b3e99 100%);
    color: #f5f5d5;
}
.stTextInput > div > input {
    background-color: #3a4a77;
    color: #f5f5d5;
    border-radius: 12px;
    border: 1px solid #7a8acc;
    padding: 12px;
}
/* 优化返回内容方框背景为浅色，提升可读性 */
.stChatMessage {
    background-color: #f7f7ff;    /* 明亮浅色底 */
    border-radius: 12px;
    padding: 15px;
    margin-bottom: 15px;
    box-shadow: 0 3px 6px rgba(0,0,0,0.14);
    color: #232346;               /* 深色字体 */
    font-size: 1.1em;
    line-height: 1.5;
}
.stChatMessage.user {
    background-color: #34495e;
    color: #ecf0f1;
    font-size: 1.1em;
    line-height: 1.5;
}
.stExpander {
    background-color: #3a4a77;
    border-radius: 12px;
    border: 1px solid #7a8acc;
    transition: all 0.3s ease;
}
.stExpander > summary {
    font-size: 1.3em;
    font-weight: 500;
    color: #d4d9ff;
}
.stExpander:hover {
    border-color: #8a9cff;
    box-shadow: 0 4px 10px rgba(0,0,0,0.25);
}
h1 {
    color: #d4d9ff;
    font-weight: 300;
    font-size: 2.5em;
}
h2, h3 {
    color: #d4d9ff;
    font-weight: 300;
}
.card-title {
    color: #8a9cff;
    font-size: 1.6em;
    margin-bottom: 10px;
}
.card-content {
    color: #f5f5d5;
    font-size: 0.95em;
}
.footer {
    text-align: center;
    color: #d4d9ff;
    padding: 20px;
    font-size: 1.2em;
}
</style>
""", unsafe_allow_html=True)

# -------------------- 会话状态、网络初始化 --------------------

if "messages" not in st.session_state:
    # 会话消息列表(用于保存往来消息)
    st.session_state.messages = []
if "agent_network" not in st.session_state:
    # 代理网络初始化
    network = AgentNetwork(name="Travel Assistant Network")
    network.add("Weather Query Assistant", "http://localhost:5005")  # 天气查询代理
    network.add("Ticket Query Assistant", "http://localhost:5006")    # 票务查询代理
    st.session_state.agent_network = network

    # LLM路由服务初始化
    st.session_state.router = AIAgentRouter(
        llm_client=A2AClient("http://localhost:6666"),  # LLM 路由服务器地址
        agent_network=network
    )

    # LLM模型（OpenAI or compatible）配置
    conf = Config()
    st.session_state.llm = ChatOpenAI(
        model=conf.model_name,        # 配置项模型名称
        api_key=conf.api_key,         # API Key
        base_url=conf.api_url,        # API地址
        temperature=0.8                 # 采样温度，0为确定性输出
    )
    # 代理服务URL映射
    st.session_state.agent_urls = {
        "Weather Query Assistant": "http://localhost:5005",
        "Ticket Query Assistant": "http://localhost:5006"
    }
    # 对话历史(用于辅助上下文意图识别)
    st.session_state.conversation_history = ""

# -------------------- PROMPT 模板参数与注释 --------------------

# 意图识别与槽位抽取 prompt
# 参数:
#   conversation_history: 当前对话历史文本
#   query: 用户最新问题
#   current_date: 当前日期字符串(Asia/Shanghai)
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

# 天气总结 prompt
# 参数:
#   query: 原始查询
#   raw_response: 天气API/Agent返回的原始结果文本
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

# 票务总结 prompt
# 参数:
#   query: 原始查询
#   raw_response: 票务API/Agent返回的原始结果文本
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

# 景点推荐 prompt
# 参数:
#   query: 原始用户查询
#   slots: 已提取的意图槽位(json格式)
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

# -------------------- 页面布局与主逻辑 --------------------

st.title("🤖 基于A2A的SmartVoyage旅行智能助手")
st.markdown("欢迎体验智能对话！输入问题，系统将精准识别意图并提供服务。")

# Streamlit 分栏，两栏布局
# col1: 主对话界面; col2: Agent卡片展示
col1, col2 = st.columns([2, 1])

# -------------------- 左侧：对话窗口 --------------------
with col1:
    st.subheader("💬 对话")
    # 展示历史对话消息（区分角色user/assistant）；st.session_state.messages结构: [{"role": ..., "content": ...}]
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):  # Streamlit chat消息块
            st.markdown(message["content"])

    # 聊天输入框，等待用户输入问题（prompt为输入内容）
    if prompt := st.chat_input("请输入您的问题..."):
        # -------- Step1: 记录和展示用户消息 --------
        with st.chat_message("user"):
            st.markdown(prompt)  # 在界面输出用户输入
        # 保存用户输入到对话历史和Session状态
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.conversation_history += f"\nUser: {prompt}"

        # -------- Step2: 获取LLM对象与当前日期 --------
        llm = st.session_state.llm  # 从st.session_state获得LLM实例
        # 上海时区当前日期字符串，用于prompt上下文
        current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')

        # -------- Step3: 意图识别与槽位抽取 --------
        with st.spinner("正在分析您的意图..."):
            try:
                # 构造意图识别chain（prompt+llm）,并推理获取LLM响应
                chain = intent_prompt | llm
                # 调用chain，传入：当前对话历史、当前用户输入、当前日期
                intent_response = chain.invoke(
                    {
                        "conversation_history": st.session_state.conversation_history,  # 对话上下文
                        "query": prompt,                                              # 用户本轮输入
                        "current_date": current_date                                  # 系统当前日期
                    }
                ).content.strip()
                # 日志记录LLM原始输出格式（通常应JSON）
                logger.info(f"意图识别原始响应: {intent_response}")

                # 清理LLM响应可能存在的markdown三引号代码块包裹，例如```json ... ```
                intent_response = re.sub(r'^```json\s*|\s*```$', '', intent_response).strip()
                logger.info(f"清理后响应: {intent_response}")

                # 反序列化解析为JSON字典，提取意图、槽位等信息
                intent_output = json.loads(intent_response)
                # 多意图结果，列表形式，如["flight", "weather"]
                intents = intent_output.get("intents", [])
                # 对应意图的槽位信息，dict结构
                slots = intent_output.get("slots", {})
                # 尚未补齐的槽位（如缺少起点/终点等），dict
                missing_slots = intent_output.get("missing_slots", {})
                # 用于追问用户的消息（如需补充信息时）
                follow_up_message = intent_output.get("follow_up_message", "")
                logger.info(f"解析意图输出: {intent_output}")

                # -------- Step4: 判定意图类型并给出响应 --------
                if "out_of_scope" in intents:
                    # 用户问题超出能力范围，通用拒答+温馨引导
                    response = (
                        "您好!我是AI旅行助手SmartVoyage，专注于旅行相关的信息和服务，"
                        "比如火车票、高铁票、演唱会门票、天气查询、景点推荐等。"
                        "如果您有任何旅行方面的需求，请随时告诉我，我会尽力为您提供帮助!"
                    )
                elif missing_slots:
                    # 部分槽位缺失，继续追问用户补充必要信息
                    response = follow_up_message
                    # 更新对话历史（便于后续上下文继续理解）
                    st.session_state.conversation_history += f"\nAssistant: {response}"
                else:
                    # 多意图综合处理，每个意图路由至对应Agent
                    responses = []      # 存储每个意图的最终回复
                    routed_agents = []  # 跟踪本轮涉及的Agent（用于界面展示路由关系）
                    for intent in intents:
                        # ---------- 1. 确定目标Agent ----------
                        if intent == "weather":
                            agent_name = "Weather Query Assistant"
                        elif intent in ["flight", "train", "concert"]:
                            agent_name = "Ticket Query Assistant"
                        else:
                            agent_name = None

                        # ---------- 2. 景点推荐意图（内容生成） ----------
                        if intent == "attraction":
                            # 直接由LLM根据槽位推荐景点，无Agent路由
                            chain = attraction_prompt | llm
                            rec_response = chain.invoke({
                                "query": prompt,
                                "slots": json.dumps(slots.get(intent, {}), ensure_ascii=False)
                            }).content.strip()
                            responses.append(rec_response)
                        # ---------- 3. 票务、天气等具体服务Agent路由 ----------
                        elif agent_name:
                            # 获取某一意图对应的槽位信息
                            intent_slots = slots.get(intent, {})

                            # ------- 查询参数适配与自动默认填充 -------
                            if intent == "weather":
                                # 天气查询补默认城市与日期
                                if not intent_slots.get("city"):
                                    intent_slots["city"] = "北京,上海,广州,深圳"
                                if not intent_slots.get("date"):
                                    intent_slots["date"] = current_date
                                # 构造查询字符串交给Agent
                                query_str = f"{intent_slots['city']} {intent_slots['date']}"
                            else:
                                # 票务相关意图
                                query_str = (
                                    f"{intent} "
                                    f"{intent_slots.get('departure_city', '')} "
                                    f"{intent_slots.get('arrival_city', '')} "
                                    f"{intent_slots.get('date', current_date)} "
                                    f"{intent_slots.get('seat_type', '')}"
                                ).strip()
                                # "concert"意图需特殊拼接（城市/艺人/类型）
                                if intent == "concert":
                                    query_str = (
                                        f"演唱会 "
                                        f"{intent_slots.get('city', '')} "
                                        f"{intent_slots.get('artist', '')} "
                                        f"{intent_slots.get('date', current_date)} "
                                        f"{intent_slots.get('ticket_type', '')}"
                                    ).strip()
                            # ------- Agent调用与结果处理 -------
                            # 获取目标Agent实例（基于路由判定的agent_name）
                            agent = st.session_state.agent_network.get_agent(agent_name)
                            # 发送查询字符串，获取Agent原始响应文本（如天气数据、车票/航班/演唱会信息等）
                            raw_response = agent.ask(query_str)  # Agent返回原始文本
                            logger.info(f"{agent_name} 原始响应: {raw_response}")

                            # ------- LLM总结/格式化Agent返回 -------
                            # 根据不同服务类型，选用不同的LLM总结/格式化链路
                            if agent_name == "Weather Query Assistant":
                                # 天气类服务用summarize_weather_prompt + LLM总结用户可读答案
                                chain = summarize_weather_prompt | llm
                                sum_response = chain.invoke(
                                    {"query": query_str, "raw_response": raw_response}
                                ).content.strip()
                            else:
                                # 票务/演唱会类服务用summarize_ticket_prompt + LLM做最终答案整理
                                chain = summarize_ticket_prompt | llm
                                sum_response = chain.invoke(
                                    {"query": query_str, "raw_response": raw_response}
                                ).content.strip()
                            # 收集本意图的总结结果，并标记已路由的Agent
                            responses.append(sum_response)
                            routed_agents.append(agent_name)
                        # ---------- 4. 其它暂不支持意图类型 ----------
                        else:
                            # 不支持的意图类型友好提示
                            responses.append("暂不支持此意图。")
                    # 汇总多意图响应文本（以换行分隔）
                    response = "\n\n".join(responses)
                    if routed_agents:
                        # 主动声明此次路由涉及的Agent，便于界面理解Agent协作全链路
                        response = f"**路由至：{', '.join(set(routed_agents))}**\n\n" + response
                    # 对话历史追加本轮AI助手回复
                    st.session_state.conversation_history += f"\nAssistant: {response}"

                # -------- Step5: 展示助手回复，保存状态 --------
                with st.chat_message("assistant"):
                    st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except json.JSONDecodeError as json_err:
                # LLM响应不是有效JSON结构，报错并反馈给用户
                logger.error(f"意图识别JSON解析失败，响应内容: {intent_response}")
                error_message = f"意图识别JSON解析失败：{str(json_err)}。请重试。"
                with st.chat_message("assistant"):
                    st.markdown(error_message)
                st.session_state.messages.append({"role": "assistant", "content": error_message})
            except Exception as e:
                # 全流程异常兜底容错处理，保障不崩
                logger.error(f"处理异常: {str(e)}")
                error_message = f"处理失败：{str(e)}。请重试。"
                with st.chat_message("assistant"):
                    st.markdown(error_message)
                st.session_state.messages.append({"role": "assistant", "content": error_message})

# -------------------- 右侧：Agent卡片信息展示 --------------------
with col2:
    # 右侧区域：展示每个Agent的卡片信息
    st.subheader("🛠️ AgentCard")  # 分区标题
    # 遍历已注册的所有Agent名称
    for agent_name in st.session_state.agent_network.agents.keys():
        # 获取当前Agent的Card信息（包含技能、描述等）
        agent_card = st.session_state.agent_network.get_agent_card(agent_name)
        # 获取当前Agent对应的服务地址（如果没有则显示“未知地址”）
        agent_url = st.session_state.agent_urls.get(agent_name, "未知地址")
        # 使用Expander折叠面板对每个Agent信息分组
        with st.expander(f"Agent: {agent_name}", expanded=False):
            # 显示Agent技能列表
            st.markdown(f"<div class='card-title'>技能</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='card-content'>{agent_card.skills}</div>", unsafe_allow_html=True)
            # 显示Agent描述
            st.markdown(f"<div class='card-title'>描述</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='card-content'>{agent_card.description}</div>", unsafe_allow_html=True)
            # 显示Agent服务地址
            st.markdown(f"<div class='card-title'>地址</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='card-content'>{agent_url}</div>", unsafe_allow_html=True)
            # 显示Agent在线状态（此处默认全部为“在线”，未做实时检测）
            st.markdown(f"<div class='card-title'>状态</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='card-content'>在线</div>", unsafe_allow_html=True)

# 页脚(产品说明)
st.markdown("---")
st.markdown('<div class="footer">Powered by 云上营商程序员 | 基于Agent2Agent的旅行助手系统 v2.0</div>', unsafe_allow_html=True)
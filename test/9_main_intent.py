import json
import logging
from datetime import datetime
import pytz
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from config import Config
conf=Config()
# 设置日志
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

llm = ChatOpenAI(
    model=conf.model_name,
    api_key=conf.api_key,
    base_url=conf.api_url,
    temperature=0
)

# 意图识别提示模板（复制脚本中的intent_prompt）
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

# 模拟意图识别函数（复制脚本中的逻辑）
def recognize_intent(conversation_history, query, current_date):
    """
    模拟脚本中的意图识别逻辑，返回JSON输出。
    """
    chain = intent_prompt | llm  # 创建链：Prompt + LLM
    intent_response = chain.invoke({
        "conversation_history": conversation_history,
        "query": query,
        "current_date": current_date
    }).content.strip()  # 调用LLM生成响应
    try:
        return json.loads(intent_response)  # 解析JSON
    except json.JSONDecodeError as e:
        # logger.error(f"JSON解析失败: {e}")
        return {"error": "JSON解析失败"}


if __name__ == '__main__':
    print("=== 验证意图识别和槽位填充 ===")
    current_date = "2025-09-14"  # 固定当前日期
    conversation_history = ""  # 初始对话历史为空

    # 测试场景1：weather意图（完整输入）
    query1 = "北京明天天气"
    print("场景1（weather完整输入）：", query1)
    result1 = recognize_intent(conversation_history, query1, current_date)
    print("场景1 意图与槽位填充情况：")
    print(result1)
    assert "weather" in result1["intents"], "未识别weather意图"
    assert result1["slots"]["weather"]["city"] == "北京", "city槽位不匹配"
    assert result1["slots"]["weather"]["date"] == "2025-09-15", "date槽位不匹配（明天应为2025-09-15）"
    assert not result1.get("missing_slots"), "不应有缺失槽位"
    print("\n")

    # 测试场景2：weather意图（缺失city，默认填充）
    query2 = "明天天气"
    print("场景2（weather缺失槽位，默认填充）：", query2)
    result2 = recognize_intent(conversation_history, query2, current_date)
    print("场景 2意图与槽位填充情况：：")
    print(result2)
    assert "weather" in result2["intents"], "未识别weather意图"
    assert result2["slots"]["weather"]["city"] == "北京,上海,广州,深圳", "city未默认填充"
    assert result2["slots"]["weather"]["date"] == "2025-09-15", "date槽位不匹配"
    print("\n")

    # 测试场景3：weather意图（缺失槽位，触发追问）
    query3 = "天气"
    print("场景3（weather缺失槽位，默认填充）：", query3)
    result3 = recognize_intent(conversation_history, query3, current_date)
    print("场景3 意图与槽位填充情况：")
    print(result3)
    assert "weather" in result3["intents"], "未识别weather意图"
    assert "missing_slots" in result3, "未返回missing_slots"
    assert "follow_up_message" in result3, "未返回追问消息"
    print("\n")

    # 测试场景4：flight意图（完整输入）
    query4 = "北京到上海的机票 2025-09-15 经济舱"
    print("场景4（flight完整输入）：", query4)
    result4 = recognize_intent(conversation_history, query4, current_date)
    print("场景4 意图与槽位填充情况：：")
    print(result4)
    assert "flight" in result4["intents"], "未识别flight意图"
    assert result4["slots"]["flight"]["departure_city"] == "北京", "departure_city槽位不匹配"
    assert result4["slots"]["flight"]["arrival_city"] == "上海", "arrival_city槽位不匹配"
    assert result4["slots"]["flight"]["date"] == "2025-09-15", "date槽位不匹配"
    assert result4["slots"]["flight"]["seat_type"] == "经济舱", "seat_type槽位不匹配"
    assert not result4.get("missing_slots"), "不应有缺失槽位"
    print("\n")

    # 测试场景6：flight意图（缺失槽位，触发追问）
    query6 = "机票"
    print("场景6（flight缺失槽位，触发追问）：", query6)
    result6 = recognize_intent(conversation_history, query6, current_date)
    print("场景6 意图与槽位填充情况：")
    print(result6)
    assert "flight" in result6["intents"], "未识别flight意图"
    assert "missing_slots" in result6, "未返回missing_slots"
    assert "departure_city" in result6["missing_slots"]["flight"], "未识别缺失departure_city"
    assert "arrival_city" in result6["missing_slots"]["flight"], "未识别缺失arrival_city"
    assert "date" in result6["missing_slots"]["flight"], "未识别缺失date"
    assert "follow_up_message" in result6, "未返回追问消息"
    print("\n")

    # 测试场景7：train意图（完整输入）
    query7 = "北京到上海的高铁 2025-09-15 二等座"
    print("场景7（train完整输入）：", query7)
    result7 = recognize_intent(conversation_history, query7, current_date)
    print("场景7 意图与槽位填充情况：")
    print(result7)
    assert "train" in result7["intents"], "未识别train意图"
    assert result7["slots"]["train"]["departure_city"] == "北京", "departure_city槽位不匹配"
    assert result7["slots"]["train"]["arrival_city"] == "上海", "arrival_city槽位不匹配"
    assert result7["slots"]["train"]["date"] == "2025-09-15", "date槽位不匹配"
    assert result7["slots"]["train"]["seat_type"] == "二等座", "seat_type槽位不匹配"
    assert not result7.get("missing_slots"), "不应有缺失槽位"
    print("\n")

    # 测试场景8：train意图（缺失槽位，触发追问）
    query8 = "高铁票"
    print("场景8（train缺失槽位，触发追问）：", query8)
    result8 = recognize_intent(conversation_history, query8, current_date)
    print("场景8 意图与槽位填充情况：")
    print(result8)
    assert "train" in result8["intents"], "未识别train意图"
    assert "missing_slots" in result8, "未返回missing_slots"
    assert "departure_city" in result8["missing_slots"]["train"], "未识别缺失departure_city"
    assert "arrival_city" in result8["missing_slots"]["train"], "未识别缺失arrival_city"
    assert "date" in result8["missing_slots"]["train"], "未识别缺失date"
    assert "follow_up_message" in result8, "未返回追问消息"
    print("\n")

    # 测试场景9：concert意图（完整输入）
    query9 = "北京周杰伦演唱会 2025-09-15 VIP"
    print("场景9（concert完整输入）：", query9)
    result9 = recognize_intent(conversation_history, query9, current_date)
    print("场景9 意图与槽位填充情况：")
    print(result9)
    assert "concert" in result9["intents"], "未识别concert意图"
    assert result9["slots"]["concert"]["city"] == "北京", "city槽位不匹配"
    assert result9["slots"]["concert"]["artist"] == "周杰伦", "artist槽位不匹配"
    assert result9["slots"]["concert"]["date"] == "2025-09-15", "date槽位不匹配"
    assert result9["slots"]["concert"]["ticket_type"] == "VIP", "ticket_type槽位不匹配"
    assert not result9.get("missing_slots"), "不应有缺失槽位"
    print("\n")

    # 测试场景10：concert意图（缺失槽位，触发追问）
    query10 = "演唱会票"
    print("场景10（concert缺失槽位，触发追问）：", query10)
    result10 = recognize_intent(conversation_history, query10, current_date)
    print("场景10 意图与槽位填充情况：")
    print(result10)
    assert "concert" in result10["intents"], "未识别concert意图"
    assert "missing_slots" in result10, "未返回missing_slots"
    assert "city" in result10["missing_slots"]["concert"], "未识别缺失city"
    assert "artist" in result10["missing_slots"]["concert"], "未识别缺失artist"
    assert "date" in result10["missing_slots"]["concert"], "未识别缺失date"
    assert "follow_up_message" in result10, "未返回追问消息"
    print("\n")

    # 测试场景11：组合意图（weather + flight，完整输入）
    query11 = "北京明天天气和北京到上海的机票 2025-09-15"
    print("场景11（组合意图weather + flight，完整输入）：", query11)
    result11 = recognize_intent(conversation_history, query11, current_date)
    print("场景11 意图与槽位填充情况：：")
    print(result11)
    assert set(result11["intents"]) == {"weather", "flight"}, "未识别组合意图"
    assert result11["slots"]["weather"]["city"] == "北京", "weather city槽位不匹配"
    assert result11["slots"]["weather"]["date"] == "2025-09-15", "weather date槽位不匹配"
    assert result11["slots"]["flight"]["departure_city"] == "北京", "flight departure_city槽位不匹配"
    assert result11["slots"]["flight"]["arrival_city"] == "上海", "flight arrival_city槽位不匹配"
    assert result11["slots"]["flight"]["date"] == "2025-09-15", "flight date槽位不匹配"
    print("\n")

    # 测试场景12：组合意图（weather + flight，缺失槽位）
    query12 = "明天天气和机票"
    print("场景12（组合意图weather + flight，缺失槽位）：", query12)
    result12 = recognize_intent(conversation_history, query12, current_date)
    print("场景12 意图与槽位填充情况：")
    print(result12)
    assert set(result12["intents"]) == {"weather", "flight"}, "未识别组合意图"
    assert "missing_slots" in result12, "未返回missing_slots"
    assert "city" in result12["missing_slots"]["weather"], "weather未识别缺失city"
    assert "departure_city" in result12["missing_slots"]["flight"], "flight未识别缺失departure_city"
    assert "arrival_city" in result12["missing_slots"]["flight"], "flight未识别缺失arrival_city"
    assert "follow_up_message" in result12, "未返回追问消息"

    print("\n所有场景验证通过！")
import json


def process_response(response, query_type):
    """
    处理MCP返回的响应，根据query_type格式化输出。
    :param response: MCP返回的JSON字符串或字典
    :param query_type: 查询类型（train, flight, concert）
    :return: 格式化后的response_text
    """
    if isinstance(response, str):
        response = json.loads(response)

    if response.get("status") == "no_data":
        return f"{response['message']} 如果需要其他日期，请补充."

    data = response.get("data", [])
    response_text = ""
    for d in data:
        if query_type == "train":
            response_text += f"{d['departure_city']} 到 {d['arrival_city']} {d['departure_time']}: 车次 {d['train_number']}，{d['seat_type']}，票价 {d['price']}元，剩余 {d['remaining_seats']} 张\n"
        elif query_type == "flight":
            response_text += f"{d['departure_city']} 到 {d['arrival_city']} {d['departure_time']}: 航班 {d['flight_number']}，{d['cabin_type']}，票价 {d['price']}元，剩余 {d['remaining_seats']} 张\n"
        elif query_type == "concert":
            response_text += f"{d['city']} {d['start_time']}: {d['artist']} 演唱会，{d['ticket_type']}，场地 {d['venue']}，票价 {d['price']}元，剩余 {d['remaining_seats']} 张\n"

    if not response_text:
        return "无结果。如果需要其他日期，请补充."

    return response_text.strip()


# 验证逻辑
def validate_response_processing():
    print("=== 验证响应处理逻辑 ===")

    # 测试场景1：train查询，有数据
    response_train = {
        "status": "success",
        "data": [
            {
                "departure_city": "北京",
                "arrival_city": "上海",
                "departure_time": "2025-09-15 08:00",
                "train_number": "G123",
                "seat_type": "二等座",
                "price": 553,
                "remaining_seats": 20
            },
            {
                "departure_city": "北京",
                "arrival_city": "上海",
                "departure_time": "2025-09-15 10:00",
                "train_number": "G126",
                "seat_type": "二等座",
                "price":600,
                "remaining_seats": 20
            }
        ]
    }
    result1 = process_response(response_train, "train")
    print("\n场景1（train查询，有数据）：")
    print(result1)
    assert "北京 到 上海" in result1, "train结果未包含出发/到达城市"
    assert "车次 G123" in result1, "train结果未包含车次"

    # 测试场景2：flight查询，有数据
    response_flight = {
        "status": "success",
        "data": [
            {
                "departure_city": "上海",
                "arrival_city": "广州",
                "departure_time": "2025-09-15 10:00",
                "flight_number": "CZ1234",
                "cabin_type": "经济舱",
                "price": 1200,
                "remaining_seats": 15
            }
        ]
    }
    result2 = process_response(response_flight, "flight")
    print("\n场景2（flight查询，有数据）：")
    print(result2)
    assert "上海 到 广州" in result2, "flight结果未包含出发/到达城市"
    assert "航班 CZ1234" in result2, "flight结果未包含航班号"

    # 测试场景3：concert查询，有数据
    response_concert = {
        "status": "success",
        "data": [
            {
                "city": "北京",
                "start_time": "2025-09-15 19:00",
                "artist": "周杰伦",
                "ticket_type": "VIP",
                "venue": "工人体育场",
                "price": 1800,
                "remaining_seats": 5
            }
        ]
    }
    result3 = process_response(response_concert, "concert")
    print("\n场景3（concert查询，有数据）：")
    print(result3)
    assert "北京 2025-09-15 19:00" in result3, "concert结果未包含城市和时间"
    assert "周杰伦 演唱会" in result3, "concert结果未包含艺人"

    # 测试场景4：no_data情况
    response_no_data = {
        "status": "no_data",
        "message": "无可用数据"
    }
    result4 = process_response(response_no_data, "train")
    print("\n场景4（no_data情况）：")
    print(result4)
    assert "无可用数据 如果需要其他日期，请补充" in result4, "no_data结果未包含预期消息"

    print("\n验证通过！")


if __name__ == '__main__':
    validate_response_processing()
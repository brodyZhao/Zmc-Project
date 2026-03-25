import requests  
import json
from config import Config

config = Config()

# -------------------------
# 参数说明:
# API_KEY  : 和风天气开放平台API的访问密钥，用于身份验证
# url      : 请求的API地址，此处为北京区域（location=101010100）的30天天气预报接口
# headers  : 请求头，X-QW-Api-Key为API访问密钥，Accept-Encoding=gzip表示可接受gzip压缩响应
# timeout  : 超时时间（秒），防止请求长时间无响应
# -------------------------

# API_KEY = "83a5c6985b434cea940267a777292d7f"  # 替换为自己的API KEY
# url = "https://m37fc22nxa.re.qweatherapi.com/v7/weather/30d?location=101010100"  # 替换为自己的API HOST
API_KEY = config.weather_api_key
url = config.weather_base_url + "?location=101010100"
headers = {
    "X-QW-Api-Key": API_KEY,  # 认证信息
    "Accept-Encoding": "gzip",  # 支持gzip压缩，但不是强制
}

try:
    print("正在请求API...")
    # 发起GET请求，最多等待10秒
    response = requests.get(url, headers=headers, timeout=10)
    print('response--->', response)
    # 取得响应的文本内容（字符串格式的JSON）
    data = response.text
    # 解析字符串JSON为Python字典
    parsed_data = json.loads(data)
    print("直接解析成功！")
    print(parsed_data)
except requests.RequestException as e:
    print(f"直接解析失败哦: {e}")

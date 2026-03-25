# 定义配置文件
class Config(object):
    def __init__(self):
        # 大模型配置信息
        self.api_key = "sk-2eaee1d6c4f8468385307b96a3269492"
        self.api_url = "https://api.deepseek.com"
        self.model_name = "deepseek-chat"  # 支持function call

        # 数据库配置信息
        self.db_host = "localhost"
        self.db_port = 3306
        self.db_user = "root"
        self.db_password = "123456"
        self.db_database = "travel_rag"

        # 和风天气配置信息
        self.weather_api_key = "83a5c6985b434cea940267a777292d7f"
        # 修改为你的和风天气API HOST
        self.weather_api_host = "m37fc22nxa.re.qweatherapi.com"
        self.weather_base_url = f"https://{self.weather_api_host}/v7/weather/30d"
        self.weather_city_codes = {
            "北京": "101010100",
            "上海": "101020100",
            "广州": "101280101",
            "深圳": "101280601"}


if __name__ == '__main__':
    config = Config()
    print(config.weather_base_url)
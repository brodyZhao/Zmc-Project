response_weather= {
        "status": "success",
        "data": [
            {
                "city": "北京",
                "fx_date": "2025-09-15",
                "text_day": "多云",
                "text_night": "晴",
                "temp_min": "15",
                "temp_max": "25",
                "humidity": "60",
                "wind_dir_day": "南风",
                "precip": "0.1"
            }
        ]
    }

response_text = "\n".join([f"{d['city']} {d['fx_date']}: {d['text_day']}（夜间 {d['text_night']}），温度 {d['temp_min']}-{d['temp_max']}°C，湿度 {d['humidity']}%，风向 {d['wind_dir_day']}，降水 {d['precip']}mm"
                                  for d in response_weather["data"]])
print(response_text)
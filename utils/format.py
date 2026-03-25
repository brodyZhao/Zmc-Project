"""
将查询的数据类型进行转换成python数据类型
"""
import json
from datetime import date, datetime, timedelta
from decimal import Decimal


# 自定义格式编码方法
def default_encoder(obj):  # 定义编码器方法，用于格式化单个对象
    """
    :param obj: 对象
    :return: 编码后的对象
    """
    # isinstance(): 判断对象是否属于指定的类型
    if isinstance(obj, datetime):  # 检查是否为datetime，返回带时间的格式化字符串
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, date):  # 检查是否为date，返回日期格式化字符串
        return obj.strftime('%Y-%m-%d')
    if isinstance(obj, timedelta):  # 检查是否为timedelta，转换为字符串
        return str(obj)
    if isinstance(obj, Decimal):  # 检查是否为Decimal，转换为浮点数
        return float(obj)
    return obj  # 否则返回原对象


# 定义自定义JSON编码器类，继承自json.JSONEncoder，用于处理非标准类型序列化
class DateEncoder(json.JSONEncoder):
    def default(self, obj):  # 重写default方法，处理序列化时的默认对象转换
        if isinstance(obj, (date, datetime)):  # 检查对象是否为date或datetime类型，对于datetime返回带时间的字符串，对于date返回日期字符串
            return obj.strftime('%Y-%m-%d %H:%M:%S') if isinstance(obj, datetime) else obj.strftime('%Y-%m-%d')
        if isinstance(obj, timedelta):  # 检查对象是否为timedelta类型，将时间差转换为字符串
            return str(obj)
        if isinstance(obj, Decimal):  # 检查对象是否为Decimal类型，将Decimal转换为浮点数以兼容JSON
            return float(obj)
        return super().default(obj)  # 对于其他类型，调用父类默认方法


if __name__ == '__main__':
    print(default_encoder(datetime(2025, 8, 11, 8, 0)))
    print(default_encoder(date(2025, 8, 11)))
    print(default_encoder(timedelta(days=1)))
    print(default_encoder(Decimal('123.45')))
    print(type(Decimal('123.45')))
    print(type(default_encoder(Decimal('123.45'))))
    print('*' * 80)

    encoder = DateEncoder()
    print(encoder.default(datetime(2025, 8, 11, 8, 0)))
    print(encoder.default(date(2025, 8, 11)))
    print(encoder.default(timedelta(days=1)))
    print(encoder.default(Decimal('123.45')))

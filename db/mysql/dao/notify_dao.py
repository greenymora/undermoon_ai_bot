from db.mysql.model import Notify
from db.mysql.mysql_manager import mysql
import json
import random

def get_sign_notify():
    return mysql.select_list("select content from ab_notify where type = %s", (1,), str)


def get_hello_notify():
    hello_notify_jsonstr = mysql.select_one(
        "select content from ab_notify where TIME(NOW()) >= start_time and TIME(NOW()) < end_time and type = %s",
        (2,),
        str)
    try:
        # 尝试解析JSON
        notify_list = json.loads(hello_notify_jsonstr)
        if isinstance(notify_list, list) and len(notify_list) > 0:
            # 随机选择一个回复
            return random.choice(notify_list)
    except:
        return random.choice("你好呀~")

def get_wait_notify():
    wait_notify_jsonstr = mysql.select_one("select content from ab_notify where type = %s", (3,), str)
    try:
        notify_list = json.loads(wait_notify_jsonstr)
        if isinstance(notify_list, list) and len(notify_list) > 0:
            return random.choice(notify_list)
    except:
        return random.choice("稍等一下，我正在思考呢~")

def get_back_notify():
    back_notify_jsonstr = mysql.select_one("select content from ab_notify where type = %s", (4,), str)
    try:
        notify_list = json.loads(back_notify_jsonstr)
        if isinstance(notify_list, list) and len(notify_list) > 0:
            return random.choice(notify_list)
    except:
        return random.choice("刚才发啥了？等我看一眼~")
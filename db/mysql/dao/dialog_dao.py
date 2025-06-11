from db.mysql.model import Dialog
from db.mysql.mysql_manager import mysql


def has_dialog_in_pass_time(user_id, chating_hour=2):
    # 检查用户在过去 chating_hour 小时内是否有对话记录
    return  mysql.select_one(
        "select count(*) from ab_dialog where user_id = %s and ask_time > DATE_SUB(NOW(), INTERVAL %s HOUR)",
        (user_id, chating_hour,),
        int
    ) > 0

def has_unreply_dialog(user_id):
    return mysql.select_one(
        "SELECT count(*) FROM ab_dialog WHERE user_id = %s AND reply_time is null",
        (user_id,),
        int
    ) > 0

def get_dialog_by_id(id):
    """根据ID获取对话"""
    return mysql.select_one("SELECT * FROM ab_dialog WHERE id = %s", (id,), Dialog)


def get_dialogs_by_user_id(user_id, limit=5):
    """根据用户ID获取对话列表"""
    return mysql.select_list(
        "SELECT * FROM ab_dialog WHERE user_id = %s ORDER BY ask_time DESC LIMIT %s",
        (user_id, limit,),
        Dialog
    )


def get_latest_dialog_by_user_id(user_id):
    """获取用户最新的对话"""
    return mysql.select_one(
        "SELECT * FROM ab_dialog WHERE user_id = %s ORDER BY ask_time DESC LIMIT 1",
        (user_id,),
        Dialog
    )


def insert_dialog(user_id, ask_type, ask_content):
    """
    插入新对话
    :param user_id: 用户ID
    :param ask_content: 提问内容
    :param ask_type: 提问类型，默认为'text'
    :return: 插入后的Dialog对象
    """
    # 执行插入操作并获取自增ID
    dialog_id = mysql.insert_and_get_id(
        "INSERT INTO ab_dialog (user_id, ask_type, ask_content, ask_time) VALUES (%s, %s, %s, NOW())",
        (user_id, ask_type, ask_content,)
    )

    if dialog_id:
        # 插入成功，根据ID查询并返回新插入的对话对象
        return mysql.select_one("SELECT * FROM ab_dialog WHERE id = %s", (dialog_id,), Dialog)
    else:
        return None


def update_dialog_reply(dialog_id, reply_content):
    """更新对话的回复内容和回复时间"""
    if not dialog_id or not reply_content:
        return
    return mysql.update(
        "UPDATE ab_dialog SET reply_content = %s, reply_time = NOW() WHERE id = %s",
        (reply_content, dialog_id)
    )


def get_user_dialog(user_id, limit=5):
    dialogs = get_dialogs_by_user_id(user_id, limit)
    dialogs.reverse()
    history = []
    for dialog in dialogs:
        history.append({"role": "user", "content": dialog.ask_content})
        history.append({"role": "assitant", "content": dialog.reply_content})
    return history

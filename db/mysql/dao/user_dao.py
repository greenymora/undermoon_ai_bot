from db.mysql.model import User
from db.mysql.mysql_manager import mysql


def get_user_by_id(id):
    return mysql.select_one("select * from ab_user where id = %s", (id,), User)


def get_user_by_openid(openid):
    user = mysql.select_one("select * from ab_user where openid = %s", (openid,), User)
    if not user:
        user = insert_user(openid)
    return user


def insert_user(openid):
    # 执行插入操作并获取自增ID
    user_id = mysql.insert_and_get_id("INSERT INTO ab_user (openid) VALUES (%s)", (openid,))
    
    if user_id:
        # 插入成功，根据ID查询并返回新插入的用户对象
        return mysql.select_one("SELECT * FROM ab_user WHERE id = %s", (user_id,), User)
    else:
        return None


def update_user(user):
    if not user:
        return

    if not user.id and not user.openid:
        raise ValueError("更新用户信息必须提供id或openid")

    sql = "update ab_user set "
    temp = ""
    for key, value in user.items():
        if key == 'create_time' or key == 'modify_time':
            continue
        if value is not None:
            temp += f"{key} = {value}, "
    if temp!= "":
        temp = temp[0:len(temp)-2]
        sql += temp + " where id = %s and openid = %s"
        mysql.update(sql, (user.id, user.openid))
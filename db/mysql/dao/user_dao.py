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

    # 获取User模型的所有列名（排除不需要更新的字段）
    exclude_fields = {'id', 'create_time', 'modify_time'}
    
    sql = "update ab_user set "
    update_params = []
    update_values = []
    
    # 遍历User对象的所有属性
    for column in user.__table__.columns:
        field_name = column.name
        if field_name in exclude_fields:
            continue
            
        # 获取属性值
        value = getattr(user, field_name, None)
        if value is not None:
            update_params.append(f"{field_name} = %s")
            update_values.append(value)
    
    if update_params:
        sql += ", ".join(update_params) + " where id = %s"
        update_values.append(user.id)
        mysql.update(sql, tuple(update_values))
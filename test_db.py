from db.mysql.dao import user_dao

user = user_dao.get_user_by_id(1)
print(user)

user.privacy_status = 2
user_dao.update_user(user)

user = user_dao.get_user_by_id(1)
print(user)
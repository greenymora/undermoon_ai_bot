from channel.wechatmp.wechatmp_channel import WechatMPChannel
from db.mysql.dao import user_dao
from common.log import logger


class PrivacyService:
    """隐私协议同意状态管理服务"""

    def check_privacy_agreed(self, user_id, openid):
        """检查用户是否已同意隐私协议"""
        if not user_id and not openid:
            return False
        if user_id:
            user = user_dao.get_user_by_id(user_id)
        else:
            user = user_dao.get_user_by_openid(openid)
        if not user:
            return False
        return user.privacy_status > 0

    def update_privacy_status(self, user_id, openid, status):
        """更新用户隐私协议同意状态"""
        if not user_id and not openid:
            return
        if not status:
            return
        if user_id:
            user = user_dao.get_user_by_id(user_id)
        else:
            user = user_dao.get_user_by_openid(openid)
        if not user:
            return
        user.privacy_status = status
        user_dao.update_user(user)

    # 向用户发送隐私协议确认消息
    def send_agree_notify(self, openid):
        success_notify = "看来你已立契~ 本神现在的业务有：\n\n"
        success_notify += "1. 教你该怎么跟对面的人聊\n"
        success_notify += "2. 分析聊天记录，指点一二\n"
        success_notify += "3. 帮你攻略某个对象\n\n"
        success_notify += "偶尔本神心情不错的时候，也会破例陪你聊个天🤷‍♀️ 不过先交代清楚➡️ 你是男是女？喜欢男的还是女的？"

        try:
            channel = WechatMPChannel()
            # 发送消息
            channel._send_text_message(openid, success_notify)
        except Exception as e:
            logger.error(f"[PrivacyAPI] 发送确认消息失败: {str(e)}")


# 创建单例实例
privacy_service = PrivacyService()
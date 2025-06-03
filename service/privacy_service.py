import os
import json
from datetime import datetime
from channel.wechatmp.wechatmp_client import WechatMPClient
from config import conf
from common.log import logger

class PrivacyService:
    """隐私协议同意状态管理服务"""
    
    def __init__(self):
        """初始化隐私服务"""
        self.data_file = "privacy_consents.json"
        self.consents = self._load_consents()

    
    def _load_consents(self):
        """从文件加载用户同意记录"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载隐私同意记录失败: {str(e)}")
                return {}
        return {}
    
    def _save_consents(self):
        """保存用户同意记录到文件"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.consents, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存隐私同意记录失败: {str(e)}")
            return False
    
    def check_privacy_agreed(self, user_id):
        """检查用户是否已同意隐私协议"""
        return user_id in self.consents
    
    def set_privacy_agreed(self, user_id, device_id=None, ip_address=None):
        """设置用户同意隐私协议"""
        if not user_id:
            return False
        
        self.consents[user_id] = {
            "agreed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "device_id": device_id,
            "ip_address": ip_address
        }
        
        return self._save_consents()
    
    # 向用户发送隐私协议确认消息
    def agree_notify(self, user_id):
        try:
            # 获取微信配置
            appid = conf().get('wechatmp_app_id')
            secret = conf().get('wechatmp_app_secret')
            
            if not appid or not secret:
                logger.error("[PrivacyAPI] 微信公众号配置不完整，无法发送消息")
                return False
            
            # 创建微信客户端
            client = WechatMPClient(appid, secret)
            
            # 使用chr()函数生成emoji避免编码问题
            # 女性耸肩emoji = 基础耸肩 + 零宽连接符 + 女性符号 + 变体选择符
            shrug_emoji = chr(0x1f937) + chr(0x200d) + chr(0x2640) + chr(0xfe0f)  # 🤷‍♀️
            arrow_emoji = chr(0x27a1)   # ➡️
            
            # 发送确认消息
            success_notify = f"""看来你已立契~ 本神现在的业务有：

1. 教你该怎么跟对面的人聊
2. 分析聊天记录，指点一二
3. 帮你攻略某个对象

偶尔本神心情不错的时候，也会破例陪你聊个天{shrug_emoji} 不过先交代清楚{arrow_emoji} 你是男是女？喜欢男的还是女的？"""
                            
            try:
                # 发送消息
                client.message.send_text(user_id, success_notify)
            except Exception as e:
                logger.error(f"[PrivacyAPI] 发送第确认消息失败: {str(e)}")
                raise e
            return True
        except Exception as e:
            logger.error(f"[PrivacyAPI] 发送确认消息异常: {str(e)}")
            return False


# 创建单例实例
privacy_service = PrivacyService()
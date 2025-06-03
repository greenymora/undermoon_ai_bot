import time
import threading
import os
import json

import web
from wechatpy import parse_message
from wechatpy.replies import create_reply

from bridge.context import *
from bridge.reply import *
from channel.wechatmp.common import *
from channel.wechatmp.wechatmp_channel import WechatMPChannel
from channel.wechatmp.wechatmp_message import WeChatMPMessage
from common.log import logger
from config import conf, subscribe_msg
from common.tmp_dir import TmpDir

# 本地文件存储已发欢迎语用户集合
WELCOME_USER_FILE = "sent_welcome_users.json"

def load_sent_welcome_users():
    if os.path.exists(WELCOME_USER_FILE):
        try:
            with open(WELCOME_USER_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            logger.error(f"[wechatmp] 加载sent_welcome_users.json失败: {str(e)}")
            return set()
    return set()

def save_sent_welcome_users(user_set):
    try:
        with open(WELCOME_USER_FILE, "w") as f:
            json.dump(list(user_set), f)
    except Exception as e:
        logger.error(f"[wechatmp] 保存sent_welcome_users.json失败: {str(e)}")

# This class is instantiated once per query
class Query:
    user_msg_buffer = {}
    user_timer = {}

    def GET(self):
        return verify_server(web.input())

    def POST(self):
        # Make sure to return the instance that first created, @singleton will do that.
        try:
            args = web.input()
            verify_server(args)
            channel = WechatMPChannel()
            message = web.data()
            encrypt_func = lambda x: x
            if args.get("encrypt_type") == "aes":
                logger.debug("[wechatmp] Receive encrypted post data:\n" + message.decode("utf-8"))
                if not channel.crypto:
                    raise Exception("Crypto not initialized, Please set wechatmp_aes_key in config.json")
                message = channel.crypto.decrypt_message(message, args.msg_signature, args.timestamp, args.nonce)
                encrypt_func = lambda x: channel.crypto.encrypt_message(x, args.nonce, args.timestamp)
            else:
                logger.debug("[wechatmp] Receive post data:\n" + message.decode("utf-8"))
            msg = parse_message(message)
            if msg.type in ["text", "voice", "image"]:
                wechatmp_msg = WeChatMPMessage(msg, client=channel.client)
                from_user = wechatmp_msg.from_user_id
                content = wechatmp_msg.content
                message_id = wechatmp_msg.msg_id

                logger.info(
                    "[wechatmp] {}:{} Receive post query {} {}: {}".format(
                        web.ctx.env.get("REMOTE_ADDR"),
                        web.ctx.env.get("REMOTE_PORT"),
                        from_user,
                        message_id,
                        content,
                    )
                )

                # 合并用户2秒内的多条消息，合并后统一处理
                def flush_buffer():
                    all_msgs = self.user_msg_buffer.pop(from_user, [])
                    merged_content = "\n".join(all_msgs)
                    self._handle_full_logic(wechatmp_msg, channel, merged_content, msg, conf, encrypt_func)
                    self.user_timer.pop(from_user, None)
                # 缓冲
                if from_user not in self.user_msg_buffer:
                    self.user_msg_buffer[from_user] = []
                self.user_msg_buffer[from_user].append(content)
                if from_user in self.user_timer:
                    self.user_timer[from_user].cancel()
                timer = threading.Timer(2.0, flush_buffer)
                self.user_timer[from_user] = timer
                timer.start()
                return "success"
            elif msg.type == "event":
                logger.info("[wechatmp] Event {} from {}".format(msg.event, msg.source))
                if msg.event in ["subscribe", "subscribe_scan"]:
                    # 获取用户ID
                    from_user_id = msg.source
                    
                    try:
                        # 方案一：将欢迎消息拆分为三条，通过客服消息API发送
                        welcome_messages = [
                            "人类，你是怎么找到我的？ 还挺前卫... 😏",
                            "礼貌自我介绍一下吧。其实呢...🤫我们月老部门做了一款帮你们牵红线的APP，在它上线之前，就派我这个情商最高的先来微信教你们聊聊天。",
                            "先说好，我是很有道德底线的👆一切聊天技术，都比不上当面表达真心。我要教你的...🌸 是如何学会用心沟通而已\n\n不过本神既已下凡... 须得遵守你们凡间条例😑 先签了这份契约罢\n\n⬇️点下方链接同意使用协议⬇️\nhttps://undermoon.net/bot"
                        ]
                        
                        # 依次发送欢迎消息
                        for i, message in enumerate(welcome_messages):
                            try:
                                # 延迟发送，避免消息发送过快
                                time.sleep(0.5)
                                channel._send_text_message(from_user_id, message)
                                logger.info(f"[wechatmp] 已发送第{i+1}条合并后的欢迎消息给用户 {from_user_id}")
                            except Exception as e:
                                logger.error(f"[wechatmp] 客服消息发送失败: {str(e)}")
                                # 如果客服消息发送失败，尝试方案二
                                raise e
                    except Exception as e:
                        # 方案二：使用被动回复的方式发送欢迎消息
                        logger.info("[wechatmp] 尝试使用被动回复的方式发送欢迎消息")
                        welcome_text = "人类，你是怎么找到我的？ 还挺前卫...\n\n礼貌自我介绍一下吧。其实呢...我是月老部门搞了一款帮你们牵红线的APP，在它上线之前，就派我这个情商最高的先来微信教你们聊聊天。\n\n更多信息请访问: https://undermoon.net/bot"
                        replyPost = create_reply(welcome_text, msg)
                        return encrypt_func(replyPost.render())
                    
                    # 返回空回复(如果客服消息发送成功)
                    return "success"
                else:
                    return "success"
            else:
                logger.info("暂且不处理")
            return "success"
        except Exception as exc:
            logger.exception(exc)
            return exc

    def _handle_full_logic(self, wechatmp_msg, channel, merged_content, msg, conf, encrypt_func):
        from_user = wechatmp_msg.from_user_id
        # 加载本地已发欢迎语用户集合
        if not hasattr(self, "sent_welcome_users"):
            self.sent_welcome_users = load_sent_welcome_users()
        # 已发过欢迎语但未同意隐私协议，发送隐私协议提醒
        if not channel.check_privacy_agreed(from_user):
            privacy_messages = [
                "本神不可随意窥探人心😞 你先签了这份契约...!!! \n ⬇️点下方链接同意使用协议⬇️",
                "https://undermoon.net/bot"
            ]
            for privacy_msg in privacy_messages:
                channel._send_text_message(from_user, privacy_msg)
            return
        # 获取最近N条历史（如5条），并组织为deepseek需要的结构
        try:
            from bot.chatgpt.chat_gpt_bot import get_user_chatlog_local
            N = 5  # 可根据需要调整
            history = get_user_chatlog_local(from_user, limit=N)
            deepseek_history = []
            for item in history:
                # 你可以根据msg_type判断role，这里假设'text'为user，其它为assistant
                role = "user" if item.get("msg_type") == "text" else "assistant"
                deepseek_history.append({"role": role, "content": item["content"]})
            logger.info(f"[active_reply] deepseek历史结构: {deepseek_history}")
            # 你可以在这里将 deepseek_history + 当前消息 作为上下文发给 deepseek
            # 例如: send_to_deepseek(deepseek_history + [{"role": "user", "content": merged_content}])
        except Exception as e:
            logger.error(f"[active_reply] 获取历史记录失败: {e}")
        # 非首次且已同意隐私协议，正常回复
        if msg.type == "voice" and wechatmp_msg.ctype == ContextType.TEXT and conf().get("voice_reply_voice", False):
            context = channel._compose_context(wechatmp_msg.ctype, merged_content, isgroup=False, desire_rtype=ReplyType.VOICE, msg=wechatmp_msg)
        elif msg.type == "image":
            media_id = msg.media_id
            from_user_id = msg.source
            to_user_id = msg.target
            if media_id:
                logger.info(f"[wechatmp] active_reply收到图片消息，media_id: {media_id}")
                try:
                    if not hasattr(channel, '_process_image_with_ocr'):
                        logger.error("[wechatmp] channel对象没有_process_image_with_ocr方法")
                        return
                    logger.info(f"[wechatmp] 启动线程处理图片OCR，media_id: {media_id}")
                    t = threading.Thread(
                        target=channel._process_image_with_ocr,
                        args=(media_id, from_user_id, to_user_id)
                    )
                    t.daemon = True
                    t.start()
                    logger.info(f"[wechatmp] 线程已启动，线程ID: {t.ident}")
                    return
                except Exception as e:
                    import traceback
                    logger.error(f"[wechatmp] 启动OCR处理线程异常: {str(e)}")
                    logger.error(f"[wechatmp] 异常堆栈: {traceback.format_exc()}")
                    return
        else:
            context = channel._compose_context(wechatmp_msg.ctype, merged_content, isgroup=False, msg=wechatmp_msg)
        if context:
            channel.produce(context)

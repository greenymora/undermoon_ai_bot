import time
import threading

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
from db.mysql.mysql_manager import mysql
from channel.wechatmp.passive_reply import hello_notify
from channel.wechatmp.passive_reply import wait_notify
from db.mysql.model import User, Dialog, Notify
from db.mysql.dao import notify_dao, user_dao, dialog_dao


def handle_message(message, channel):
    user = user_dao.get_user_by_openid(message.source)

    if user.privacy_status == 0:
        privacy_messages = [
            "本神不可随意窥探人心😞 你先签了这份契约...!!! \n ⬇️点下方链接同意使用协议⬇️",
            "https://undermoon.net/bot"
        ]
        for privacy_msg in privacy_messages:
            channel._send_text_message(user.openid, privacy_msg)
            
    elif user.privacy_status == 1:
        do_handle_message(message, channel)
    elif user.privacy_status == 2:
        do_handle_message(message, channel)


def do_handle_message(message, channel):
    wechatmp_msg = WeChatMPMessage(message, client=channel.client)
    user = user_dao.get_user_by_openid(wechatmp_msg.from_user_id)
    chat_history = dialog_dao.get_replied_dialog(user.id)
    hello_notify(user, channel)
    wait_notify(user, channel)

    # 插入对话记录并获取dialog
    dialog = dialog_dao.insert_dialog(user.id, message.type, wechatmp_msg.content)

    if message.type == "text":
        context = channel._compose_context(wechatmp_msg.ctype, wechatmp_msg.content, isgroup=False, msg=wechatmp_msg,)
        logger.info(f"[wechatmp] active_reply收到文本消息，content: {wechatmp_msg.content}")
    elif message.type == "voice" and wechatmp_msg.ctype == ContextType.TEXT and conf().get("voice_reply_voice", False):
        context = channel._compose_context(wechatmp_msg.ctype, wechatmp_msg.content, isgroup=False, desire_rtype=ReplyType.VOICE, msg=wechatmp_msg)
        logger.info(f"[wechatmp] active_reply收到语音消息，content: {wechatmp_msg.content}")
    elif message.type == "image":
        if wechatmp_msg.media_id:
            logger.info(f"[wechatmp] active_reply收到图片消息，media_id: {wechatmp_msg.media_id}")
            try:
                if not hasattr(channel, '_process_image_with_ocr'):
                    logger.error("[wechatmp] channel对象没有_process_image_with_ocr方法")
                    return
                logger.info(f"[wechatmp] 启动线程处理图片OCR，media_id: {wechatmp_msg.media_id}")
                t = threading.Thread(
                    target=channel._process_image_with_ocr,
                    args=(wechatmp_msg.media_id, wechatmp_msg.from_user_id, wechatmp_msg.to_user_id, dialog.id)
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
        context = channel._compose_context(wechatmp_msg.ctype, wechatmp_msg.content, isgroup=False, msg=wechatmp_msg)
    if context:
        context.chat_history = chat_history
        context['dialog_id'] = dialog.id
        channel.produce(context)


class Query:
    def GET(self):
        return verify_server(web.input())

    def POST(self):
        try:
            args = web.input()
            verify_server(args)
            # 微信公众号接收到的原始XML格式消息
            message_xml = web.data()
            encrypt_fun = lambda x: x
            channel = WechatMPChannel()
            if args.get("encrypt_type") == "aes":
                logger.debug("[wechatmp] Receive encrypted post data:\n" + message_xml.decode("utf-8"))
                if not channel.crypto:
                    raise Exception("Crypto not initialized, Please set wechatmp_aes_key in config.json")
                # 解密后的xml信息格式消息
                message_xml_decrypted = channel.crypto.decrypt_message(message_xml, args.msg_signature, args.timestamp, args.nonce)
                encrypt_fun = lambda x: channel.crypto.encrypt_message(x, args.nonce, args.timestamp)
            else:
                logger.debug("[wechatmp] Receive post data:\n" + message_xml.decode("utf-8"))
            # 解析原始XML后得到的结构化消息对象
            message = parse_message(message_xml_decrypted)
            if message.type in ["text", "voice", "image"]:
                handle_message(message, channel)

            elif message.type == "event":
                openid = message.source
                if message.event == "unsubscribe":
                    logger.info(f"【wechatmp】 用户{openid}取消订阅公众号了...")
                    return "success"
                if message.event in ["subscribe", "subscribe_scan"]:
                    # 用户初始化
                    user_dao.get_user_by_openid(openid)
                    logger.info(f"【wechatmp】 用户{openid}订阅了公众号")

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
                                channel._send_text_message(openid, message)
                                logger.info(f"[wechatmp] 已发送第{i + 1}条合并后的欢迎消息给用户 {openid}")
                            except Exception as e:
                                logger.error(f"[wechatmp] 客服消息发送失败: {str(e)}")
                                # 如果客服消息发送失败，尝试方案二
                                raise e
                    except Exception as e:
                        # 方案二：使用被动回复的方式发送欢迎消息
                        logger.info("[wechatmp] 尝试使用被动回复的方式发送欢迎消息")
                        welcome_text = "人类，你是怎么找到我的？ 还挺前卫...\n\n礼貌自我介绍一下吧。其实呢...我是月老部门搞了一款帮你们牵红线的APP，在它上线之前，就派我这个情商最高的先来微信教你们聊聊天。\n\n更多信息请访问: https://undermoon.net/bot"
                        replyPost = create_reply(welcome_text, message)
                        return encrypt_fun(replyPost.render())

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

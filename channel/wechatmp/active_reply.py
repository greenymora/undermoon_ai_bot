import time
import threading
import os

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


# This class is instantiated once per query
class Query:
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
                if msg.type == "voice" and wechatmp_msg.ctype == ContextType.TEXT and conf().get("voice_reply_voice", False):
                    context = channel._compose_context(wechatmp_msg.ctype, content, isgroup=False, desire_rtype=ReplyType.VOICE, msg=wechatmp_msg)
                elif msg.type == "image":
                    # 获取图片媒体ID
                    media_id = msg.media_id
                    from_user_id = msg.source
                    to_user_id = msg.target
                    
                    if media_id:
                        logger.info(f"[wechatmp] active_reply收到图片消息，media_id: {media_id}")
                        
                        try:
                            # 确保channel对象已初始化
                            if not hasattr(channel, '_process_image_with_ocr'):
                                logger.error("[wechatmp] channel对象没有_process_image_with_ocr方法")
                                return "系统配置错误，请联系管理员。"
                            
                            # 异步处理图片，避免阻塞主线程
                            logger.info(f"[wechatmp] 启动线程处理图片OCR，media_id: {media_id}")
                            t = threading.Thread(
                                target=channel._process_image_with_ocr,
                                args=(media_id, from_user_id, to_user_id)
                            )
                            t.daemon = True  # 设置为守护线程
                            t.start()
                            logger.info(f"[wechatmp] 线程已启动，线程ID: {t.ident}")
                            
                            return "正在分析图片中的聊天记录，这可能需要几秒钟时间...\n分析完成后会自动回复结果，请稍候。"
                        except Exception as e:
                            import traceback
                            logger.error(f"[wechatmp] 启动OCR处理线程异常: {str(e)}")
                            logger.error(f"[wechatmp] 异常堆栈: {traceback.format_exc()}")
                            return "处理图片时出现错误，请稍后再试。"
                else:
                    context = channel._compose_context(wechatmp_msg.ctype, content, isgroup=False, msg=wechatmp_msg)
                if context:
                    channel.produce(context)
                # The reply will be sent by channel.send() in another thread
                return "success"
            elif msg.type == "event":
                logger.info("[wechatmp] Event {} from {}".format(msg.event, msg.source))
                if msg.event in ["subscribe", "subscribe_scan"]:
                    reply_text = subscribe_msg()
                    if reply_text:
                        replyPost = create_reply(reply_text, msg)
                        return encrypt_func(replyPost.render())
                else:
                    return "success"
            else:
                logger.info("暂且不处理")
            return "success"
        except Exception as exc:
            logger.exception(exc)
            return exc

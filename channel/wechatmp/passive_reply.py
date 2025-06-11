import asyncio
import time
import threading
import os
import json
import random

import web
from wechatpy import parse_message
from wechatpy.replies import ImageReply, VoiceReply, create_reply
import textwrap
from bridge.context import *
from bridge.reply import *
from channel.wechatmp.common import *
from channel.wechatmp.wechatmp_channel import WechatMPChannel
from channel.wechatmp.wechatmp_message import WeChatMPMessage
from common.log import logger
from common.utils import split_string_by_utf8_length
from config import conf, subscribe_msg
from common.tmp_dir import TmpDir
from PIL import Image, ImageDraw, ImageFont
import io
from db.mysql.mysql_manager import mysql
from db.mysql.model import User, Dialog, Notify
from db.mysql.dao import notify_dao, user_dao, dialog_dao


def hello_notify(user, channel, chating_hour=2):
    """根据当前时间返回合适的问候回复"""
    # 检查用户在过去 chating_hour 小时内是否有对话记录
    has_dialog = dialog_dao.has_dialog_in_pass_time(user.id, chating_hour)

    # 如果没有对话记录，查询时间段内的回复配置
    if not has_dialog:
        hello_notify = notify_dao.get_hello_notify()
        channel._send_text_message(user.openid, hello_notify)


def wait_notify(user, channel):
    has_unreply_dialog = dialog_dao.has_unreply_dialog(user.id)

    if has_unreply_dialog:
        wait_notify = notify_dao.get_wait_notify()
        channel._send_text_message(user.openid, wait_notify)


# This class is instantiated once per query
class Query:
    def GET(self):
        return verify_server(web.input())

    def POST(self):
        try:
            args = web.input()
            verify_server(args)
            request_time = time.time()
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

            # 处理图片消息，检查是否为聊天记录截图
            if msg.type == "image":
                # 获取发送者和接收者信息
                from_user_id = msg.source
                to_user_id = msg.target

                # 检查用户是否同意隐私政策
                if not channel.check_privacy_agreed(from_user_id):
                    # 如果用户未同意隐私政策，发送隐私政策提醒
                    privacy_messages = channel.get_privacy_notice(from_user_id)
                    for privacy_msg in privacy_messages:
                        channel._send_text_message(from_user_id, privacy_msg)

                    # 返回成功，不继续处理消息
                    return "success"

                # 获取图片媒体ID
                media_id = msg.media_id

                if media_id:
                    logger.info(f"[wechatmp] 收到图片消息，media_id: {media_id}")

                    # 检查配置是否启用聊天记录分析
                    if conf().get("chat_record_analysis_enabled", False):
                        # 新增：发送正在分析图片的提示消息
                        prompt_message = "正在分析图片中的聊天记录，这可能需要一些时间..."
                        channel._send_text_message(from_user_id, prompt_message)

                        # 检查是否使用直接处理模式（用于调试）
                        if conf().get("chat_record_direct_process", False):
                            try:
                                logger.info(f"[wechatmp] 使用直接处理模式处理图片OCR")
                                # 直接处理，不使用线程
                                channel._process_image_with_ocr(media_id, from_user_id, to_user_id)
                                reply_text = "图片处理完成。"
                                reply = create_reply(reply_text, msg)
                                return encrypt_func(reply.render())
                            except Exception as e:
                                import traceback
                                logger.error(f"[wechatmp] 直接处理OCR异常: {str(e)}")
                                logger.error(f"[wechatmp] 异常堆栈: {traceback.format_exc()}")
                                reply_text = "处理图片时出现错误，请稍后再试。"
                                reply = create_reply(reply_text, msg)
                                return encrypt_func(reply.render())
                        else:
                            # 使用线程处理（原代码）
                            # 异步处理图片，避免阻塞主线程
                            logger.info(f"[wechatmp] 启动线程处理图片OCR，media_id: {media_id}")
                            t = threading.Thread(
                                target=channel._process_image_with_ocr,
                                args=(media_id, from_user_id, to_user_id)
                            )
                            t.daemon = True  # 设置为守护线程
                            t.start()
                            logger.info(f"[wechatmp] 线程已启动，线程ID: {t.ident}")

                            # 返回提示消息
                            reply_text = "正在分析图片中的聊天记录，这可能需要几秒钟时间...\n分析完成后会自动回复结果，请稍候。"
                            reply = create_reply(reply_text, msg)
                            return encrypt_func(reply.render())
                    else:
                        # 如果未启用聊天记录分析，告知用户
                        reply_text = "聊天记录分析功能未启用，请在配置文件中设置 chat_record_analysis_enabled 为 true。"
                        reply = create_reply(reply_text, msg)
                        return encrypt_func(reply.render())

            if msg.type in ["text", "voice", "image"]:
                wechatmp_msg = WeChatMPMessage(msg, client=channel.client)
                from_user = wechatmp_msg.from_user_id
                content = wechatmp_msg.content
                message_id = wechatmp_msg.msg_id

                # 检查用户是否同意隐私政策
                if not channel.check_privacy_agreed(from_user):
                    # 检查用户消息是否为同意隐私政策
                    if msg.type == "text" and channel.is_agree_privacy(content):
                        # 设置用户已同意隐私政策
                        channel.set_privacy_agreed(from_user)
                        reply_text = "感谢您同意使用协议，现在可以正常使用本服务了！"
                        replyPost = create_reply(reply_text, msg)
                        return encrypt_func(replyPost.render())
                    else:
                        # 如果用户未同意隐私政策，发送隐私政策提醒
                        privacy_messages = channel.get_privacy_notice(from_user)
                        for privacy_msg in privacy_messages:
                            channel._send_text_message(from_user, privacy_msg)
                        # 返回成功，不继续处理消息
                        return "success"

                # 新增：如果数据库查不到该用户（即首次发消息的历史用户），发送三条欢迎消息
                # 这里假设 check_privacy_agreed 返回 False 表示数据库无记录
                if not channel.check_privacy_agreed(from_user):
                    welcome_messages = [
                        "人类，你是怎么找到我的？ 还挺前卫... 😄",
                        "礼貌自我介绍一下吧。其实呢...😊我是月老部门搞了一款帮你们拆红线的APP，在它上线之前，就派我这个情商最高的先来微信教你们聊聊天。",
                        "先说好，我是很有道德底线的🧐—切聊天技术，都比不上当面表达真心。我要教你的...👍 是如何学会用心沟通而已"
                    ]
                    for i, message in enumerate(welcome_messages):
                        try:
                            time.sleep(0.5)
                            channel._send_text_message(from_user, message)
                        except Exception as e:
                            logger.error(f"[wechatmp] 历史用户欢迎消息发送失败: {str(e)}")
                    # 只发一次欢迎消息，后续消息不再重复
                    # 可以在数据库插入一条记录，或设置一个缓存避免重复

                supported = True
                if "【收到不支持的消息类型，暂无法显示】" in content:
                    supported = False  # not supported, used to refresh

                # New request
                if (
                    channel.cache_dict.get(from_user) is None
                    and from_user not in channel.running
                    or content.startswith("#")
                    and message_id not in channel.request_cnt  # insert the godcmd
                ):
                    # The first query begin
                    if msg.type == "voice" and wechatmp_msg.ctype == ContextType.TEXT and conf().get("voice_reply_voice", False):
                        context = channel._compose_context(wechatmp_msg.ctype, content, isgroup=False, desire_rtype=ReplyType.VOICE, msg=wechatmp_msg)
                    else:
                        context = channel._compose_context(wechatmp_msg.ctype, content, isgroup=False, msg=wechatmp_msg)
                    logger.debug("[wechatmp] context: {} {} {}".format(context, wechatmp_msg, supported))

                    if supported and context:
                        # 在被动回复模式下也需要插入对话记录并获取dialog_id
                        try:
                            user = user_dao.get_user_by_openid(from_user)
                            if user:
                                # 插入对话记录并获取dialog_id
                                dialog = dialog_dao.insert_dialog(user.id, msg.type, content)
                                context['dialog_id'] = dialog.id
                                logger.debug(f"[wechatmp] 被动回复模式插入对话记录，dialog_id: {dialog.id}")
                        except Exception as e:
                            logger.error(f"[wechatmp] 被动回复模式插入对话记录失败: {str(e)}")
                        # 新增：发送正在生成回复的提示消息
                        prompt_message = "正在生成回复，请稍候..."
                        channel._send_text_message(from_user, prompt_message)

                        channel.running.add(from_user)
                        channel.produce(context)
                    else:
                        trigger_prefix = conf().get("single_chat_prefix", [""])[0]
                        if trigger_prefix or not supported:
                            if trigger_prefix:
                                reply_text = textwrap.dedent(
                                    f"""\
                                    请输入'{trigger_prefix}'接你想说的话跟我说话。
                                    例如:
                                    {trigger_prefix}你好，很高兴见到你。"""
                                )
                            else:
                                reply_text = textwrap.dedent(
                                    """\
                                    你好，很高兴见到你。
                                    请跟我说话吧。"""
                                )
                        else:
                            logger.error(f"[wechatmp] unknown error")
                            reply_text = textwrap.dedent(
                                """\
                                未知错误，请稍后再试"""
                            )

                        replyPost = create_reply(reply_text, msg)
                        return encrypt_func(replyPost.render())

                # Wechat official server will request 3 times (5 seconds each), with the same message_id.
                # Because the interval is 5 seconds, here assumed that do not have multithreading problems.
                request_cnt = channel.request_cnt.get(message_id, 0) + 1
                channel.request_cnt[message_id] = request_cnt
                logger.info(
                    "[wechatmp] Request {} from {} {} {}:{}\n{}".format(
                        request_cnt, from_user, message_id, web.ctx.env.get("REMOTE_ADDR"), web.ctx.env.get("REMOTE_PORT"), content
                    )
                )

                task_running = True
                waiting_until = request_time + 4
                while time.time() < waiting_until:
                    if from_user in channel.running:
                        time.sleep(0.1)
                    else:
                        task_running = False
                        break

                reply_text = ""
                if task_running:
                    if request_cnt < 3:
                        # waiting for timeout (the POST request will be closed by Wechat official server)
                        time.sleep(2)
                        # and do nothing, waiting for the next request
                        return "success"
                    else:  # request_cnt == 3:
                        # return timeout message
                        reply_text = "【正在思考中，回复任意文字尝试获取回复】"
                        replyPost = create_reply(reply_text, msg)
                        return encrypt_func(replyPost.render())

                # reply is ready
                channel.request_cnt.pop(message_id)

                # no return because of bandwords or other reasons
                if from_user not in channel.cache_dict and from_user not in channel.running:
                    return "success"

                # Only one request can access to the cached data
                try:
                    (reply_type, reply_content) = channel.cache_dict[from_user].pop(0)
                    if not channel.cache_dict[from_user]:  # If popping the message makes the list empty, delete the user entry from cache
                        del channel.cache_dict[from_user]
                except IndexError:
                    return "success"

                if reply_type == "text":
                    if len(reply_content.encode("utf8")) <= MAX_UTF8_LEN:
                        reply_text = reply_content
                    else:
                        continue_text = "\n【未完待续，回复任意文字以继续】"
                        splits = split_string_by_utf8_length(
                            reply_content,
                            MAX_UTF8_LEN - len(continue_text.encode("utf-8")),
                            max_split=1,
                        )
                        reply_text = splits[0] + continue_text
                        channel.cache_dict[from_user].append(("text", splits[1]))

                    logger.info(
                        "[wechatmp] Request {} do send to {} {}: {}\n{}".format(
                            request_cnt,
                            from_user,
                            message_id,
                            content,
                            reply_text,
                        )
                    )
                    replyPost = create_reply(reply_text, msg)
                    return encrypt_func(replyPost.render())

                elif reply_type == "voice":
                    media_id = reply_content
                    asyncio.run_coroutine_threadsafe(channel.delete_media(media_id), channel.delete_media_loop)
                    logger.info(
                        "[wechatmp] Request {} do send to {} {}: {} voice media_id {}".format(
                            request_cnt,
                            from_user,
                            message_id,
                            content,
                            media_id,
                        )
                    )
                    replyPost = VoiceReply(message=msg)
                    replyPost.media_id = media_id
                    return encrypt_func(replyPost.render())

                elif reply_type == "image":
                    media_id = reply_content
                    asyncio.run_coroutine_threadsafe(channel.delete_media(media_id), channel.delete_media_loop)
                    logger.info(
                        "[wechatmp] Request {} do send to {} {}: {} image media_id {}".format(
                            request_cnt,
                            from_user,
                            message_id,
                            content,
                            media_id,
                        )
                    )
                    replyPost = ImageReply(message=msg)
                    replyPost.media_id = media_id
                    return encrypt_func(replyPost.render())

            elif msg.type == "text":
                content = msg.content.strip()

                # 检查是否是测试OCR功能的命令
                if content == "测试OCR" and conf().get("chat_record_analysis_enabled", False):
                    try:
                        # 创建一个简单的测试图片
                        from PIL import Image, ImageDraw, ImageFont
                        import io

                        # 创建一个白色背景的图片
                        img = Image.new('RGB', (400, 200), color = (255, 255, 255))
                        d = ImageDraw.Draw(img)

                        # 尝试加载字体，如果失败则使用默认字体
                        try:
                            font = ImageFont.truetype("simhei.ttf", 20)
                        except:
                            font = ImageFont.load_default()

                        # 在图片上写文字
                        d.text((10, 10), "对方: 你好，最近怎么样？", fill=(0, 0, 0), font=font)
                        d.text((200, 50), "我: 还不错，谢谢关心", fill=(0, 0, 0), font=font)
                        d.text((10, 90), "对方: 有空一起吃饭吧", fill=(0, 0, 0), font=font)
                        d.text((200, 130), "我: 好的，周末有空", fill=(0, 0, 0), font=font)

                        # 保存图片到内存
                        img_io = io.BytesIO()
                        img.save(img_io, 'PNG')
                        img_io.seek(0)

                        # 保存到临时文件
                        test_image_path = TmpDir().path() + "ocr_test.png"
                        with open(test_image_path, 'wb') as f:
                            f.write(img_io.getvalue())

                        logger.info(f"[wechatmp] 创建测试图片: {test_image_path}")

                        # 上传图片到微信服务器
                        with open(test_image_path, 'rb') as f:
                            response = channel.client.media.upload("image", ("ocr_test.png", f, "image/png"))

                        if "media_id" in response:
                            media_id = response["media_id"]
                            logger.info(f"[wechatmp] 测试图片上传成功，media_id: {media_id}")

                            # 处理测试图片
                            channel._process_image_with_ocr(media_id, msg.source, msg.target)

                            reply_text = "OCR测试已启动，请等待结果。"
                        else:
                            reply_text = "上传测试图片失败。"

                        reply = create_reply(reply_text, msg)
                        return encrypt_func(reply.render())
                    except Exception as e:
                        import traceback
                        logger.error(f"[wechatmp] OCR测试异常: {str(e)}")
                        logger.error(f"[wechatmp] 异常堆栈: {traceback.format_exc()}")
                        reply_text = "OCR测试失败，请查看日志。"
                        reply = create_reply(reply_text, msg)
                        return encrypt_func(reply.render())

            elif msg.type == "event":
                logger.info("[wechatmp] Event {} from {}".format(msg.event, msg.source))
                if msg.event in ["subscribe", "subscribe_scan"]:
                    # 获取用户ID
                    from_user_id = msg.source
                    channel = WechatMPChannel()

                    # 发送多条欢迎消息
                    welcome_messages = [
                        "人类，你是怎么找到我的？ 还挺前卫... 😄",
                        "礼貌自我介绍一下吧。其实呢...😊我11月老部门搞了一款帮你们拆红线的APP，在它上线之前，就派我这个情商最高的先来微信教你们聊聊天。",
                        "先说好，我是很有道德底线的🧐—切聊天技术，都比不上当面表达真心。我要教你的...👍 是如何学会用心沟通而已",
                        "不过本神略已下凡... 须得遵守你们几间条例😄 先签了这份契约",
                        "https://undermoon.net/AI_bot/privacy"
                    ]

                    # 不使用官方配置的订阅消息，直接发送自定义的欢迎消息
                    # 依次发送5条欢迎消息
                    for i, message in enumerate(welcome_messages):
                        try:
                            # 延迟发送，避免消息发送过快
                            time.sleep(0.5)
                            channel._send_text_message(from_user_id, message)
                            logger.info(f"[wechatmp] 已发送第{i+1}条欢迎消息给用户 {from_user_id}")
                        except Exception as e:
                            logger.error(f"[wechatmp] 发送欢迎消息失败: {str(e)}")

                    # 返回空回复，因为我们已经通过客服消息发送了欢迎语
                    return "success"
                else:
                    return "success"
            else:
                logger.info("暂且不处理")
            return "success"
        except Exception as exc:
            logger.exception(exc)
            return exc

    def _handle_text_message(self, msg, encrypt_func):
        content = msg.content.strip()

        # 检查是否是手动触发聊天记录分析的命令
        if content == "分析最近图片" and conf().get("chat_record_analysis_enabled", False):
            # 获取用户最近发送的图片
            from_user_id = msg.source
            to_user_id = msg.target

            # 返回提示消息
            reply_text = "请先发送一张聊天记录截图，然后我会为您分析。"
            reply = create_reply(reply_text, msg)
            return encrypt_func(reply.render())

        # 在处理图片消息部分添加简化处理选项
        if conf().get("use_simple_image_process", False):
            # 使用简化版处理
            threading.Thread(
                target=channel._simple_process_image,
                args=(media_id, from_user_id, to_user_id)
            ).start()

            reply_text = "正在处理您的图片，请稍候..."
            reply = create_reply(reply_text, msg)
            return encrypt_func(reply.render())

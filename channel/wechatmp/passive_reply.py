import asyncio
import time
import threading
import os

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
                
                # 获取图片媒体ID
                media_id = msg.media_id
                
                if media_id:
                    logger.info(f"[wechatmp] 收到图片消息，media_id: {media_id}")
                    
                    # 检查配置是否启用聊天记录分析
                    if conf().get("chat_record_analysis_enabled", False):
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
                        d.text((10,10), "对方: 你好，最近怎么样？", fill=(0,0,0), font=font)
                        d.text((200,50), "我: 还不错，谢谢关心", fill=(0,0,0), font=font)
                        d.text((10,90), "对方: 有空一起吃饭吧", fill=(0,0,0), font=font)
                        d.text((200,130), "我: 好的，周末有空", fill=(0,0,0), font=font)
                        
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

# -*- coding: utf-8 -*-
import asyncio
import imghdr
import io
import os
import threading
import time

import requests
import web
from wechatpy.crypto import WeChatCrypto
from wechatpy.exceptions import WeChatClientException
from collections import defaultdict
from PIL import Image
from paddleocr import PaddleOCR
import re

from bridge.context import *
from bridge.reply import *
from channel.chat_channel import ChatChannel
from channel.wechatmp.common import *
from channel.wechatmp.wechatmp_client import WechatMPClient
from common.log import logger
from common.singleton import singleton
from common.utils import split_string_by_utf8_length, remove_markdown_symbol
from config import conf
from voice.audio_convert import any_to_mp3, split_audio
from channel.wechatmp.wechatmp_message import WeChatMPMessage
from common.tmp_dir import TmpDir
from db.mysql.model import User, Dialog, Notify
from db.mysql.dao import user_dao, dialog_dao, notify_dao

# If using SSL, uncomment the following lines, and modify the certificate path.
# from cheroot.server import HTTPServer
# from cheroot.ssl.builtin import BuiltinSSLAdapter
# HTTPServer.ssl_adapter = BuiltinSSLAdapter(
#         certificate='/ssl/cert.pem',
#         private_key='/ssl/cert.key')

# 初始化OCR，使用更简单的配置
try:
    ocr = PaddleOCR(use_angle_cls=False, lang='ch', use_gpu=False)
    logger.info("[wechatmp] PaddleOCR初始化成功")
except Exception as e:
    logger.error(f"[wechatmp] PaddleOCR初始化失败: {str(e)}")
    import traceback
    logger.error(f"[wechatmp] PaddleOCR初始化异常堆栈: {traceback.format_exc()}")


@singleton
class WechatMPChannel(ChatChannel):
    def __init__(self, passive_reply=True):
        super().__init__()
        self.passive_reply = passive_reply
        self.NOT_SUPPORT_REPLYTYPE = []
        appid = conf().get("wechatmp_app_id")
        secret = conf().get("wechatmp_app_secret")
        token = conf().get("wechatmp_token")
        aes_key = conf().get("wechatmp_aes_key")
        self.client = WechatMPClient(appid, secret)
        self.crypto = None
        if aes_key:
            self.crypto = WeChatCrypto(token, aes_key, appid)
        if self.passive_reply:
            # Cache the reply to the user's first message
            self.cache_dict = defaultdict(list)
            # Record whether the current message is being processed
            self.running = set()
            # Count the request from wechat official server by message_id
            self.request_cnt = dict()
            # The permanent media need to be deleted to avoid media number limit
            self.delete_media_loop = asyncio.new_event_loop()
            t = threading.Thread(target=self.start_loop, args=(self.delete_media_loop,))
            t.setDaemon(True)
            t.start()

    def startup(self):
        if self.passive_reply:
            urls = ("/wx", "channel.wechatmp.passive_reply.Query")
        else:
            urls = ("/wx", "channel.wechatmp.active_reply.Query")
        app = web.application(urls, globals(), autoreload=False)
        port = conf().get("wechatmp_port", 8080)
        web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", port))

    def start_loop(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    async def delete_media(self, media_id):
        logger.debug("[wechatmp] permanent media {} will be deleted in 10s".format(media_id))
        await asyncio.sleep(10)
        self.client.material.delete(media_id)
        logger.info("[wechatmp] permanent media {} has been deleted".format(media_id))

    def send(self, reply: Reply, context: Context):
        receiver = context["receiver"]
        if self.passive_reply:
            if reply.type == ReplyType.TEXT or reply.type == ReplyType.INFO or reply.type == ReplyType.ERROR:
                reply_text = remove_markdown_symbol(reply.content)
                logger.info("[wechatmp] text cached, receiver {}\n{}".format(receiver, reply_text))
                self.cache_dict[receiver].append(("text", reply_text))
            elif reply.type == ReplyType.VOICE:
                voice_file_path = reply.content
                duration, files = split_audio(voice_file_path, 60 * 1000)
                if len(files) > 1:
                    logger.info("[wechatmp] voice too long {}s > 60s , split into {} parts".format(duration / 1000.0, len(files)))

                for path in files:
                    # support: <2M, <60s, mp3/wma/wav/amr
                    try:
                        with open(path, "rb") as f:
                            response = self.client.material.add("voice", f)
                            logger.debug("[wechatmp] upload voice response: {}".format(response))
                            f_size = os.fstat(f.fileno()).st_size
                            time.sleep(1.0 + 2 * f_size / 1024 / 1024)
                            # todo check media_id
                    except WeChatClientException as e:
                        logger.error("[wechatmp] upload voice failed: {}".format(e))
                        return
                    media_id = response["media_id"]
                    logger.info("[wechatmp] voice uploaded, receiver {}, media_id {}".format(receiver, media_id))
                    self.cache_dict[receiver].append(("voice", media_id))

            elif reply.type == ReplyType.IMAGE_URL:  # 从网络下载图片
                img_url = reply.content
                pic_res = requests.get(img_url, stream=True)
                image_storage = io.BytesIO()
                for block in pic_res.iter_content(1024):
                    image_storage.write(block)
                image_storage.seek(0)
                image_type = imghdr.what(image_storage)
                filename = receiver + "-" + str(context["msg"].msg_id) + "." + image_type
                content_type = "image/" + image_type
                try:
                    response = self.client.material.add("image", (filename, image_storage, content_type))
                    logger.debug("[wechatmp] upload image response: {}".format(response))
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload image failed: {}".format(e))
                    return
                media_id = response["media_id"]
                logger.info("[wechatmp] image uploaded, receiver {}, media_id {}".format(receiver, media_id))
                self.cache_dict[receiver].append(("image", media_id))
            elif reply.type == ReplyType.IMAGE:  # 从文件读取图片
                image_storage = reply.content
                image_storage.seek(0)
                image_type = imghdr.what(image_storage)
                filename = receiver + "-" + str(context["msg"].msg_id) + "." + image_type
                content_type = "image/" + image_type
                try:
                    response = self.client.material.add("image", (filename, image_storage, content_type))
                    logger.debug("[wechatmp] upload image response: {}".format(response))
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload image failed: {}".format(e))
                    return
                media_id = response["media_id"]
                logger.info("[wechatmp] image uploaded, receiver {}, media_id {}".format(receiver, media_id))
                self.cache_dict[receiver].append(("image", media_id))
            elif reply.type == ReplyType.VIDEO_URL:  # 从网络下载视频
                video_url = reply.content
                video_res = requests.get(video_url, stream=True)
                video_storage = io.BytesIO()
                for block in video_res.iter_content(1024):
                    video_storage.write(block)
                video_storage.seek(0)
                video_type = 'mp4'
                filename = receiver + "-" + str(context["msg"].msg_id) + "." + video_type
                content_type = "video/" + video_type
                try:
                    response = self.client.material.add("video", (filename, video_storage, content_type))
                    logger.debug("[wechatmp] upload video response: {}".format(response))
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload video failed: {}".format(e))
                    return
                media_id = response["media_id"]
                logger.info("[wechatmp] video uploaded, receiver {}, media_id {}".format(receiver, media_id))
                self.cache_dict[receiver].append(("video", media_id))

            elif reply.type == ReplyType.VIDEO:  # 从文件读取视频
                video_storage = reply.content
                video_storage.seek(0)
                video_type = 'mp4'
                filename = receiver + "-" + str(context["msg"].msg_id) + "." + video_type
                content_type = "video/" + video_type
                try:
                    response = self.client.material.add("video", (filename, video_storage, content_type))
                    logger.debug("[wechatmp] upload video response: {}".format(response))
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload video failed: {}".format(e))
                    return
                media_id = response["media_id"]
                logger.info("[wechatmp] video uploaded, receiver {}, media_id {}".format(receiver, media_id))
                self.cache_dict[receiver].append(("video", media_id))

        else:
            if reply.type == ReplyType.TEXT or reply.type == ReplyType.INFO or reply.type == ReplyType.ERROR:
                reply_text = reply.content
                MAX_UTF8_LEN = conf().get("single_reply_max_len", 1800) # 微信单条消息限制

                # 新的智能拆分逻辑
                current_segment = ""
                sentences = re.split(r'([。？！.?!\n])', reply_text) # 按标点和换行符分割，并保留分隔符

                for i, sentence in enumerate(sentences):
                    if not sentence:
                        continue

                    # 计算当前段落加上下一个句子的长度
                    test_segment = current_segment + sentence

                    # 如果加上当前句子不超过最大长度，则添加到当前段落
                    if len(test_segment.encode('utf-8')) <= MAX_UTF8_LEN:
                        current_segment = test_segment
                    else:
                        # 如果当前段落不为空，发送当前段落
                        if current_segment:
                            self.client.message.send_text(receiver, current_segment.strip())
                            logger.info(f"[wechatmp] 发送拆分消息到 {receiver}: {current_segment.strip()[:50]}...")
                            time.sleep(0.5) # 每发送一条消息后休眠
                        # 开始新的段落，当前句子作为新段落的开头
                        current_segment = sentence
                # 发送最后剩余的段落
                if current_segment:
                     self.client.message.send_text(receiver, current_segment.strip())
                     logger.info(f"[wechatmp] 发送最后拆分消息到 {receiver}: {current_segment.strip()[:50]}...")

                if context.get("dialog_id"):
                    dialog_dao.update_dialog_reply(context["dialog_id"], reply_text)
                logger.info("[wechatmp] Do send text to {}: {}".format(receiver, reply_text))

            elif reply.type == ReplyType.VOICE:
                try:
                    file_path = reply.content
                    file_name = os.path.basename(file_path)
                    file_type = os.path.splitext(file_name)[1]
                    if file_type == ".mp3":
                        file_type = "audio/mpeg"
                    elif file_type == ".amr":
                        file_type = "audio/amr"
                    else:
                        mp3_file = os.path.splitext(file_path)[0] + ".mp3"
                        any_to_mp3(file_path, mp3_file)
                        file_path = mp3_file
                        file_name = os.path.basename(file_path)
                        file_type = "audio/mpeg"
                    logger.info("[wechatmp] file_name: {}, file_type: {} ".format(file_name, file_type))
                    media_ids = []
                    duration, files = split_audio(file_path, 60 * 1000)
                    if len(files) > 1:
                        logger.info("[wechatmp] voice too long {}s > 60s , split into {} parts".format(duration / 1000.0, len(files)))
                    for path in files:
                        # support: <2M, <60s, AMR\MP3
                        response = self.client.media.upload("voice", (os.path.basename(path), open(path, "rb"), file_type))
                        logger.debug("[wechatcom] upload voice response: {}".format(response))
                        media_ids.append(response["media_id"])
                        os.remove(path)
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload voice failed: {}".format(e))
                    return

                try:
                    os.remove(file_path)
                except Exception:
                    pass

                for media_id in media_ids:
                    self.client.message.send_voice(receiver, media_id)
                    time.sleep(1)
                logger.info("[wechatmp] Do send voice to {}".format(receiver))
            elif reply.type == ReplyType.IMAGE_URL:  # 从网络下载图片
                img_url = reply.content
                pic_res = requests.get(img_url, stream=True)
                image_storage = io.BytesIO()
                for block in pic_res.iter_content(1024):
                    image_storage.write(block)
                image_storage.seek(0)
                image_type = imghdr.what(image_storage)
                filename = receiver + "-" + str(context["msg"].msg_id) + "." + image_type
                content_type = "image/" + image_type
                try:
                    response = self.client.media.upload("image", (filename, image_storage, content_type))
                    logger.debug("[wechatmp] upload image response: {}".format(response))
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload image failed: {}".format(e))
                    return
                self.client.message.send_image(receiver, response["media_id"])
                logger.info("[wechatmp] Do send image to {}".format(receiver))
            elif reply.type == ReplyType.IMAGE:  # 从文件读取图片
                image_storage = reply.content
                image_storage.seek(0)
                image_type = imghdr.what(image_storage)
                filename = receiver + "-" + str(context["msg"].msg_id) + "." + image_type
                content_type = "image/" + image_type
                try:
                    response = self.client.media.upload("image", (filename, image_storage, content_type))
                    logger.debug("[wechatmp] upload image response: {}".format(response))
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload image failed: {}".format(e))
                    return
                self.client.message.send_image(receiver, response["media_id"])
                logger.info("[wechatmp] Do send image to {}".format(receiver))
            elif reply.type == ReplyType.VIDEO_URL:  # 从网络下载视频
                video_url = reply.content
                video_res = requests.get(video_url, stream=True)
                video_storage = io.BytesIO()
                for block in video_res.iter_content(1024):
                    video_storage.write(block)
                video_storage.seek(0)
                video_type = 'mp4'
                filename = receiver + "-" + str(context["msg"].msg_id) + "." + video_type
                content_type = "video/" + video_type
                try:
                    response = self.client.media.upload("video", (filename, video_storage, content_type))
                    logger.debug("[wechatmp] upload video response: {}".format(response))
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload video failed: {}".format(e))
                    return
                self.client.message.send_video(receiver, response["media_id"])
                logger.info("[wechatmp] Do send video to {}".format(receiver))
            elif reply.type == ReplyType.VIDEO:  # 从文件读取视频
                video_storage = reply.content
                video_storage.seek(0)
                video_type = 'mp4'
                filename = receiver + "-" + str(context["msg"].msg_id) + "." + video_type
                content_type = "video/" + video_type
                try:
                    response = self.client.media.upload("video", (filename, video_storage, content_type))
                    logger.debug("[wechatmp] upload video response: {}".format(response))
                except WeChatClientException as e:
                    logger.error("[wechatmp] upload video failed: {}".format(e))
                    return
                self.client.message.send_video(receiver, response["media_id"])
                logger.info("[wechatmp] Do send video to {}".format(receiver))
        return

    def _success_callback(self, session_id, context, **kwargs):  # 线程异常结束时的回调函数
        logger.debug("[wechatmp] Success to generate reply, msgId={}".format(context["msg"].msg_id))
        if self.passive_reply:
            self.running.remove(session_id)

    def _fail_callback(self, session_id, exception, context, **kwargs):  # 线程异常结束时的回调函数
        logger.exception("[wechatmp] Fail to generate reply to user, msgId={}, exception={}".format(context["msg"].msg_id, exception))
        if self.passive_reply:
            assert session_id not in self.cache_dict
            self.running.remove(session_id)

    def _process_image_with_ocr(self, media_id, from_user_id, to_user_id):
        """处理图片OCR并解析聊天记录"""
        try:
            logger.info(f"[wechatmp] 开始处理图片OCR，media_id={media_id}")

            # 先发送一条消息安抚用户
            self._send_text_message(from_user_id, "已收到您的图片，正在分析中，这可能需要10-20秒时间...")

            # 下载图片
            image_path = TmpDir().path() + media_id + ".png"

            try:
                response = self.client.media.download(media_id)

                if response.status_code == 200:
                    with open(image_path, "wb") as f:
                        f.write(response.content)
                    logger.info(f"[wechatmp] 图片已保存到: {image_path}")
                else:
                    logger.error(f"[wechatmp] 下载图片失败，状态码: {response.status_code}")
                    self._send_text_message(from_user_id, "下载图片失败，请稍后重试。")
                    return
            except Exception as e:
                logger.error(f"[wechatmp] 下载图片异常: {str(e)}")
                self._send_text_message(from_user_id, "下载图片时出错，请稍后重试。")
                return

            # 进行OCR识别
            try:
                logger.info("[wechatmp] 开始OCR识别")
                result = ocr.ocr(image_path, cls=False)
                logger.info(f"[wechatmp] OCR识别完成，结果长度: {len(result) if result else 0}")
                if result and len(result) > 0 and result[0]:
                    logger.info(f"[wechatmp] OCR识别到的文本数量: {len(result[0])}")
                else:
                    logger.info("[wechatmp] OCR未识别到文本")
                    self._send_text_message(from_user_id, "未能识别出图片中的文字，请确保图片清晰可读。")
                    return
            except Exception as e:
                logger.error(f"[wechatmp] OCR识别异常: {str(e)}")
                import traceback
                logger.error(f"[wechatmp] OCR异常堆栈: {traceback.format_exc()}")
                self._send_text_message(from_user_id, "OCR识别过程中出现错误，请稍后重试。")
                return

            if not result or len(result) == 0 or not result[0]:
                logger.error("[wechatmp] OCR结果为空")
                self._send_text_message(from_user_id, "未能识别出图片中的文字，请确保图片清晰可读。")
                return

            # 提取识别出的文本并整理聊天记录
            try:
                logger.info("[wechatmp] 开始整理聊天记录")
                chat_history = self._organize_chat_history(result[0])
                logger.info(f"[wechatmp] 整理后的聊天记录: {chat_history[:100]}...")
                # 新增：获取最近N条历史，拼接成deepseek多轮结构
                try:
                    from bot.chatgpt.chat_gpt_bot import get_user_chatlog_local
                    N = 5  # 可根据需要调整
                    history = get_user_chatlog_local(from_user_id, limit=N)
                    deepseek_history = []
                    for item in history:
                        role = "user" if item.get("msg_type") == "text" else "assistant"
                        deepseek_history.append({"role": role, "content": item["content"]})
                    # OCR识别内容作为新一条user消息
                    deepseek_history.append({"role": "user", "content": chat_history})
                    logger.info(f"[wechatmp][ocr] deepseek历史结构: {deepseek_history}")
                    # 你可以在这里将 deepseek_history 作为上下文发给 deepseek
                    # 例如: send_to_deepseek(deepseek_history)
                except Exception as e:
                    logger.error(f"[wechatmp][ocr] 获取历史记录失败: {e}")
            except Exception as e:
                logger.error(f"[wechatmp] 整理聊天记录异常: {str(e)}")
                import traceback
                logger.error(f"[wechatmp] 整理聊天记录异常堆栈: {traceback.format_exc()}")
                self._send_text_message(from_user_id, "整理聊天记录时出现错误，请稍后重试。")
                return

            if not chat_history:
                logger.error("[wechatmp] 未能识别出有效的聊天记录")
                self._send_text_message(from_user_id, "未能识别出有效的聊天记录，请确保图片包含清晰的对话内容。")
                return

            # 发送最后一条进度消息
            self._send_text_message(from_user_id, "聊天记录提取完成，正在分析对话内容...")

            # 构建提示信息，告诉AI这是聊天记录
            prompt = f"以下是一段微信聊天记录截图中提取的文本，请帮我分析并解读对话内容，理清对话的逻辑和情感：\n\n{chat_history}"
            logger.info(f"[wechatmp] 构建的提示信息: {prompt[:100]}...")

            # 清理临时文件
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
                    logger.info(f"[wechatmp] 已删除临时文件: {image_path}")
            except Exception as e:
                logger.error(f"[wechatmp] 删除临时文件异常: {str(e)}")

            # 创建一个自定义消息封装类，适配微信公众号消息格式
            logger.info("[wechatmp] 创建自定义消息对象")
            class CustomMsg:
                def __init__(self):
                    self.id = f"ocr_{int(time.time())}"
                    self.time = int(time.time())
                    self.type = "text"
                    self.content = prompt
                    self.source = from_user_id
                    self.target = to_user_id

            # 创建消息对象
            custom_msg = CustomMsg()

            # 使用与WeChatMPMessage相同的接口创建消息对象
            wechatmp_msg = WeChatMPMessage(custom_msg, client=self.client)

            # 创建上下文
            context = self._compose_context(
                wechatmp_msg.ctype,
                wechatmp_msg.content,
                isgroup=False,
                msg=wechatmp_msg,
            )

            # 设置会话ID
            if context:
                context['session_id'] = f"user_{from_user_id}"
                context['receiver'] = from_user_id
                
                # 为OCR处理的消息也插入对话记录并获取dialog_id
                try:
                    user = user_dao.get_user_by_openid(from_user_id)
                    if user:
                        # 插入对话记录并获取dialog_id
                        dialog = dialog_dao.insert_dialog(user.id, "image", prompt)
                        context['dialog_id'] = dialog.id
                        logger.debug(f"[wechatmp] OCR处理插入对话记录，dialog_id: {dialog.id}")
                except Exception as e:
                    logger.error(f"[wechatmp] OCR处理插入对话记录失败: {str(e)}")

                # 将消息传递给AI处理
                logger.info(f"[wechatmp] 将OCR识别的聊天记录传递给AI处理")
                self.produce(context)
            else:
                logger.error("[wechatmp] 无法创建有效的上下文")
                self._send_text_message(from_user_id, "处理聊天记录时出现错误，请稍后重试。")

        except Exception as e:
            import traceback
            logger.error(f"[wechatmp] OCR处理异常: {str(e)}")
            logger.error(f"[wechatmp] 异常堆栈: {traceback.format_exc()}")
            self._send_text_message(from_user_id, "处理图片时出现错误，请稍后重试。")

    def _organize_chat_history(self, ocr_result):
        """整理OCR识别出的聊天记录，去除不必要的信息和无效内容"""
        import re
        try:
            # 按照文本在图片中的位置排序（从上到下）
            sorted_texts = sorted(ocr_result, key=lambda x: x[0][0][1])  # 按y坐标排序
            all_texts = []
            for item in sorted_texts:
                if len(item) >= 2:
                    if isinstance(item[1], tuple) and len(item[1]) >= 1:
                        text = item[1][0]
                    elif isinstance(item[1], str):
                        text = item[1]
                    else:
                        continue
                    all_texts.append(text)
            logger.info(f"[wechatmp] 所有识别出的文本: {all_texts}")
            text_items = []
            for item in sorted_texts:
                if len(item) >= 2:
                    if isinstance(item[1], tuple) and len(item[1]) >= 1:
                        text = item[1][0]
                        confidence = item[1][1] if len(item[1]) > 1 else 0.5
                    elif isinstance(item[1], str):
                        text = item[1]
                        confidence = 0.5
                    else:
                        continue
                else:
                    continue
                if confidence < 0.6:
                    continue
                if not text or len(text.strip()) == 0:
                    continue
                # 新增：过滤无效内容
                content = re.sub(r"^(我|对方)[:：]?", "", text).strip()
                if len(content) <= 1:
                    continue
                if any(x in content for x in ["空格", "发送"]):
                    continue
                if re.fullmatch(r"[\d\W_]+", content):
                    continue
                # 获取文本的位置信息
                if len(item[0]) > 0:
                    top_y = item[0][0][1] if len(item[0][0]) > 1 else 0
                    left_x = item[0][0][0] if len(item[0][0]) > 0 else 0
                else:
                    top_y = 0
                    left_x = 0
                text_items.append((text, left_x, top_y))
            # 只过滤明确的状态栏信息，不过滤整个顶部区域
            filtered_items = []
            for item in text_items:
                text, left_x, top_y = item
                status_bar_patterns = [
                    r'^\d+%$', r'^\d+:\d+$', r'^[0-9]+G$', r'^WIFI$|^WiFi$', r'^[0-9]+:[0-9]+\s*(AM|PM)$',
                ]
                is_status_bar = False
                for pattern in status_bar_patterns:
                    if re.match(pattern, text):
                        logger.info(f"[wechatmp] 过滤掉状态栏信息: {text}")
                        is_status_bar = True
                        break
                if is_status_bar:
                    continue
                filtered_items.append(item)
            text_items = filtered_items
            chat_lines = []
            if text_items:
                all_x = [item[1] for item in text_items]
                mid_x = sum(all_x) / len(all_x)
            else:
                mid_x = 0
            time_patterns = [
                r'^\d{1,2}:\d{2}$', r'^\d{4}/\d{1,2}/\d{1,2}$', r'^\d{4}-\d{1,2}-\d{1,2}$',
            ]
            for item in text_items:
                text, left_x, _ = item
                is_time = False
                for pattern in time_patterns:
                    if re.match(pattern, text):
                        is_time = True
                        break
                if is_time:
                    continue
                name_match = re.match(r'^([^:：]+)[:：]\s*(.*)', text)
                if name_match:
                    name = name_match.group(1).strip()
                    content = name_match.group(2).strip()
                    if not content:
                        content = text
                    text = content
                if len(text) < 1:
                    continue
                is_self = left_x > mid_x
                if is_self:
                    formatted_line = f"我: {text}"
                else:
                    formatted_line = f"对方: {text}"
                chat_lines.append(formatted_line)
            chat_history = "\n".join(chat_lines)
            chat_history = chat_history.replace("  ", " ").strip()
            logger.info(f"[wechatmp] 最终整理的聊天记录: {chat_history}")
            return chat_history
        except Exception as e:
            logger.error(f"[wechatmp] 整理聊天记录异常: {str(e)}")
            import traceback
            logger.error(f"[wechatmp] 整理聊天记录异常堆栈: {traceback.format_exc()}")
            return ""

    def _simple_process_image(self, media_id, from_user_id, to_user_id):
        """简化版图片处理函数，用于测试基本功能"""
        try:
            logger.info(f"[wechatmp] 开始简化处理图片，media_id={media_id}")

            # 下载图片
            image_path = TmpDir().path() + media_id + ".png"

            try:
                response = self.client.media.download(media_id)

                if response.status_code == 200:
                    with open(image_path, "wb") as f:
                        f.write(response.content)
                    logger.info(f"[wechatmp] 图片已保存到: {image_path}")
                else:
                    logger.error(f"[wechatmp] 下载图片失败，状态码: {response.status_code}")
                    return
            except Exception as e:
                logger.error(f"[wechatmp] 下载图片异常: {str(e)}")
                return

            # 构建简单的回复
            prompt = "我已收到您的图片，但由于OCR服务可能存在问题，无法进行文字识别。这是一个简化的回复，用于测试基本功能是否正常。"

            # 创建一个自定义消息
            class CustomMsg:
                def __init__(self):
                    self.id = f"simple_{int(time.time())}"
                    self.time = int(time.time())
                    self.type = "text"
                    self.content = prompt
                    self.source = from_user_id
                    self.target = to_user_id

            # 创建消息对象
            custom_msg = CustomMsg()

            # 使用与WeChatMPMessage相同的接口创建消息对象
            wechatmp_msg = WeChatMPMessage(custom_msg, client=self.client)

            # 创建上下文
            context = self._compose_context(
                wechatmp_msg.ctype,
                wechatmp_msg.content,
                isgroup=False,
                msg=wechatmp_msg,
            )

            # 设置会话ID
            if context:
                context['session_id'] = f"user_{from_user_id}"
                context['receiver'] = from_user_id
                
                # 为简化处理的消息也插入对话记录并获取dialog_id
                try:
                    user = user_dao.get_user_by_openid(from_user_id)
                    if user:
                        # 插入对话记录并获取dialog_id
                        dialog = dialog_dao.insert_dialog(user.id, "image", prompt)
                        context['dialog_id'] = dialog.id
                        logger.debug(f"[wechatmp] 简化处理插入对话记录，dialog_id: {dialog.id}")
                except Exception as e:
                    logger.error(f"[wechatmp] 简化处理插入对话记录失败: {str(e)}")

                # 将消息传递给AI处理
                logger.info(f"[wechatmp] 将简化消息传递给AI处理")
                self.produce(context)
            else:
                logger.error("[wechatmp] 无法创建有效的上下文")

        except Exception as e:
            import traceback
            logger.error(f"[wechatmp] 简化处理异常: {str(e)}")
            logger.error(f"[wechatmp] 异常堆栈: {traceback.format_exc()}")

    def _send_text_message(self, user_id, text):
        """直接发送文本消息给用户"""
        try:
            logger.info(f"[wechatmp] 发送文本消息给用户 {user_id}: {text[:30]}...")

            # 使用微信公众号的客服消息接口发送消息
            self.client.message.send_text(user_id, text)
            logger.info(f"[wechatmp] 文本消息发送成功")
        except Exception as e:
            logger.error(f"[wechatmp] 发送文本消息失败: {str(e)}")
            import traceback
            logger.error(f"[wechatmp] 发送文本消息异常堆栈: {traceback.format_exc()}")

    def _send_error_message(self, user_id, error_text):
        """发送错误消息给用户"""
        try:
            logger.info(f"[wechatmp] 发送错误消息给用户 {user_id}: {error_text}")

            # 使用微信公众号的客服消息接口发送消息
            self.client.message.send_text(user_id, f"错误: {error_text}")
            logger.info(f"[wechatmp] 错误消息发送成功")
        except Exception as e:
            logger.error(f"[wechatmp] 发送错误消息失败: {str(e)}")
            import traceback
            logger.error(f"[wechatmp] 发送错误消息异常堆栈: {traceback.format_exc()}")

    def check_privacy_agreed(self, user_id):
        """检查用户是否同意隐私政策（通过API查询）"""
        try:
            api_url = "http://0.0.0.0:9900/api/privacy/check"  # 独立API地址
            response = requests.get(f"{api_url}?user_id={user_id}", timeout=3)

            if response.status_code == 200:
                result = response.json()
                if result['code'] == 200:
                    has_consented = result['data']['has_consented']
                    logger.info(f"[wechatmp] 查询用户 {user_id} 隐私协议同意状态: {has_consented}")
                    return has_consented

            logger.error(f"[wechatmp] API查询失败，状态码: {response.status_code}")
            # 如果API不可用，默认用户未同意，确保隐私安全
            return False
        except Exception as e:
            logger.error(f"[wechatmp] 查询用户隐私协议状态失败: {str(e)}")
            # 发生异常时，默认用户未同意
            return False

    def set_privacy_agreed(self, user_id):
        """设置用户已同意隐私政策（通过API更新）"""
        try:
            api_url = "http://0.0.0.0:9900/api/privacy/update"  # 独立API地址

            # 获取用户IP和设备ID（如果有）
            ip_address = web.ctx.env.get('REMOTE_ADDR') if hasattr(web, 'ctx') else None
            device_id = None  # 微信公众号场景下可能无法获取设备ID

            data = {
                "user_id": user_id,
                "has_consented": True,
                "device_id": device_id,
                "ip_address": ip_address
            }

            response = requests.post(api_url, json=data, timeout=3)

            if response.status_code == 200:
                result = response.json()
                if result['code'] == 200:
                    logger.info(f"[wechatmp] 更新用户 {user_id} 隐私协议同意状态成功")
                    return True

            logger.error(f"[wechatmp] API更新失败，状态码: {response.status_code}")
            return False
        except Exception as e:
            logger.error(f"[wechatmp] 更新用户隐私协议状态失败: {str(e)}")
            return False

    def get_privacy_notice(self, user_id):
        """获取隐私政策提醒消息"""
        messages = [
            "本神不可随意窥探人心😞 你先签了这份契约...!!!",
            "⬇️点下方链接同意使用协议⬇️",
            "https://undermoon.net/AI_bot/privacy"
        ]
        return messages

    def is_agree_privacy(self, content):
        """判断用户消息是否为同意隐私政策"""
        # 检查是否包含同意隐私政策的关键词
        agree_keywords = ["同意", "agree", "我同意", "ok", "好的", "接受", "accept", "是", "yes", "确认", "嗯嗯", "嗯", "好", "行", "可以"]

        # 将用户输入转为小写，并去除空格
        content = content.lower().strip()

        # 优先检查点击链接的标志
        if "点下方链接同意使用协议" in content or "同意使用协议" in content:
            return True

        # 检查是否为单独的同意关键词
        for keyword in agree_keywords:
            if content == keyword.lower():
                return True

        return False

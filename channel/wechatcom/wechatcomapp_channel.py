# -*- coding=utf-8 -*-
import io
import json
import os
import time
import re
import threading
from PIL import Image
from paddleocr import PaddleOCR

import requests
import web
from wechatpy.enterprise import create_reply, parse_message
from wechatpy.enterprise.crypto import WeChatCrypto
from wechatpy.enterprise.exceptions import InvalidCorpIdException
from wechatpy.exceptions import InvalidSignatureException, WeChatClientException

from bridge.context import Context
from bridge.reply import Reply, ReplyType
from cache import cache
from channel.chat_channel import ChatChannel
from channel.wechatcom.wechatcomapp_client import WechatComAppClient
from channel.wechatcom.wechatcomapp_message import WechatComAppMessage
from common.log import logger
from common.singleton import singleton
from common.utils import compress_imgfile, fsize, split_string_by_utf8_length, convert_webp_to_png, remove_markdown_symbol
from config import conf, subscribe_msg
from voice.audio_convert import any_to_amr, split_audio
from xml.etree import ElementTree
from common.tmp_dir import TmpDir  # 添加 TmpDir 导入

MAX_UTF8_LEN = 2048

# 修改OCR初始化，使用更轻量级的配置
ocr = PaddleOCR(use_angle_cls=False, lang='ch', use_gpu=False, enable_mkldnn=False, 
                cpu_threads=2, det_model_dir=None, rec_model_dir=None, 
                det_limit_side_len=960, det_db_thresh=0.3, det_db_box_thresh=0.5)

@singleton
class WechatComAppChannel(ChatChannel):
    NOT_SUPPORT_REPLYTYPE = []

    def __init__(self):
        super().__init__()
        self.corp_id = conf().get("wechatcom_corp_id")
        self.secret = conf().get("wechatcomapp_secret")
        self.agent_id = conf().get("wechatcomapp_agent_id")
        self.token = conf().get("wechatcomapp_token")
        self.aes_key = conf().get("wechatcomapp_aes_key")
        print(self.corp_id, self.secret, self.agent_id, self.token, self.aes_key)
        logger.info("[wechatcom] init: corp_id: {}, secret: {}, agent_id: {}, token: {}, aes_key: {}".format(self.corp_id, self.secret, self.agent_id, self.token, self.aes_key))
        self.crypto = WeChatCrypto(self.token, self.aes_key, self.corp_id)
        self.client = WechatComAppClient(self.corp_id, self.secret)

    def startup(self):
        # start message listener
        urls = ("/wxcomapp/?", "channel.wechatcom.wechatcomapp_channel.Query")
        app = web.application(urls, globals(), autoreload=False)
        port = conf().get("wechatcomapp_port", 9898)
        web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", port))

    def send(self, reply: Reply, context: Context):
        receiver = context["receiver"]
        channel_type = context.get('reply_callback', {}).get('channel_type')
        if channel_type == 'wechatcomkf':
            # 使用客服消息发送方法
            user_id = context['reply_callback']['user_id']
            open_kf_id = context['reply_callback']['open_kf_id']
            if reply.type in [ReplyType.TEXT, ReplyType.ERROR, ReplyType.INFO]:
                self.send_kf_message(open_kf_id, user_id, "text", reply.content)
            return
        if reply.type in [ReplyType.TEXT, ReplyType.ERROR, ReplyType.INFO]:
            reply_text = remove_markdown_symbol(reply.content)
            texts = split_string_by_utf8_length(reply_text, MAX_UTF8_LEN)
            if len(texts) > 1:
                logger.info("[wechatcom] text too long, split into {} parts".format(len(texts)))
            for i, text in enumerate(texts):
                self.client.message.send_text(self.agent_id, receiver, text)
                if i != len(texts) - 1:
                    time.sleep(0.5)  # 休眠0.5秒，防止发送过快乱序
            logger.info("[wechatcom] Do send text to {}: {}".format(receiver, reply_text))
        elif reply.type == ReplyType.VOICE:
            try:
                media_ids = []
                file_path = reply.content
                amr_file = os.path.splitext(file_path)[0] + ".amr"
                any_to_amr(file_path, amr_file)
                duration, files = split_audio(amr_file, 60 * 1000)
                if len(files) > 1:
                    logger.info("[wechatcom] voice too long {}s > 60s , split into {} parts".format(duration / 1000.0, len(files)))
                for path in files:
                    response = self.client.media.upload("voice", open(path, "rb"))
                    logger.debug("[wechatcom] upload voice response: {}".format(response))
                    media_ids.append(response["media_id"])
            except WeChatClientException as e:
                logger.error("[wechatcom] upload voice failed: {}".format(e))
                return
            try:
                os.remove(file_path)
                if amr_file != file_path:
                    os.remove(amr_file)
            except Exception:
                pass
            for media_id in media_ids:
                self.client.message.send_voice(self.agent_id, receiver, media_id)
                time.sleep(1)
            logger.info("[wechatcom] sendVoice={}, receiver={}".format(reply.content, receiver))
        elif reply.type == ReplyType.IMAGE_URL:  # 从网络下载图片
            img_url = reply.content
            pic_res = requests.get(img_url, stream=True)
            image_storage = io.BytesIO()
            for block in pic_res.iter_content(1024):
                image_storage.write(block)
            sz = fsize(image_storage)
            if sz >= 10 * 1024 * 1024:
                logger.info("[wechatcom] image too large, ready to compress, sz={}".format(sz))
                image_storage = compress_imgfile(image_storage, 10 * 1024 * 1024 - 1)
                logger.info("[wechatcom] image compressed, sz={}".format(fsize(image_storage)))
            image_storage.seek(0)
            if ".webp" in img_url:
                try:
                    image_storage = convert_webp_to_png(image_storage)
                except Exception as e:
                    logger.error(f"Failed to convert image: {e}")
                    return
            try:
                response = self.client.media.upload("image", image_storage)
                logger.debug("[wechatcom] upload image response: {}".format(response))
            except WeChatClientException as e:
                logger.error("[wechatcom] upload image failed: {}".format(e))
                return

            self.client.message.send_image(self.agent_id, receiver, response["media_id"])
            logger.info("[wechatcom] sendImage url={}, receiver={}".format(img_url, receiver))
        elif reply.type == ReplyType.IMAGE:  # 从文件读取图片
            image_storage = reply.content
            sz = fsize(image_storage)
            if sz >= 10 * 1024 * 1024:
                logger.info("[wechatcom] image too large, ready to compress, sz={}".format(sz))
                image_storage = compress_imgfile(image_storage, 10 * 1024 * 1024 - 1)
                logger.info("[wechatcom] image compressed, sz={}".format(fsize(image_storage)))
            image_storage.seek(0)
            try:
                response = self.client.media.upload("image", image_storage)
                logger.debug("[wechatcom] upload image response: {}".format(response))
            except WeChatClientException as e:
                logger.error("[wechatcom] upload image failed: {}".format(e))
                return
            self.client.message.send_image(self.agent_id, receiver, response["media_id"])
            logger.info("[wechatcom] sendImage, receiver={}".format(receiver))

    def sync_kf_message(self, open_kfid, token):
        access_token = self.client.access_token  # 获取有效的 access_token
        url = f"https://qyapi.weixin.qq.com/cgi-bin/kf/sync_msg?access_token={access_token}"
        payload = {
            "open_kfid": open_kfid,
            "token": token
        }
        cursor = cache.get("wx_cursor")
        if cursor is None:
            payload['cursor'] = cursor

        try:
            response = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload))
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"[wechatcom] sync_kf_message error: {e}")
            return None

    def send_kf_message(self, open_kfid, external_userid, msg_type, content):
        access_token = self.client.access_token
        url = f"https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg?access_token={access_token}"
        payload = {
            "touser": external_userid,
            "open_kfid": open_kfid,
            "msgtype": msg_type
        }
        if msg_type == "text":
            payload["text"] = {"content": content}
        # 可以根据需要添加其他消息类型

        try:
            response = requests.post(url, json=payload)
            result = response.json()
            if result.get("errcode") != 0:
                logger.error(f"[wechatcom] send_kf_message error: {result}")
            return result
        except Exception as e:
            logger.error(f"[wechatcom] send_kf_message exception: {e}")
            return None

    def _process_image_with_ocr(self, media_id, from_user_id, to_user_id, agent_id, open_kf_id=None, external_userid=None):
        """异步处理图片OCR并解析聊天记录"""
        try:
            logger.info(f"[wechatcom] 开始处理图片OCR，media_id={media_id[:10]}...")
            logger.info(f"[wechatcom] 客服相关信息: open_kf_id={open_kf_id}, external_userid={external_userid}")
            
            # 确保有有效的发送者ID
            if not from_user_id or from_user_id == "None":
                logger.error("[wechatcom] 原始消息没有有效的发送者ID，无法处理")
                return
            
            # 下载图片 - 参考 WechatComAppMessage 中的下载方式
            image_path = TmpDir().path() + media_id + ".png"
            
            # 使用与 WechatComAppMessage 相同的下载方式
            try:
                response = self.client.media.download(media_id)
                
                # 检查响应并获取二进制数据
                if hasattr(response, 'status_code'):
                    if response.status_code == 200:
                        # 如果是 Response 对象，保存到文件
                        with open(image_path, "wb") as f:
                            f.write(response.content)
                        logger.info(f"[wechatcom] 图片已保存")
                    else:
                        logger.error(f"[wechatcom] 下载图片失败，状态码: {response.status_code}")
                        return
                else:
                    # 如果不是标准响应，尝试直接作为二进制数据处理
                    if hasattr(response, 'content'):
                        image_data = response.content
                    else:
                        image_data = response
                        
                    if not image_data:
                        logger.error("[wechatcom] 无法获取图片数据")
                        return
                        
                    # 将二进制数据保存到文件
                    with open(image_path, "wb") as f:
                        f.write(image_data)
                    logger.info(f"[wechatcom] 图片数据已保存")
            except Exception as e:
                logger.error(f"[wechatcom] 下载图片异常: {str(e)}")
                return
            
            # 检查文件是否存在和大小
            if not os.path.exists(image_path) or os.path.getsize(image_path) == 0:
                logger.error(f"[wechatcom] 图片文件不存在或为空")
                return
            
            # 压缩图片以减少内存使用
            try:
                # 读取原始图片
                with Image.open(image_path) as img:
                    # 获取原始尺寸
                    width, height = img.size
                    
                    # 计算压缩比例，目标宽度为800像素
                    ratio = 800 / width
                    new_width = 800
                    new_height = int(height * ratio)
                    
                    # 调整图片大小
                    resized_img = img.resize((new_width, new_height), Image.LANCZOS)
                    
                    # 保存压缩后的图片
                    compressed_path = image_path + ".compressed.jpg"
                    resized_img.save(compressed_path, "JPEG", quality=85)
                    
                    # 使用压缩后的图片路径
                    image_path = compressed_path
            except Exception as e:
                logger.error(f"[wechatcom] 压缩图片异常: {str(e)}")
                # 继续使用原始图片
            
            # 调用OCR服务识别图片中的文字
            try:
                logger.info("[wechatcom] 开始OCR识别")
                # 使用更低内存的方式调用OCR
                result = ocr.ocr(image_path, cls=False)
                logger.info(f"[wechatcom] OCR识别完成")
            except Exception as e:
                logger.error(f"[wechatcom] OCR识别异常: {str(e)}")
                return
            
            if not result or len(result) == 0 or not result[0]:
                logger.error("[wechatcom] OCR结果为空")
                return
            
            # 提取识别出的文本并整理聊天记录
            try:
                chat_history = self._organize_chat_history(result[0])
                logger.info(f"[wechatcom] 整理后的聊天记录: {chat_history[:100]}...")
            except Exception as e:
                logger.error(f"[wechatcom] 整理聊天记录异常: {str(e)}")
                return
            
            if not chat_history:
                logger.error("[wechatcom] 未能识别出有效的聊天记录")
                return
            
            # 构建提示信息，告诉AI这是聊天记录
            prompt = f"以下是一段微信聊天记录截图中提取的文本，请帮我分析并解读对话内容，理清对话的逻辑和情感：\n\n{chat_history}"
            
            # 清理临时文件
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except Exception as e:
                logger.error(f"[wechatcom] 删除临时文件异常: {str(e)}")
            
            # 确保有 agent_id
            if not agent_id:
                agent_id = self.agent_id
                if not agent_id:
                    agent_id = conf().get("wechatcomapp_agent_id")
            
            # 创建一个自定义消息封装类，适配企业微信消息格式
            class CustomMsg:
                def __init__(self):
                    self.id = f"ocr_{int(time.time())}"
                    self.time = int(time.time())
                    self.type = "text"
                    self.content = prompt
                    self.source = external_userid if external_userid else from_user_id
                    self.target = None
                    self.agent_id = agent_id
                    # 添加客服消息特有的属性
                    self.open_kfid = open_kf_id
                    self.external_userid = external_userid

            # 创建消息对象
            custom_msg = CustomMsg()
            
            # 使用与WechatComAppMessage相同的接口创建消息对象
            wechatcom_msg = WechatComAppMessage(custom_msg, client=self.client)
            
            # 创建上下文
            context = self._compose_context(
                wechatcom_msg.ctype,
                wechatcom_msg.content,
                isgroup=False,
                msg=wechatcom_msg,
            )
            
            # 为客服消息设置唯一的session_id和回调信息
            if context:
                if open_kf_id and external_userid:
                    # 创建唯一的会话ID，确保同一用户的对话在同一会话中
                    unique_session_id = f"kf_{open_kf_id}_{external_userid}"
                    context['session_id'] = unique_session_id
                    
                    # 添加客服特有的回调信息到上下文
                    context['reply_callback'] = {
                        'channel_type': 'wechatcomkf',
                        'user_id': external_userid,
                        'open_kf_id': open_kf_id
                    }
                else:
                    # 如果不是客服消息，使用普通的会话ID
                    context['session_id'] = f"user_{from_user_id}"
                    context['receiver'] = from_user_id
                
                # 将消息传递给AI处理
                logger.info(f"[wechatcom] 将OCR识别的聊天记录传递给AI处理")
                self.produce(context)
            else:
                logger.error("[wechatcom] 无法创建有效的上下文")
            
        except Exception as e:
            import traceback
            logger.error(f"OCR处理异常: {str(e)}")
            logger.error(f"异常堆栈: {traceback.format_exc()}")

    def _organize_chat_history(self, ocr_result):
        """整理OCR识别出的聊天记录"""
        try:
            # 按照文本在图片中的位置排序（从上到下）
            sorted_texts = sorted(ocr_result, key=lambda x: x[0][0][1])  # 按y坐标排序
            
            # 提取文本内容和位置信息
            text_items = []
            for item in sorted_texts:
                # 检查OCR结果格式
                if len(item) >= 2:
                    if isinstance(item[1], tuple) and len(item[1]) >= 1:
                        text = item[1][0]  # 获取识别出的文本
                        confidence = item[1][1] if len(item[1]) > 1 else 0.5  # 获取置信度
                    elif isinstance(item[1], str):
                        text = item[1]
                        confidence = 0.5  # 默认置信度
                    else:
                        continue
                else:
                    continue
                
                # 过滤掉置信度过低的结果和太短的文本
                if confidence < 0.5 or len(text.strip()) < 2:
                    continue
                
                # 获取文本的位置信息（左上角x坐标）
                left_x = item[0][0][0]
                top_y = item[0][0][1]
                
                # 添加到列表
                text_items.append((text.strip(), left_x, top_y))
            
            # 计算中点，用于区分左右两侧的消息
            if text_items:
                all_x = [item[1] for item in text_items]
                mid_x = sum(all_x) / len(all_x)
            else:
                mid_x = 400  # 默认中点
            
            # 按照y坐标排序，确保消息从上到下
            text_items.sort(key=lambda x: x[2])
            
            # 整理聊天记录，区分左右两侧
            chat_lines = []
            
            for text, left_x, _ in text_items:
                # 跳过时间戳格式的文本
                time_pattern = re.compile(r'^\d{1,2}:\d{2}$')
                if time_pattern.match(text):
                    continue
                
                # 根据位置确定是对方还是自己的消息
                is_self = left_x > mid_x
                
                # 格式化聊天行
                if is_self:
                    formatted_line = f"我: {text}"
                else:
                    formatted_line = f"对方: {text}"
                
                chat_lines.append(formatted_line)
            
            # 合并文本行
            chat_history = "\n".join(chat_lines)
            
            # 简单清理
            chat_history = chat_history.replace("  ", " ").strip()
            
            return chat_history
        except Exception as e:
            logger.error(f"[wechatcom] 整理聊天记录异常: {str(e)}")
            return ""

    def _process_text_message(self, msg):
        """处理文本消息的方法"""
        try:
            logger.info(f"[wechatcom] 处理文本消息: {msg.content[:100]}...")
            
            # 获取必要的信息
            content = msg.content
            from_user_id = msg.source
            agent_id = getattr(msg, 'agent_id', conf().get("wechatcomapp_agent_id"))
            
            # 直接发送消息
            self.client.message.send_text(agent_id, from_user_id, content)
            logger.info(f"[wechatcom] 成功发送文本消息给 {from_user_id}")
            
        except Exception as e:
            logger.error(f"[wechatcom] 处理文本消息异常: {str(e)}")

class Query:
    def GET(self):
        channel = WechatComAppChannel()
        params = web.input()
        logger.info("[wechatcom] receive params: {}".format(params))
        try:
            signature = params.msg_signature
            timestamp = params.timestamp
            nonce = params.nonce
            echostr = params.echostr
            echostr = channel.crypto.check_signature(signature, timestamp, nonce, echostr)
        except InvalidSignatureException:
            raise web.Forbidden()
        return echostr

    def POST(self):
        # 1. 接收企微回调请求参数
        channel = WechatComAppChannel()
        params = web.input()

        # 2. 验证签名并解密消息
        try:
            signature = params.msg_signature
            timestamp = params.timestamp
            nonce = params.nonce
            message = channel.crypto.decrypt_message(web.data(), signature, timestamp, nonce)
        except (InvalidSignatureException, InvalidCorpIdException):
            raise web.Forbidden()

        # 3. 手动解析 XML 字符串
        root = ElementTree.fromstring(message)
        kf_id = root.findtext("OpenKfId")
        token = root.findtext("Token")

        # 4. 请求企微拉取消息
        response = channel.sync_kf_message(kf_id, token)
        if not response or "msg_list" not in response:
            return "success"

        # 5. 更新游标（如果有新的）
        new_cursor = response.get("next_cursor")
        if new_cursor:
            cache.set("cursor", new_cursor)

        last_msg = response.get("msg_list")[-1]
        if last_msg["msgtype"] == "text":
            try:
                # 创建自定义消息封装类，适配企业微信客服消息格式
                class KfMsg:
                    def __init__(self, msg_data):
                        self.id = msg_data.get("msgid")
                        self.time = msg_data.get("send_time")
                        self.type = msg_data.get("msgtype")
                        self.content = msg_data.get("text", {}).get("content", "")
                        self.source = msg_data.get("external_userid")
                        self.target = msg_data.get("open_kfid")
                        # 添加客服消息特有的属性
                        self.open_kfid = msg_data.get("open_kfid")
                        self.external_userid = msg_data.get("external_userid")

                # 将字典转为对象
                kf_msg_obj = KfMsg(last_msg)
                # 使用与WechatComAppMessage相同的接口创建消息对象
                wechatcom_msg = WechatComAppMessage(kf_msg_obj, client=channel.client)
                
                # 创建上下文
                context = channel._compose_context(
                    wechatcom_msg.ctype,
                    wechatcom_msg.content,
                    isgroup=False,
                    msg=wechatcom_msg,
                )
                
                # 关键修改：为客服消息设置唯一的session_id
                # 使用 open_kfid + external_userid 作为唯一标识
                if context:
                    # 创建唯一的会话ID，确保同一用户的对话在同一会话中
                    unique_session_id = f"kf_{kf_msg_obj.open_kfid}_{kf_msg_obj.external_userid}"
                    context['session_id'] = unique_session_id
                    
                    # 添加客服特有的回调信息到上下文
                    context['reply_callback'] = {
                        'channel_type': 'wechatcomkf',
                        'user_id': wechatcom_msg.from_user_id,
                        'open_kf_id': kf_msg_obj.open_kfid
                    }
                    channel.produce(context)
            except Exception as e:
                logger.error(f"处理客服消息异常: {str(e)}")

        # 处理图片消息
        if last_msg["msgtype"] == "image":
            try:
                # 获取发送者信息
                from_user_id = last_msg.get("external_userid") or last_msg.get("from") or last_msg.get("FromUserName")
                to_user_id = last_msg.get("to") or last_msg.get("ToUserName")
                
                # 获取客服消息特有的字段
                open_kf_id = last_msg.get("open_kfid")
                external_userid = last_msg.get("external_userid")
                
                # 记录用户ID信息，便于调试
                logger.info(f"[wechatcom] 图片消息信息: from_user_id={from_user_id}, to_user_id={to_user_id}")
                logger.info(f"[wechatcom] 客服消息信息: open_kf_id={open_kf_id}, external_userid={external_userid}")
                
                # 获取 agent_id
                agent_id = last_msg.get("agentid")
                if not agent_id:
                    agent_id = conf().get("wechatcomapp_agent_id")
                    logger.info(f"[wechatcom] 使用配置的 agent_id: {agent_id}")
                
                # 获取图片媒体ID
                media_id = last_msg.get("image", {}).get("media_id")
                if not media_id:
                    # 尝试其他可能的字段名
                    media_id = last_msg.get("MediaId")
                
                if media_id:
                    logger.info(f"[wechatcom] 获取到图片 media_id: {media_id}")
                    
                    # 异步处理图片，避免阻塞主线程
                    threading.Thread(
                        target=channel._process_image_with_ocr,
                        args=(media_id, from_user_id, to_user_id, agent_id, open_kf_id, external_userid)
                    ).start()
                    
                    # 立即返回，避免微信超时
                    return "success"
                else:
                    logger.error("[wechatcom] 未能获取图片 media_id")
            except Exception as e:
                logger.error(f"处理图片消息异常: {str(e)}")
        
        # 立即返回成功，异步处理消息
        return "success"

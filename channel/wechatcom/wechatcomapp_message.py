from wechatpy.enterprise import WeChatClient
import re

from bridge.context import ContextType
from channel.chat_message import ChatMessage
from common.log import logger
from common.tmp_dir import TmpDir


class WechatComAppMessage(ChatMessage):
    def __init__(self, msg, client: WeChatClient, is_group=False):
        super().__init__(msg)
        self.msg_id = msg.id
        self.create_time = msg.time
        self.is_group = is_group

        if msg.type == "text":
            self.ctype = ContextType.TEXT
            self.content = msg.content
            
            # 检查是否是转发消息
            if "<msg>" in msg.content and "</msg>" in msg.content:
                logger.info(f"[wechatcom] 检测到转发消息: {msg.content[:100]}...")
                # 尝试提取转发消息中的文本内容
                try:
                    # 尝试提取 <content>...</content> 中的内容
                    content_match = re.search(r'<content>(.*?)</content>', msg.content, re.DOTALL)
                    if content_match:
                        extracted_text = content_match.group(1)
                        # 去除可能的XML标签
                        extracted_text = re.sub(r'<[^>]+>', '', extracted_text)
                        logger.info(f"[wechatcom] 提取的转发消息内容: {extracted_text}")
                        self.content = extracted_text
                    else:
                        # 如果无法提取，使用一个通用提示
                        logger.warning(f"[wechatcom] 无法提取转发消息内容: {msg.content[:100]}...")
                        # 保持原始内容，让后续处理决定如何处理
                except Exception as e:
                    logger.error(f"[wechatcom] 解析转发消息失败: {e}")
                    # 保持原始内容，让后续处理决定如何处理
        elif msg.type == "voice":
            self.ctype = ContextType.VOICE
            self.content = TmpDir().path() + msg.media_id + "." + msg.format  # content直接存临时目录路径

            def download_voice():
                # 如果响应状态码是200，则将响应内容写入本地文件
                response = client.media.download(msg.media_id)
                if response.status_code == 200:
                    with open(self.content, "wb") as f:
                        f.write(response.content)
                else:
                    logger.info(f"[wechatcom] Failed to download voice file, {response.content}")

            self._prepare_fn = download_voice
        elif msg.type == "image":
            self.ctype = ContextType.IMAGE
            self.content = TmpDir().path() + msg.media_id + ".png"  # content直接存临时目录路径

            def download_image():
                # 如果响应状态码是200，则将响应内容写入本地文件
                response = client.media.download(msg.media_id)
                if response.status_code == 200:
                    with open(self.content, "wb") as f:
                        f.write(response.content)
                else:
                    logger.info(f"[wechatcom] Failed to download image file, {response.content}")

            self._prepare_fn = download_image
        # 添加对其他类型消息的支持
        elif msg.type == "link":
            # 处理链接消息
            self.ctype = ContextType.TEXT
            title = getattr(msg, 'title', '未知标题')
            description = getattr(msg, 'description', '无描述')
            url = getattr(msg, 'url', '#')
            self.content = f"收到链接：\n标题：{title}\n描述：{description}\n链接：{url}"
            logger.info(f"[wechatcom] 收到链接消息: {self.content}")
        elif msg.type == "location":
            # 处理位置消息
            self.ctype = ContextType.TEXT
            label = getattr(msg, 'label', '未知位置')
            x = getattr(msg, 'x', 0)
            y = getattr(msg, 'y', 0)
            self.content = f"收到位置：{label}，坐标：({x}, {y})"
            logger.info(f"[wechatcom] 收到位置消息: {self.content}")
        elif msg.type == "file":
            # 处理文件消息
            self.ctype = ContextType.TEXT
            file_name = getattr(msg, 'file_name', '未知文件')
            self.content = f"收到文件：{file_name}，由于安全原因，我无法直接处理文件内容。"
            logger.info(f"[wechatcom] 收到文件消息: {file_name}")
        else:
            # 默认作为文本处理
            self.ctype = ContextType.TEXT
            self.content = f"收到了一条 {msg.type} 类型的消息，但我暂时无法处理。请尝试发送文本消息。"
            logger.warning(f"[wechatcom] 收到未知类型消息: {msg.type}")

        self.from_user_id = msg.source
        self.to_user_id = msg.target
        self.other_user_id = msg.source

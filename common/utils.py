import io
import os
import re
from urllib.parse import urlparse
from PIL import Image
from common.log import logger
import asyncio

def fsize(file):
    if isinstance(file, io.BytesIO):
        return file.getbuffer().nbytes
    elif isinstance(file, str):
        return os.path.getsize(file)
    elif hasattr(file, "seek") and hasattr(file, "tell"):
        pos = file.tell()
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(pos)
        return size
    else:
        raise TypeError("Unsupported type")


def compress_imgfile(file, max_size):
    if fsize(file) <= max_size:
        return file
    file.seek(0)
    img = Image.open(file)
    rgb_image = img.convert("RGB")
    quality = 95
    while True:
        out_buf = io.BytesIO()
        rgb_image.save(out_buf, "JPEG", quality=quality)
        if fsize(out_buf) <= max_size:
            return out_buf
        quality -= 5


def split_string_by_utf8_length(string, max_length, max_split=0):
    encoded = string.encode("utf-8")
    start, end = 0, 0
    result = []
    while end < len(encoded):
        if max_split > 0 and len(result) >= max_split:
            result.append(encoded[start:].decode("utf-8"))
            break
        end = min(start + max_length, len(encoded))
        # 如果当前字节不是 UTF-8 编码的开始字节，则向前查找直到找到开始字节为止
        while end < len(encoded) and (encoded[end] & 0b11000000) == 0b10000000:
            end -= 1
        result.append(encoded[start:end].decode("utf-8"))
        start = end
    return result


def get_path_suffix(path):
    path = urlparse(path).path
    return os.path.splitext(path)[-1].lstrip('.')


def convert_webp_to_png(webp_image):
    from PIL import Image
    try:
        webp_image.seek(0)
        img = Image.open(webp_image).convert("RGBA")
        png_image = io.BytesIO()
        img.save(png_image, format="PNG")
        png_image.seek(0)
        return png_image
    except Exception as e:
        logger.error(f"Failed to convert WEBP to PNG: {e}")
        raise


def remove_markdown_symbol(text: str):
    # 移除markdown格式，目前先移除**
    if not text:
        return text
    return re.sub(r'\*\*(.*?)\*\*', r'\1', text)


async def send_message_to_open_ai_with_retry(prompt, model=None, api_key=None, base_url=None, temperature=0.7, top_p=0.9, max_tokens=2000, retry_count=3):
    """
    直接发送消息到OpenAI/DeepSeek API并获取响应，支持重试
    
    Args:
        prompt: 要发送的消息内容
        model: 模型名称，如果为None则使用配置文件中的默认模型
        api_key: API密钥，如果为None则使用配置文件中的密钥
        base_url: API基础URL，如果为None则使用配置文件中的URL
        temperature: 温度参数，控制随机性
        top_p: top_p参数，控制多样性
        max_tokens: 最大生成token数
        retry_count: 重试次数
        
    Returns:
        返回API响应的文本内容，如果失败则返回None
    """
    import aiohttp
    import json
    import time
    from common.log import logger
    from config import conf
    
    # 如果未提供参数，使用配置中的默认值
    if not model:
        model = conf().get("model")
    if not api_key:
        api_key = conf().get("open_ai_api_key")
    if not base_url:
        base_url = conf().get("open_ai_api_base")
    
    if not base_url.endswith('/'):
        base_url += '/'
    
    url = f"{base_url}chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens
    }
    
    for attempt in range(retry_count):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data, timeout=60) as response:
                    if response.status == 200:
                        result = await response.json()
                        if "choices" in result and len(result["choices"]) > 0:
                            content = result["choices"][0]["message"]["content"]
                            return content
                        else:
                            logger.error(f"[send_message_to_open_ai_with_retry] Invalid response format: {result}")
                    else:
                        error_text = await response.text()
                        logger.error(f"[send_message_to_open_ai_with_retry] API返回错误，状态码: {response.status}, 错误: {error_text}")
        except Exception as e:
            logger.error(f"[send_message_to_open_ai_with_retry] 第{attempt+1}次调用API异常: {e}")
            import traceback
            logger.error(f"[send_message_to_open_ai_with_retry] 异常堆栈: {traceback.format_exc()}")
        
        # 如果不是最后一次尝试，等待一段时间再重试
        if attempt < retry_count - 1:
            wait_time = 2 ** attempt  # 指数退避策略
            logger.info(f"[send_message_to_open_ai_with_retry] 等待{wait_time}秒后重试...")
            await asyncio.sleep(wait_time)
    
    logger.error(f"[send_message_to_open_ai_with_retry] 达到最大重试次数({retry_count})，调用失败")
    return None


async def send_reply(reply, msg):
    """
    发送回复消息到指定渠道
    """
    from bridge.context import Context
    from channel.chat_message import ChatMessage
    from common.log import logger
    
    if isinstance(msg, ChatMessage):
        channel_name = msg.ctype
        user_id = msg.from_user_id
        context = Context(msg)
        
        try:
            from common.singleton import singleton
            from channel.channel_factory import create_channel
            channel = create_channel(channel_name)
            if channel:
                await channel.send(reply, context)
                logger.info(f"[send_reply] 成功发送消息到用户 {user_id}")
            else:
                logger.error(f"[send_reply] 无法创建渠道 {channel_name}")
        except Exception as e:
            logger.error(f"[send_reply] 发送消息异常: {e}")
            import traceback
            logger.error(f"[send_reply] 异常堆栈: {traceback.format_exc()}")
    else:
        logger.error(f"[send_reply] 不支持的消息类型: {type(msg)}")

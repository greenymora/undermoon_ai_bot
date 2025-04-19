# encoding:utf-8

import time

import openai
import openai.error
import requests
from common import const
from bot.bot import Bot
from bot.chatgpt.chat_gpt_session import ChatGPTSession
from bot.openai.open_ai_image import OpenAIImage
from bot.session_manager import SessionManager
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from common.token_bucket import TokenBucket
from config import conf, load_config
from bot.baidu.baidu_wenxin_session import BaiduWenxinSession

# OpenAI对话模型API (可用)
class ChatGPTBot(Bot, OpenAIImage):
    def __init__(self):
        super().__init__()
        # set the default api_key
        openai.api_key = conf().get("open_ai_api_key")
        if conf().get("open_ai_api_base"):
            openai.api_base = conf().get("open_ai_api_base")
        proxy = conf().get("proxy")
        if proxy:
            openai.proxy = proxy
        if conf().get("rate_limit_chatgpt"):
            self.tb4chatgpt = TokenBucket(conf().get("rate_limit_chatgpt", 20))
        # 加载配置
        model = conf().get("model") or "gpt-3.5-turbo"
        self.sessions = SessionManager(ChatGPTSession, model=model)
        
        # 设置默认参数
        self.args = {
            "model": model,
            "temperature": conf().get("temperature", 0.7),
            "max_tokens": conf().get("conversation_max_tokens", 1500),  # 使用 conversation_max_tokens
            "top_p": conf().get("top_p", 1.0),
            "frequency_penalty": conf().get("frequency_penalty", 0.0),
            "presence_penalty": conf().get("presence_penalty", 0.0)
        }
        
        # 记录初始化参数
        logger.info(f"[CHATGPT] Initialized with args: {self.args}")
        
        # 初始化图像生成功能
        self.image_create_prefix = conf().get("image_create_prefix", ["画", "draw", "Paint"])
        self.image_create_size = conf().get("image_create_size", "256x256")
        
        # 检查配置文件中是否有 image_create_n 参数
        try:
            self.image_create_n = conf().get("image_create_n", 1)
        except Exception as e:
            logger.warning(f"[CHATGPT] image_create_n not in config, using default value 1: {e}")
            self.image_create_n = 1
        # o1相关模型不支持system prompt，暂时用文心模型的session

        self.args = {
            "model": model,  # 对话模型的名称
            "temperature": conf().get("temperature", 0.9),  # 值在[0,1]之间，越大表示回复越具有不确定性
            # "max_tokens":4096,  # 回复最大的字符数
            "top_p": conf().get("top_p", 1),
            "frequency_penalty": conf().get("frequency_penalty", 0.0),  # [-2,2]之间，该值越大则更倾向于产生不同的内容
            "presence_penalty": conf().get("presence_penalty", 0.0),  # [-2,2]之间，该值越大则更倾向于产生不同的内容
            "request_timeout": conf().get("request_timeout", None),  # 请求超时时间，openai接口默认设置为600，对于难问题一般需要较长时间
            "timeout": conf().get("request_timeout", None),  # 重试超时时间，在这个时间内，将会自动重试
        }
        # o1相关模型固定了部分参数，暂时去掉
        if model in [const.O1, const.O1_MINI]:
            self.sessions = SessionManager(BaiduWenxinSession, model=conf().get("model") or const.O1_MINI)
            remove_keys = ["temperature", "top_p", "frequency_penalty", "presence_penalty"]
            for key in remove_keys:
                self.args.pop(key, None)  # 如果键不存在，使用 None 来避免抛出错误

    def reply(self, query, context=None):
        # acquire reply content
        if context.type == ContextType.TEXT:
            logger.info("[CHATGPT] query={}".format(query))

            session_id = context["session_id"]
            reply = None
            clear_memory_commands = conf().get("clear_memory_commands", ["#清除记忆"])
            if query in clear_memory_commands:
                self.sessions.clear_session(session_id)
                reply = Reply(ReplyType.INFO, "记忆已清除")
            elif query == "#清除所有":
                self.sessions.clear_all_session()
                reply = Reply(ReplyType.INFO, "所有人记忆已清除")
            elif query == "#更新配置":
                load_config()
                reply = Reply(ReplyType.INFO, "配置已更新")
            if reply:
                return reply
            session = self.sessions.session_query(query, session_id)
            logger.debug("[CHATGPT] session query={}".format(session.messages))

            api_key = context.get("openai_api_key")
            model = context.get("gpt_model")
            new_args = None
            if model:
                new_args = self.args.copy()
                new_args["model"] = model
            # if context.get('stream'):
            #     # reply in stream
            #     return self.reply_text_stream(query, new_query, session_id)

            reply_content = self.reply_text(session, api_key, args=new_args)
            logger.debug(
                "[CHATGPT] new_query={}, session_id={}, reply_cont={}, completion_tokens={}".format(
                    session.messages,
                    session_id,
                    reply_content["content"],
                    reply_content["completion_tokens"],
                )
            )
            if reply_content["completion_tokens"] == 0 and len(reply_content["content"]) > 0:
                reply = Reply(ReplyType.ERROR, reply_content["content"])
            elif reply_content["completion_tokens"] > 0:
                self.sessions.session_reply(reply_content["content"], session_id, reply_content["total_tokens"])
                reply = Reply(ReplyType.TEXT, reply_content["content"])
            else:
                reply = Reply(ReplyType.ERROR, reply_content["content"])
                logger.debug("[CHATGPT] reply {} used 0 tokens.".format(reply_content))
            return reply

        elif context.type == ContextType.IMAGE_CREATE:
            ok, retstring = self.create_img(query, 0)
            reply = None
            if ok:
                reply = Reply(ReplyType.IMAGE_URL, retstring)
            else:
                reply = Reply(ReplyType.ERROR, retstring)
            return reply
        else:
            reply = Reply(ReplyType.ERROR, "Bot不支持处理{}类型的消息".format(context.type))
            return reply

    def reply_text(self, session, api_key=None, args=None):
        # 使用默认参数，如果没有提供
        default_args = {
            "model": conf().get("model") or "gpt-3.5-turbo",
            "temperature": conf().get("temperature", 0.7),
            "max_tokens": conf().get("conversation_max_tokens", 1500),  # 使用 conversation_max_tokens
            "top_p": conf().get("top_p", 1.0),
            "frequency_penalty": conf().get("frequency_penalty", 0.0),
            "presence_penalty": conf().get("presence_penalty", 0.0)
        }
        
        # 合并默认参数和提供的参数
        if args:
            for key, value in args.items():
                default_args[key] = value
        
        args = default_args
        
        # 记录会话消息
        logger.info(f"[CHATGPT] 会话ID: {session.session_id}")
        logger.info(f"[CHATGPT] 会话消息数量: {len(session.messages)}")
        logger.info(f"[CHATGPT] 会话消息: {session.messages}")
        
        if api_key is not None:
            openai.api_key = api_key
        
        # 确保使用正确的API基础URL
        api_base = conf().get("open_ai_api_base")
        if api_base:
            openai.api_base = api_base
            logger.info(f"[CHATGPT] Using API base: {api_base}")
        
        # 记录模型信息
        model = args.get("model")
        logger.info(f"[CHATGPT] Using model: {model}")
        
        try:
            # 确保传递完整的会话历史
            response = openai.ChatCompletion.create(
                model=args["model"],
                messages=session.messages,  # 传递完整的会话历史
                temperature=args["temperature"],
                max_tokens=args["max_tokens"],
                top_p=args["top_p"],
                frequency_penalty=args["frequency_penalty"],
                presence_penalty=args["presence_penalty"],
            )
            # 记录API响应
            logger.debug(f"[CHATGPT] Response: {response}")
            
            # 处理响应
            reply = response.choices[0].message.content
            usage = response.usage
            logger.info(f"[CHATGPT] Reply: {reply[:100]}...")  # 记录回复的前100个字符
            logger.info(f"[CHATGPT] Usage: {usage}")
            
            # 将助手回复添加到会话中
            session.append_message("assistant", reply)
            
            return {
                "content": reply,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
        except Exception as e:
            # 详细记录异常
            logger.error(f"[CHATGPT] Exception: {e}")
            import traceback
            logger.error(f"[CHATGPT] Traceback: {traceback.format_exc()}")
            return {"content": f"API调用出错: {e}", "completion_tokens": 0, "total_tokens": 0}


class AzureChatGPTBot(ChatGPTBot):
    def __init__(self):
        super().__init__()
        openai.api_type = "azure"
        openai.api_version = conf().get("azure_api_version", "2023-06-01-preview")
        self.args["deployment_id"] = conf().get("azure_deployment_id")

    def create_img(self, query, retry_count=0, api_key=None):
        text_to_image_model = conf().get("text_to_image")
        if text_to_image_model == "dall-e-2":
            api_version = "2023-06-01-preview"
            endpoint = conf().get("azure_openai_dalle_api_base","open_ai_api_base")
            # 检查endpoint是否以/结尾
            if not endpoint.endswith("/"):
                endpoint = endpoint + "/"
            url = "{}openai/images/generations:submit?api-version={}".format(endpoint, api_version)
            api_key = conf().get("azure_openai_dalle_api_key","open_ai_api_key")
            headers = {"api-key": api_key, "Content-Type": "application/json"}
            try:
                body = {"prompt": query, "size": conf().get("image_create_size", "256x256"),"n": 1}
                submission = requests.post(url, headers=headers, json=body)
                operation_location = submission.headers['operation-location']
                status = ""
                while (status != "succeeded"):
                    if retry_count > 3:
                        return False, "图片生成失败"
                    response = requests.get(operation_location, headers=headers)
                    status = response.json()['status']
                    retry_count += 1
                image_url = response.json()['result']['data'][0]['url']
                return True, image_url
            except Exception as e:
                logger.error("create image error: {}".format(e))
                return False, "图片生成失败"
        elif text_to_image_model == "dall-e-3":
            api_version = conf().get("azure_api_version", "2024-02-15-preview")
            endpoint = conf().get("azure_openai_dalle_api_base","open_ai_api_base")
            # 检查endpoint是否以/结尾
            if not endpoint.endswith("/"):
                endpoint = endpoint + "/"
            url = "{}openai/deployments/{}/images/generations?api-version={}".format(endpoint, conf().get("azure_openai_dalle_deployment_id","text_to_image"),api_version)
            api_key = conf().get("azure_openai_dalle_api_key","open_ai_api_key")
            headers = {"api-key": api_key, "Content-Type": "application/json"}
            try:
                body = {"prompt": query, "size": conf().get("image_create_size", "1024x1024"), "quality": conf().get("dalle3_image_quality", "standard")}
                response = requests.post(url, headers=headers, json=body)
                response.raise_for_status()  # 检查请求是否成功
                data = response.json()

                # 检查响应中是否包含图像 URL
                if 'data' in data and len(data['data']) > 0 and 'url' in data['data'][0]:
                    image_url = data['data'][0]['url']
                    return True, image_url
                else:
                    error_message = "响应中没有图像 URL"
                    logger.error(error_message)
                    return False, "图片生成失败"

            except requests.exceptions.RequestException as e:
                # 捕获所有请求相关的异常
                try:
                    error_detail = response.json().get('error', {}).get('message', str(e))
                except ValueError:
                    error_detail = str(e)
                error_message = f"{error_detail}"
                logger.error(error_message)
                return False, error_message

            except Exception as e:
                # 捕获所有其他异常
                error_message = f"生成图像时发生错误: {e}"
                logger.error(error_message)
                return False, "图片生成失败"
        else:
            return False, "图片生成失败，未配置text_to_image参数"

from bot.session_manager import Session
from common.log import logger
from common import const

"""
    e.g.  [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Who won the world series in 2020?"},
        {"role": "assistant", "content": "The Los Angeles Dodgers won the World Series in 2020."},
        {"role": "user", "content": "Where was it played?"}
    ]
"""


class ChatGPTSession(Session):
    def __init__(self, session_id, system_prompt=None, model="gpt-3.5-turbo"):
        super().__init__(session_id, system_prompt)
        self.model = model
        self.reset()

    def append_message(self, role, content):
        """
        添加消息到会话历史
        :param role: 角色，可以是 "system", "user", "assistant"
        :param content: 消息内容
        """
        self.messages.append({"role": role, "content": content})
        logger.debug(f"[ChatGPTSession] 添加消息: role={role}, content={content[:30]}...")
        logger.debug(f"[ChatGPTSession] 当前会话消息数量: {len(self.messages)}")

    def get_messages(self):
        """
        获取所有消息
        :return: 消息列表
        """
        logger.debug(f"[ChatGPTSession] 获取消息: {self.messages}")
        return self.messages

    def discard_exceeding(self, max_tokens, llm=None):
        """
        丢弃超过最大令牌数的旧消息
        :param max_tokens: 最大令牌数
        :param llm: 语言模型，用于计算令牌数
        :return: 当前会话的令牌数
        """
        # 保留系统消息
        system_messages = [msg for msg in self.messages if msg["role"] == "system"]
        other_messages = [msg for msg in self.messages if msg["role"] != "system"]
        
        # 如果没有超过最大令牌数，则不需要丢弃
        if len(other_messages) <= 2:  # 至少保留最新的一问一答
            return sum(len(msg["content"]) for msg in self.messages) // 4  # 粗略估计token数
        
        # 从最旧的消息开始丢弃，直到令牌数小于最大令牌数
        while len(other_messages) > 2:
            # 丢弃最旧的一问一答
            if len(other_messages) >= 2:
                other_messages = other_messages[2:]
            else:
                break
            
            # 重建消息列表
            self.messages = system_messages + other_messages
            
            # 粗略估计当前令牌数
            current_tokens = sum(len(msg["content"]) for msg in self.messages) // 4
            
            # 如果当前令牌数小于最大令牌数，则停止丢弃
            if current_tokens < max_tokens:
                break
        
        # 返回粗略估计的令牌数
        return sum(len(msg["content"]) for msg in self.messages) // 4

    def calc_tokens(self):
        return num_tokens_from_messages(self.messages, self.model)


# refer to https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
def num_tokens_from_messages(messages, model):
    """Returns the number of tokens used by a list of messages."""

    if model in ["wenxin", "xunfei"] or model.startswith(const.GEMINI):
        return num_tokens_by_character(messages)

    import tiktoken

    if model in ["gpt-3.5-turbo-0301", "gpt-35-turbo", "gpt-3.5-turbo-1106", "moonshot", const.LINKAI_35]:
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo")
    elif model in ["gpt-4-0314", "gpt-4-0613", "gpt-4-32k", "gpt-4-32k-0613", "gpt-3.5-turbo-0613",
                   "gpt-3.5-turbo-16k", "gpt-3.5-turbo-16k-0613", "gpt-35-turbo-16k", "gpt-4-turbo-preview",
                   "gpt-4-1106-preview", const.GPT4_TURBO_PREVIEW, const.GPT4_VISION_PREVIEW, const.GPT4_TURBO_01_25,
                   const.GPT_4o, const.GPT_4O_0806, const.GPT_4o_MINI, const.LINKAI_4o, const.LINKAI_4_TURBO]:
        return num_tokens_from_messages(messages, model="gpt-4")
    elif model.startswith("claude-3"):
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo")
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        logger.debug("Warning: model not found. Using cl100k_base encoding.")
        encoding = tiktoken.get_encoding("cl100k_base")
    if model == "gpt-3.5-turbo":
        tokens_per_message = 4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        tokens_per_name = -1  # if there's a name, the role is omitted
    elif model == "gpt-4":
        tokens_per_message = 3
        tokens_per_name = 1
    else:
        logger.debug(f"num_tokens_from_messages() is not implemented for model {model}. Returning num tokens assuming gpt-3.5-turbo.")
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo")
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens


def num_tokens_by_character(messages):
    """Returns the number of tokens used by a list of messages."""
    tokens = 0
    for msg in messages:
        tokens += len(msg["content"])
    return tokens

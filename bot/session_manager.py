from common.expired_dict import ExpiredDict
from common.log import logger
from config import conf


class Session(object):
    def __init__(self, session_id, system_prompt=None):
        self.session_id = session_id
        self.messages = []
        if system_prompt is None:
            self.system_prompt = conf().get("character_desc", "")
        else:
            self.system_prompt = system_prompt

    # 重置会话
    def reset(self):
        system_item = {"role": "system", "content": self.system_prompt}
        self.messages = [system_item]

    def set_system_prompt(self, system_prompt):
        self.system_prompt = system_prompt
        self.reset()

    def add_query(self, query):
        user_item = {"role": "user", "content": query}
        self.messages.append(user_item)

    def add_reply(self, reply):
        assistant_item = {"role": "assistant", "content": reply}
        self.messages.append(assistant_item)

    def discard_exceeding(self, max_tokens=None, cur_tokens=None):
        raise NotImplementedError

    def calc_tokens(self):
        raise NotImplementedError


class SessionManager(object):
    def __init__(self, session_class, system_prompt=None, model=None):
        self.sessions = {}
        self.session_class = session_class
        if system_prompt is None and model:
            system_prompt = conf().get("character_desc", "")
            if system_prompt:
                logger.info("[SessionManager] Using character description as system prompt")
            else:
                logger.info("[SessionManager] No system prompt")
        self.system_prompt = system_prompt
        
    def build_session(self, session_id):
        """
        构建会话
        :param session_id: 会话ID
        :return: 会话对象
        """
        if session_id not in self.sessions:
            logger.debug(f"[SessionManager] 创建新会话: {session_id}")
            self.sessions[session_id] = self.session_class(session_id, self.system_prompt)
        return self.sessions[session_id]
        
    def session_query(self, query, session_id):
        """
        添加用户消息并返回完整会话
        :param query: 用户消息
        :param session_id: 会话ID
        :return: 会话对象
        """
        session = self.build_session(session_id)
        logger.debug(f"[SessionManager] 会话查询前消息数量: {len(session.messages)}")
        session.append_message("user", query)
        logger.debug(f"[SessionManager] 会话查询后消息数量: {len(session.messages)}")
        logger.debug(f"[SessionManager] 会话消息: {session.messages}")
        return session
        
    def session_reply(self, reply, session_id, total_tokens=None):
        """
        添加助手回复
        :param reply: 助手回复
        :param session_id: 会话ID
        :param total_tokens: 总令牌数
        :return: 会话对象
        """
        session = self.build_session(session_id)
        logger.debug(f"[SessionManager] 会话回复前消息数量: {len(session.messages)}")
        if hasattr(session, "append_message"):
            session.append_message("assistant", reply)
        logger.debug(f"[SessionManager] 会话回复后消息数量: {len(session.messages)}")
        return session
        
    def clear_session(self, session_id):
        """
        清除会话
        :param session_id: 会话ID
        """
        if session_id in self.sessions:
            logger.debug(f"[SessionManager] 清除会话: {session_id}")
            del self.sessions[session_id]
            
    def clear_all_session(self):
        """
        清除所有会话
        """
        logger.debug(f"[SessionManager] 清除所有会话")
        self.sessions.clear()

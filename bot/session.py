class Session(object):
    def __init__(self, session_id, system_prompt=None):
        self.session_id = session_id
        self.messages = []
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})

    def append_message(self, role, content):
        """
        添加消息到会话历史
        :param role: 角色，可以是 "system", "user", "assistant"
        :param content: 消息内容
        """
        self.messages.append({"role": role, "content": content})

    def get_messages(self):
        """
        获取所有消息
        :return: 消息列表
        """
        return self.messages 
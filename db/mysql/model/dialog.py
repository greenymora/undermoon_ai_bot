#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger
from sqlalchemy.sql import func

Base = declarative_base()


class Dialog(Base):
    """对话模型类"""
    __tablename__ = 'ab_dialog'
    
    # 字段定义
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键id')
    user_id = Column(BigInteger, nullable=True, comment='用户id')
    ask_type = Column(String(255), nullable=True, default='text', comment='提问方式')
    ask_content = Column(Text, nullable=True, comment='提问内容')
    reply_content = Column(Text, nullable=True, comment='ai回复内容')
    ask_time = Column(DateTime, nullable=True, default=func.now(), comment='提问时间')
    reply_time = Column(DateTime, nullable=True, default=func.now(), comment='回复时间')
    
    def __repr__(self):
        """对象的字符串表示"""
        return f'Dialog(id={self.id}, user_id={self.user_id}, ask_type={self.ask_type!r}, ask_content={self.ask_content!r})'

    @classmethod
    def create_dialog(cls, user_id: int, ask_content: str, ask_type: str = 'text', **kwargs):
        """创建新对话的类方法"""
        dialog = cls(user_id=user_id, ask_content=ask_content, ask_type=ask_type, **kwargs)
        return dialog

    @classmethod
    def from_dict(cls, data_dict):
        """从字典数据构造Dialog对象的类方法"""
        if not data_dict:
            return None
        dialog = cls()
        for key, value in data_dict.items():
            if hasattr(dialog, key):
                setattr(dialog, key, value)
        return dialog
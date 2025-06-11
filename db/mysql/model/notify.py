#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger, Time
from sqlalchemy.sql import func

Base = declarative_base()


class Notify(Base):
    """回复模型类"""
    __tablename__ = 'ab_notify'
    
    # 字段定义
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键id')
    type = Column(Integer, nullable=True, comment='回复类型\r\n1：签订隐私政策的回复\r\n2：打招呼的回复\r\n3：提醒用户等待的回复\r\n4：回看消息的回复')
    content = Column(Text, nullable=True, comment='回复内容')
    start_time = Column(Time, nullable=True, comment='起始时间')
    end_time = Column(Time, nullable=True, comment='终止时间')
    
    def __repr__(self):
        """对象的字符串表示"""
        return f'Reply(id={self.id}, type={self.type}, content={self.content!r}, start_time={self.start_time}, end_time={self.end_time})'

    @classmethod
    def create_reply(cls, type: int, content: str, **kwargs):
        """创建新回复的类方法"""
        notify = cls(type=type, content=content, **kwargs)
        return notify

    @classmethod
    def from_dict(cls, data_dict):
        """从字典数据构造Reply对象的类方法"""
        if not data_dict:
            return None
        notify = cls()
        for key, value in data_dict.items():
            if hasattr(notify, key):
                setattr(notify, key, value)
        return notify 
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger
from sqlalchemy.sql import func

Base = declarative_base()


class User(Base):
    """用户模型类"""
    __tablename__ = 'ab_user'
    
    # 字段定义
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键id')
    openid = Column(String(255), nullable=True, comment='微信openid')
    privacy_status = Column(Integer, nullable=False, default=0, comment='隐私政策状态 0：不授权 1：仅授权ai 2：授权ai及人工')
    remaining_times = Column(Integer, nullable=False, default=10, comment='剩余使用次数')
    real_name = Column(String(255), nullable=True, comment='真实姓名')
    wx_name = Column(String(255), nullable=True, comment='微信名称')
    nickname = Column(String(255), nullable=True, comment='昵称')
    avatar = Column(String(255), nullable=True, comment='头像地址')
    phone = Column(String(255), nullable=True, comment='手机号')
    create_time = Column(DateTime, nullable=False, default=func.now(), comment='注册时间')
    modify_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment='更新时间')
    
    def __repr__(self):
        """对象的字符串表示"""
        return f'User(id={self.id}, openid={self.openid!r}, privacy_status={self.privacy_status}, remaining_times={self.remaining_times})'

    @classmethod
    def create_user(cls, openid: str, **kwargs):
        """创建新用户的类方法"""
        user = cls(openid=openid, **kwargs)
        return user

    @classmethod
    def from_dict(cls, data_dict):
        """从字典数据构造User对象的类方法"""
        if not data_dict:
            return None
        user = cls()
        for key, value in data_dict.items():
            if hasattr(user, key):
                setattr(user, key, value)
        return user
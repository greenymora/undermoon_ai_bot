#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pymysql
import threading
from contextlib import contextmanager
from common.log import logger
from common.singleton import singleton
from config import conf
from db.mysql.model import User


@singleton
class MysqlManager:
    """MySQL连接管理器"""
    def __init__(self,
                host=None,
                port=None,
                user=None,
                password=None,
                database=None):
        # 优先使用传入的参数，否则从配置文件读取
        try:
            self.host = host or conf().get('mysql_host', '8.152.3.34')
            self.port = port or conf().get('mysql_port', 3306)
            self.user = user or conf().get('mysql_user', 'cloudask')
            self.password = password or conf().get('mysql_password', 'Yaoqi100@')
            self.database = database or conf().get('mysql_database', 'aibot')
            self.charset = conf().get('mysql_charset', 'utf8mb4')
        except:
            # 如果配置文件不可用，使用默认值
            self.host = host or '8.152.3.34'
            self.port = port or 3306
            self.user = user or 'cloudask'
            self.password = password or 'Yaoqi100@'
            self.database = database or 'aibot'
            self.charset = 'utf8mb4'
        self._local = threading.local()

    def _get_connection(self):
        """获取线程本地的数据库连接"""
        if not hasattr(self._local, 'connection'):
            try:
                self._local.connection = pymysql.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    charset=self.charset,
                    autocommit=True,
                    cursorclass=pymysql.cursors.DictCursor
                )
            except Exception as e:
                raise e
        return self._local.connection

    @contextmanager
    def _get_cursor(self):
        """获取数据库游标的上下文管理器"""
        connection = self._get_connection()
        cursor = connection.cursor()
        try:
            yield cursor
        except Exception as e:
            logger.error(f"[DatabaseManager] 数据库操作失败: {str(e)}")
            raise e
        finally:
            cursor.close()

    def select_list(self, sql, params=None, return_type=None):
        with self._get_cursor() as cursor:
            cursor.execute(sql, params)
            result_list = cursor.fetchall()
            
            if not result_list:
                return []
                
            if not return_type:
                return result_list
            
            # 如果return_type是类且有from_dict方法，使用from_dict转换
            if hasattr(return_type, 'from_dict') and callable(getattr(return_type, 'from_dict')):
                return [return_type.from_dict(row) for row in result_list]
            
            # 如果return_type是基础类型，提取第一个字段值并转换
            if return_type in (int, str, float, bool):
                converted_list = []
                for row in result_list:
                    value = row[list(row.keys())[0]]
                    if value is None:
                        converted_list.append(None)
                    else:
                        try:
                            converted_list.append(return_type(value))
                        except (ValueError, TypeError) as e:
                            converted_list.append(value)
                return converted_list

    def select_one(self, sql, params=None, return_type=None):
        with self._get_cursor() as cursor:
            cursor.execute(sql, params)
            result = cursor.fetchone()

            if not result:
                return None
                
            if not return_type:
                return result
            
            # 如果return_type是类且有from_dict方法，使用from_dict转换
            if hasattr(return_type, 'from_dict') and callable(getattr(return_type, 'from_dict')):
                return return_type.from_dict(result)
            
            # 如果return_type是基础类型，提取第一个字段值并转换
            if return_type in (int, str, float, bool):
                # 获取第一个字段的值
                value = result[list(result.keys())[0]]
                if value is None:
                    return None
                try:
                    return return_type(value)
                except (ValueError, TypeError) as e:
                    return value

    def update(self, sql, params=None):
        """执行更新/插入/删除语句"""
        with self._get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount
    
    def insert_and_get_id(self, sql, params=None):
        """执行插入语句并返回自增ID"""
        with self._get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.lastrowid


# 创建全局数据库管理器实例
mysql = MysqlManager()
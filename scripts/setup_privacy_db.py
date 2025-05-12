#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pymysql
import datetime
import time

# 使用成功的数据库连接配置
DB_CONFIG = {
    'user': 'root',
    'password': 'Undermoon@250416',
    'database': 'undermoon',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
    'unix_socket': '/var/lib/mysql/mysql.sock'
}

def setup_privacy_table():
    """设置隐私协议表并测试基本操作"""
    print("正在设置隐私协议表...")
    
    try:
        # 连接数据库
        connection = pymysql.connect(**DB_CONFIG)
        
        with connection.cursor() as cursor:
            # 检查表是否存在
            cursor.execute("SHOW TABLES LIKE 'user_privacy_consent'")
            if cursor.fetchone():
                print("表 user_privacy_consent 已存在")
                # 询问是否删除现有表
                answer = input("是否删除现有表并重新创建? (y/n): ")
                if answer.lower() == "y":
                    cursor.execute("DROP TABLE user_privacy_consent")
                    print("表已删除")
                else:
                    print("保留现有表")
            
            # 创建表
            print("创建 user_privacy_consent 表...")
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS user_privacy_consent (
                id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
                has_consented TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否同意隐私协议(0-不同意,1-同意)',
                consent_time DATETIME COMMENT '同意时间',
                device_id VARCHAR(128) COMMENT '设备ID',
                ip_address VARCHAR(45) COMMENT '用户IP地址',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (id),
                INDEX idx_user_id (user_id),
                INDEX idx_consent_time (consent_time)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户隐私协议同意状态表';
            """
            cursor.execute(create_table_sql)
            connection.commit()
            print("表创建成功!")
            
            # 插入测试数据
            test_user_id = f"test_user_{int(time.time())}"
            print(f"插入测试用户: {test_user_id}")
            
            current_time = datetime.datetime.now()
            insert_sql = """
            INSERT INTO user_privacy_consent 
            (user_id, has_consented, consent_time, device_id, ip_address) 
            VALUES (%s, 1, %s, %s, %s)
            """
            cursor.execute(insert_sql, (test_user_id, current_time, "test_device", "127.0.0.1"))
            connection.commit()
            print("测试数据插入成功!")
            
            # 查询测试数据
            query_sql = "SELECT * FROM user_privacy_consent WHERE user_id = %s"
            cursor.execute(query_sql, (test_user_id,))
            result = cursor.fetchone()
            print(f"查询结果: {result}")
            
        connection.close()
        print("数据库操作完成!")
        return True
        
    except Exception as e:
        print(f"设置表失败: {e}")
        import traceback
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    setup_privacy_table() 
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pymysql
import sys

def test_connection(config):
    """测试数据库连接"""
    print(f"尝试连接数据库: {config}")
    try:
        connection = pymysql.connect(**config)
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            print(f"✅ 连接成功! 数据库版本: {version}")
        connection.close()
        return True
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False

def main():
    # 基础配置
    base_config = {
        'user': 'root', 
        'password': 'Undermoon@250416',
        'database': 'undermoon',
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }
    
    # 不同的连接方式
    connection_methods = [
        # 1. 使用localhost
        {**base_config, 'host': 'localhost'},
        
        # 2. 使用127.0.0.1
        {**base_config, 'host': '127.0.0.1'},
        
        # 3. 使用localhost和明确的端口
        {**base_config, 'host': 'localhost', 'port': 3306},
        
        # 4. 使用127.0.0.1和明确的端口
        {**base_config, 'host': '127.0.0.1', 'port': 3306},
        
        # 5. MariaDB可能使用不同端口
        {**base_config, 'host': 'localhost', 'port': 3307},
        {**base_config, 'host': '127.0.0.1', 'port': 3307},
        
        # 6. 使用默认socket
        {**base_config, 'unix_socket': '/var/run/mysqld/mysqld.sock'},
        
        # 7. 使用MariaDB socket
        {**base_config, 'unix_socket': '/var/run/mariadb/mariadb.sock'},
        
        # 8. 另一个常见MariaDB socket位置
        {**base_config, 'unix_socket': '/var/lib/mysql/mysql.sock'},
        
        # 9. 尝试不使用数据库名称连接
        {'user': 'root', 'password': 'Undermoon@250416', 'host': 'localhost'},
        {'user': 'root', 'password': 'Undermoon@250416', 'host': '127.0.0.1'},
        
        # 10. 使用不同用户验证插件
        {**base_config, 'host': 'localhost', 'auth_plugin': 'mysql_native_password'},
        
        # 11. 使用不同的权限
        {'user': 'root', 'password': 'Undermoon@250416', 'host': 'localhost', 'database': 'mysql'},
    ]
    
    # 尝试所有连接方式
    success = False
    for i, config in enumerate(connection_methods):
        print(f"\n方法 {i+1}:")
        if test_connection(config):
            success = True
            print("找到可用的连接方式!")
            break
    
    if not success:
        print("\n所有连接方式都失败了。请尝试以下解决方案:")
        print("1. 验证MySQL/MariaDB服务是否正在运行:")
        print("   systemctl status mysql")
        print("   或")
        print("   systemctl status mariadb")
        
        print("\n2. 检查root密码是否正确:")
        print("   你可以尝试使用以下命令重置密码:")
        print("   sudo mysql -u root")
        print("   或")
        print("   sudo mysql -u root -p")
        
        print("\n3. 检查root用户的身份验证方法:")
        print("   SELECT user, host, plugin FROM mysql.user WHERE user='root';")
        print("   如果plugin是'auth_socket'或'unix_socket'，尝试使用sudo运行脚本")
        
        print("\n4. 创建一个新的可以远程访问的用户:")
        print("   CREATE USER 'undermoon'@'localhost' IDENTIFIED BY 'Undermoon@250416';")
        print("   GRANT ALL PRIVILEGES ON undermoon.* TO 'undermoon'@'localhost';")
        print("   FLUSH PRIVILEGES;")

if __name__ == "__main__":
    main() 
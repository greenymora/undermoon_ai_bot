#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import sys
import time

# 服务器地址配置
API_SERVER = "http://localhost:9900"  # 独立隐私协议API服务地址

def test_privacy_api():
    """测试隐私协议API"""
    print("========== 开始测试隐私协议API ==========")
    
    # 检查服务是否运行
    print("\n检查服务状态...")
    try:
        response = requests.get(f"{API_SERVER}/", timeout=3)
        if response.status_code == 200:
            result = response.json()
            print(f"服务状态: {result}")
            print("✅ 服务正常运行")
        else:
            print(f"❌ 服务异常，状态码: {response.status_code}")
            print(response.text)
            return
    except Exception as e:
        print(f"❌ 无法连接到服务: {str(e)}")
        print("请确认服务已启动并在指定端口运行")
        return
    
    # 生成测试用户ID (使用时间戳确保唯一性)
    test_user_id = f"test_user_{int(time.time())}"
    print(f"\n测试用户ID: {test_user_id}")
    
    # 步骤1: 查询用户隐私协议状态（预期未同意）
    print("\n步骤1: 查询用户初始隐私协议状态...")
    check_url = f"{API_SERVER}/api/privacy/check?user_id={test_user_id}"
    
    try:
        response = requests.get(check_url, timeout=5)
        if response.status_code == 200:
            result = response.json()
            print(f"查询结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
            
            if result['code'] == 200:
                has_consented = result['data']['has_consented']
                print(f"用户是否已同意隐私协议: {has_consented}")
                if not has_consented:
                    print("✅ 测试通过: 新用户默认未同意隐私协议")
                else:
                    print("❌ 测试失败: 新用户应默认未同意隐私协议")
            else:
                print(f"❌ 查询失败: {result['message']}")
        else:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ 查询异常: {str(e)}")
    
    # 步骤2: 更新用户隐私协议状态为已同意
    print("\n步骤2: 更新用户隐私协议状态为已同意...")
    update_url = f"{API_SERVER}/api/privacy/update"
    update_data = {
        "user_id": test_user_id,
        "has_consented": True,
        "device_id": "test_device_001"
    }
    
    try:
        response = requests.post(update_url, json=update_data, timeout=5)
        if response.status_code == 200:
            result = response.json()
            print(f"更新结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
            
            if result['code'] == 200:
                print("✅ 更新成功")
            else:
                print(f"❌ 更新失败: {result['message']}")
        else:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ 更新异常: {str(e)}")
    
    # 步骤3: 再次查询用户隐私协议状态（预期已同意）
    print("\n步骤3: 再次查询用户隐私协议状态...")
    try:
        response = requests.get(check_url, timeout=5)
        if response.status_code == 200:
            result = response.json()
            print(f"查询结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
            
            if result['code'] == 200:
                has_consented = result['data']['has_consented']
                print(f"用户是否已同意隐私协议: {has_consented}")
                if has_consented:
                    print("✅ 测试通过: 用户成功更新为已同意隐私协议")
                else:
                    print("❌ 测试失败: 用户应已同意隐私协议")
            else:
                print(f"❌ 查询失败: {result['message']}")
        else:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ 查询异常: {str(e)}")
    
    print("\n========== 隐私协议API测试完成 ==========")

if __name__ == "__main__":
    # 检查是否有自定义服务器地址参数
    if len(sys.argv) > 1:
        API_SERVER = sys.argv[1]
    
    test_privacy_api() 
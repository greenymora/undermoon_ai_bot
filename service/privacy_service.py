#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
from datetime import datetime

class PrivacyService:
    """隐私协议同意状态管理服务"""
    
    def __init__(self):
        """初始化隐私服务"""
        self.data_file = "privacy_consents.json"
        self.consents = self._load_consents()
    
    def _load_consents(self):
        """从文件加载用户同意记录"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载隐私同意记录失败: {str(e)}")
                return {}
        return {}
    
    def _save_consents(self):
        """保存用户同意记录到文件"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.consents, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存隐私同意记录失败: {str(e)}")
            return False
    
    def check_privacy_agreed(self, user_id):
        """检查用户是否已同意隐私协议"""
        return user_id in self.consents
    
    def set_privacy_agreed(self, user_id, device_id=None, ip_address=None):
        """设置用户同意隐私协议"""
        if not user_id:
            return False
        
        self.consents[user_id] = {
            "agreed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "device_id": device_id,
            "ip_address": ip_address
        }
        
        return self._save_consents()

# 创建单例实例
privacy_service = PrivacyService()

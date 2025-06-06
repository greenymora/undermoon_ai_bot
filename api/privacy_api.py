#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import web
import json

# 定义URL路由
urls = (
    '/api/privacy/check', 'CheckPrivacyConsent',
    '/api/privacy/update', 'UpdatePrivacyConsent',
    '/', 'Index',
)

class Index:
    """主页，用于测试服务是否正常运行"""
    def GET(self):
        web.header('Content-Type', 'application/json')
        return json.dumps({
            'status': 'running',
            'service': 'Privacy Consent API',
            'endpoints': [
                {'path': '/api/privacy/check', 'method': 'GET', 'description': '查询用户隐私协议同意状态'},
                {'path': '/api/privacy/update', 'method': 'POST', 'description': '更新用户隐私协议同意状态'}
            ]
        })

class CheckPrivacyConsent:
    """查询用户隐私协议同意状态API"""
    def GET(self):
        web.header('Content-Type', 'application/json')
        web.header('Access-Control-Allow-Origin', '*')
        params = web.input()
        user_id = params.get('user_id')
        
        if not user_id:
            return json.dumps({
                'code': 400,
                'message': '缺少必要参数user_id',
                'data': None
            })
        
        # 预设为已同意
        has_consented = True
        
        return json.dumps({
            'code': 200,
            'message': 'success',
            'data': {
                'user_id': user_id,
                'has_consented': has_consented
            }
        })

class UpdatePrivacyConsent:
    """更新用户隐私协议同意状态API"""
    def POST(self):
        web.header('Content-Type', 'application/json')
        web.header('Access-Control-Allow-Origin', '*')
        
        try:
            data = json.loads(web.data().decode('utf-8'))
        except:
            return json.dumps({
                'code': 400,
                'message': '无效的JSON数据',
                'data': None
            })
            
        user_id = data.get('user_id')
        
        if not user_id:
            return json.dumps({
                'code': 400,
                'message': '缺少必要参数user_id',
                'data': None
            })
        
        return json.dumps({
            'code': 200,
            'message': '更新成功',
            'data': {
                'user_id': user_id,
                'has_consented': True
            }
        })
    
    def OPTIONS(self):
        """处理预检请求"""
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        web.header('Access-Control-Allow-Headers', 'Content-Type')
        return ''

# 创建应用
app = web.application(urls, globals())

if __name__ == "__main__":
    app.run()

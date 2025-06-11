#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import web
import json
from service.privacy_service import privacy_service
from db.mysql.mysql_manager import mysql
from db.mysql.model.user import User

# 定义URL路由
urls = (
    '/', 'Index',
    '/api/privacy/check', 'CheckPrivacyStatus',
    '/api/privacy/update', 'UpdatePrivacyStatus',
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


class CheckPrivacyStatus:
    """查询用户隐私协议同意状态API"""
    def GET(self):
        web.header('Content-Type', 'application/json')
        web.header('Access-Control-Allow-Origin', '*')
        params = web.input()
        user_id = params.get('user_id')
        openid = params.get('openid')

        if not user_id and not openid:
            return json.dumps({
                'code': 400,
                'message': '缺少必要参数user_id或openid',
                'data': None
            })

        privacy_status = privacy_service.check_privacy_agreed(user_id, openid)

        return json.dumps({
            'code': 200,
            'message': 'success',
            'data': {
                'user_id': user_id,
                'openid': openid,
                'privacy_status': privacy_status
            }
        })


class UpdatePrivacyStatus:
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
        openid = data.get('openid')
        status = data.get('status')

        if not status:
            return json.dumps({
                'code': 400,
                'message': '缺少必要参数status',
                'data': None
            })

        if not user_id and not openid:
            return json.dumps({
                'code': 400,
                'message': '缺少必要参数user_id或openid',
                'data': None
            })

        privacy_service.update_privacy_status(user_id, openid, status)
        if status > 1:
            privacy_service.agree_notify(openid)

        return json.dumps({
            'code': 200,
            'message': '更新成功',
            'data': {
                'user_id': user_id,
                'openid': openid,
                'privacy_status': status
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

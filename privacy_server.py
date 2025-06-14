#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import web
import json
import sys
import requests

from service.privacy_service import privacy_service
from config import conf, load_config

# 定义URL路由
urls = (
    '/', 'Index',
    '/api/privacy/check', 'CheckPrivacyStatus',
    '/api/privacy/update', 'UpdatePrivacyStatus',
    '/api/wechat/openid', 'WechatOpenId',
)


class Index:
    """主页，用于测试服务是否正常运行"""
    def GET(self):
        web.header('Content-Type', 'application/json')
        return json.dumps({
            'status': 'running',
            'service': 'Privacy Consent API',
            'endpoints': [
                {'path': '/api/privacy/openid', 'method': 'GET', 'description': '使用code换取openid'},
                {'path': '/api/privacy/check', 'method': 'GET', 'description': '查询用户隐私协议状态'},
                {'path': '/api/privacy/update', 'method': 'POST', 'description': '更新用户隐私协议状态'}
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
                "privacy_status": privacy_status
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
        privacy_status = data.get('privacy_status')

        if not privacy_status:
            return json.dumps({
                'code': 400,
                'message': '缺少必要参数privacy_status',
                'data': None
            })

        if not user_id and not openid:
            return json.dumps({
                'code': 400,
                'message': '缺少必要参数user_id或openid',
                'data': None
            })

        privacy_service.update_privacy_status(user_id, openid, privacy_status)

        if privacy_status > 1:
            privacy_service.send_agree_notify(openid)

        return json.dumps({
            'code': 200,
            'message': '更新成功',
            'data': {
                'user_id': user_id,
                'openid': openid,
                'privacy_status': privacy_status
            }
        })

    def OPTIONS(self):
        """处理预检请求"""
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        web.header('Access-Control-Allow-Headers', 'Content-Type')
        return ''


class WechatOpenId:
    """根据code换取微信openid"""
    def GET(self):
        web.header('Content-Type', 'application/json')
        web.header('Access-Control-Allow-Origin', '*')
        params = web.input()
        code = params.get('code')
        if not code:
            return json.dumps({
                'code': 400,
                'message': '缺少code参数',
                'data': None
            })
        # 从config.json读取
        appid = conf().get('wechatmp_app_id')
        secret = conf().get('wechatmp_app_secret')

        if not appid or not secret:
            return json.dumps({
                'code': 500,
                'message': '未配置微信appid或secret',
                'data': None
            })

        url = f"https://api.weixin.qq.com/sns/oauth2/access_token?appid={appid}&secret={secret}&code={code}&grant_type=authorization_code"
        try:
            resp = requests.get(url, timeout=5)
            data = resp.json()
            if 'errcode' in data and data['errcode'] != 0:
                return json.dumps({
                    'code': 500,
                    'message': f"微信接口错误: {data.get('errmsg')}",
                    'data': data
                })
            openid = data.get('openid')
            if not openid:
                return json.dumps({
                    'code': 500,
                    'message': '未获取到openid',
                    'data': data
                })
            return json.dumps({
                'code': 200,
                'message': 'success',
                'data': {'openid': openid}
            })
        except Exception as e:
            return json.dumps({
                'code': 500,
                'message': f'服务器异常: {str(e)}',
                'data': None
            })


# 创建应用
app = web.application(urls, globals())


def run_server(port=9900):
    """运行服务器"""

    # 确保配置被正确加载
    try:
        # 重新加载配置
        load_config()

        # 验证微信配置是否存在
        wechatmp_app_id = conf().get('wechatmp_app_id')
        wechatmp_app_secret = conf().get('wechatmp_app_secret')
        print(f"微信配置加载状态: AppID={'已配置' if wechatmp_app_id else '未配置'}, Secret={'已配置' if wechatmp_app_secret else '未配置'}")
    except Exception as e:
        print(f"加载配置时出错: {str(e)}")

    # 启动服务器
    app.run()


if __name__ == "__main__":
    # 如果提供了自定义端口，使用它
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9900
    run_server(port)
    
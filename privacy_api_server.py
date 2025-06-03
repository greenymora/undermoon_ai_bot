#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import web
import json
import sys
import os
import signal
from service.privacy_service import privacy_service
from common.log import logger
import requests
from config import conf, load_config

# 定义URL路由
urls = (
    '/api/privacy/check', 'CheckPrivacyConsent',
    '/api/privacy/update', 'UpdatePrivacyConsent',
    '/', 'Index',
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
                {'path': '/api/privacy/check', 'method': 'GET', 'description': '查询用户隐私协议同意状态'},
                {'path': '/api/privacy/update', 'method': 'POST', 'description': '更新用户隐私协议同意状态'}
            ]
        })

class CheckPrivacyConsent:
    """查询用户隐私协议同意状态API"""
    def GET(self):
        try:
            # 设置响应头
            web.header('Content-Type', 'application/json')
            web.header('Access-Control-Allow-Origin', '*')  # 允许跨域访问
            
            # 获取请求参数
            params = web.input()
            user_id = params.get('user_id')
            
            if not user_id:
                return json.dumps({
                    'code': 400,
                    'message': '缺少必要参数user_id',
                    'data': None
                })
            
            # 查询用户隐私协议同意状态
            # 新增consent_type，兼容老service返回
            result = privacy_service.check_privacy_agreed(user_id)
            if isinstance(result, tuple):
                has_consented, consent_type = result
            else:
                has_consented = result
                consent_type = 'ai'
            
            return json.dumps({
                'code': 200,
                'message': 'success',
                'data': {
                    'user_id': user_id,
                    'has_consented': has_consented,
                    'consent_type': consent_type
                }
            })
            
        except Exception as e:
            logger.error(f"[PrivacyAPI] 查询隐私协议状态失败: {str(e)}")
            return json.dumps({
                'code': 500,
                'message': f'服务器内部错误: {str(e)}',
                'data': None
            })

class UpdatePrivacyConsent:

    def _send_confirmation_message(self, user_id):
        """向用户发送隐私协议确认消息"""
        try:
            # 导入微信公众号客户端
            from channel.wechatmp.wechatmp_client import WechatMPClient
            
            # 获取微信配置
            appid = conf().get('wechatmp_app_id')
            secret = conf().get('wechatmp_app_secret')
            
            if not appid or not secret:
                logger.error("[PrivacyAPI] 微信公众号配置不完整，无法发送消息")
                return False
            
            # 创建微信客户端
            client = WechatMPClient(appid, secret)
            
            # 发送确认消息
            seccess_notify = """看来你已立契~ 本神现在的业务有：

                                1. 教你该怎么跟对面的人聊
                                2. 分析聊天记录，指点一二
                                3. 分析聊天记录，指点一二

                                偶尔本神心情不错的时候，也会破例陪你聊个天🤷 不过先交代清楚➡️ 你是男是女？喜欢男的还是女的？"""
                            
            try:
                # 发送消息
                client.message.send_text(user_id, seccess_notify)
            except Exception as e:
                logger.error(f"[PrivacyAPI] 发送第确认消息失败: {str(e)}")
                raise e
            return True
        except Exception as e:
            logger.error(f"[PrivacyAPI] 发送确认消息异常: {str(e)}")
            return False
    

    """更新用户隐私协议同意状态API"""
    def POST(self):
        try:
            # 设置响应头
            web.header('Content-Type', 'application/json')
            web.header('Access-Control-Allow-Origin', '*')  # 允许跨域访问
            
            # 获取请求参数
            try:
                data = json.loads(web.data().decode('utf-8'))
            except:
                return json.dumps({
                    'code': 400,
                    'message': '无效的JSON数据',
                    'data': None
                })
                
            user_id = data.get('user_id')
            has_consented = data.get('has_consented', True)
            device_id = data.get('device_id')
            consent_type = data.get('consent_type', 'ai')  # 新增
            
            if not user_id:
                return json.dumps({
                    'code': 400,
                    'message': '缺少必要参数user_id',
                    'data': None
                })
            
            # 获取客户端IP地址
            ip_address = web.ctx.env.get('REMOTE_ADDR')
            
            # 更新用户隐私协议同意状态
            if has_consented:
                # 兼容service层接口
                try:
                    success = privacy_service.set_privacy_agreed(user_id, device_id, ip_address, consent_type)
                except TypeError:
                    # 老接口不支持consent_type
                    success = privacy_service.set_privacy_agreed(user_id, device_id, ip_address)
                
                if success:
                    # 发送确认消息给用户
                    try:
                        self._send_confirmation_message(user_id)
                        logger.info(f"[PrivacyAPI] 已向用户 {user_id} 发送隐私协议确认消息")
                    except Exception as e:
                        logger.error(f"[PrivacyAPI] 发送确认消息失败: {str(e)}")
                        # 即使发送消息失败，也不影响隐私协议的更新结果
                    
                    return json.dumps({
                        'code': 200,
                        'message': '更新成功',
                        'data': {
                            'user_id': user_id,
                            'has_consented': True,
                            'consent_type': consent_type
                        }
                    })
                else:
                    return json.dumps({
                        'code': 500,
                        'message': '更新失败',
                        'data': None
                    })
            else:
                return json.dumps({
                    'code': 400,
                    'message': '不支持取消同意操作',
                    'data': None
                })
                
        except Exception as e:
            logger.error(f"[PrivacyAPI] 更新隐私协议状态失败: {str(e)}")
            return json.dumps({
                'code': 500,
                'message': f'服务器内部错误: {str(e)}',
                'data': None
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
            return json.dumps({'code': 400, 'message': '缺少code参数', 'data': None})
        # 从config.json读取
        appid = conf().get('wechatmp_app_id')
        secret = conf().get('wechatmp_app_secret')
        
        if not appid or not secret:
            return json.dumps({'code': 500, 'message': '未配置微信appid或secret', 'data': None})

        url = f"https://api.weixin.qq.com/sns/oauth2/access_token?appid={appid}&secret={secret}&code={code}&grant_type=authorization_code"
        try:
            resp = requests.get(url, timeout=5)
            data = resp.json()
            if 'errcode' in data and data['errcode'] != 0:
                return json.dumps({'code': 500, 'message': f"微信接口错误: {data.get('errmsg')}", 'data': data})
            openid = data.get('openid')
            if not openid:
                return json.dumps({'code': 500, 'message': '未获取到openid', 'data': data})
            return json.dumps({'code': 200, 'message': 'success', 'data': {'openid': openid}})
        except Exception as e:
            return json.dumps({'code': 500, 'message': f'服务器异常: {str(e)}', 'data': None})

# 创建应用
app = web.application(urls, globals())

# 处理中断信号
def sigterm_handler(signum, frame):
    """处理终止信号"""
    print(f"收到信号 {signum}，正在关闭服务...")
    sys.exit(0)

def run_server(port=9900):
    """运行服务器"""
    # 注册信号处理器
    signal.signal(signal.SIGINT, sigterm_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, sigterm_handler)  # kill
    
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
    
    # 设置监听端口
    sys.argv = ['privacy_api_server.py', f'{port}']
    
    print(f"隐私协议API服务正在启动，端口: {port}")
    print("可用的API端点:")
    print("- GET /api/privacy/check?user_id=xxx  查询用户隐私协议同意状态")
    print("- POST /api/privacy/update  更新用户隐私协议同意状态")
    print("- GET /api/wechat/openid?code=xxx  通过code获取微信OpenID")
    
    # 启动服务器
    app.run()

if __name__ == "__main__":
    # 如果提供了自定义端口，使用它
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9900
    run_server(port) 

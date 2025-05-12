#!/bin/bash

# 确保工作目录正确
cd /root/workspace/undermoon_ai_bot

# 停止现有服务
echo "停止现有服务..."
pkill -f "python3 privacy_api_server.py"
pkill -f "python3 app.py"
sleep 2

# 启动隐私协议API服务
echo "启动隐私协议API服务..."
nohup python3 privacy_api_server.py 9900 > privacy_api.log 2>&1 &
PRIVACY_API_PID=$!
echo "隐私协议API服务已启动，PID: $PRIVACY_API_PID"

# 等待API服务启动
sleep 2

# 启动主应用
echo "启动主应用..."
nohup python3 app.py -c config.json > app.log 2>&1 &
APP_PID=$!
echo "主应用已启动，PID: $APP_PID，端口: 9899"

echo "所有服务已启动" 
#!/bin/bash

# 确保工作目录正确
cd /root/workspace/undermoon_ai_bot || { echo "❌ 无法切换到项目目录，脚本中止！"; exit 1; }

# 获取进程PID的精确函数
get_pid() {
    local process_name=$1
    pgrep -f "python3.*${process_name}$" | grep -v $$
}

# 停止 privacy_server 服务
pid=$(get_pid "privacy_server.py")
if [ -n "$pid" ]; then
    echo "【停止】隐私服务：$pid"
    kill -15 $pid
    # 等待进程优雅退出
    for i in {1..5}; do
        if ! ps -p $pid > /dev/null; then
            break
        fi
        sleep 1
    done
    # 如果进程仍然存在，强制结束
    if ps -p $pid > /dev/null; then
        echo "⚠️ 进程未响应，强制结束"
        kill -9 $pid
        sleep 1
    fi
fi

if get_pid "privacy_server.py" > /dev/null; then
    echo "❌ 无法停止隐私服务，程序中止"
    exit 1
else
    echo "✅ 隐私服务已停止"
fi
echo ""

# 停止 app.py 服务
pid=$(get_pid "app.py")
if [ -n "$pid" ]; then
    echo "【停止】AI服务：$pid"
    kill -15 $pid
    # 等待进程优雅退出
    for i in {1..5}; do
        if ! ps -p $pid > /dev/null; then
            break
        fi
        sleep 1
    done
    # 如果进程仍然存在，强制结束
    if ps -p $pid > /dev/null; then
        echo "⚠️ 进程未响应，强制结束"
        kill -9 $pid
        sleep 1
    fi
fi

if get_pid "app.py" > /dev/null; then
    echo "❌ 无法停止AI服务，程序中止..."
    exit 1
else
    echo "✅ AI服务已停止"
fi
echo ""

# 清空日志
> privacy_server.log
> app.log

# 启动 privacy_server 服务
echo "【启动】隐私服务"
nohup python3 privacy_server.py 9900 > privacy_server.log 2>&1 &
PRIVACY_API_PID=$!
sleep 2
if ! ps -p $PRIVACY_API_PID > /dev/null || ! lsof -iTCP:9900 -sTCP:LISTEN > /dev/null; then
    echo "❌ 隐私服务启动失败，日志如下："
    tail -n 20 privacy_server.log
    kill $PRIVACY_API_PID 2>/dev/null
    exit 1
else
    echo "✅ 隐私服务启动成功，PID: $PRIVACY_API_PID，PORT: 9900"
fi
echo ""

# 启动主应用 app.py
echo "【启动】AI服务"
nohup python3 app.py -c config.json > app.log 2>&1 &
APP_PID=$!
sleep 2
if ! ps -p $APP_PID > /dev/null || ! lsof -iTCP:9899 -sTCP:LISTEN > /dev/null; then
    echo "❌ AI服务启动失败，日志如下："
    tail -n 20 app.log
    kill $APP_PID 2>/dev/null
    exit 1
else
    echo "✅ AI服务启动成功，PID: $APP_PID，PORT: 9899"
fi


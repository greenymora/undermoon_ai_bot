pids=$(ps -ef | grep app.py | grep -v grep | awk '{print $2}')

if [ -n "$pids" ]; then
    kill -9 $pids
    echo "已终止 app.py"
else
    echo "未找到 app.py"
fi

# 重新启动 app.py 进程
nohup python3 app.py &
echo "已重新启动 app.py"

# 延时 3 秒
sleep 3

# 清空 run.log 文件
echo "" > run.log
echo "已清空 run.log"

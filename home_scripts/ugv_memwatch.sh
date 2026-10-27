#!/bin/bash
# UGV 内存监视器 —— 导航/建图时另开一个终端运行，定位"哪个进程把内存吃掉"
# 用法:
#   ~/ugv_memwatch.sh              5 秒记录一次，直到 Ctrl+C
#   ~/ugv_memwatch.sh 3 600        3 秒一次，记 10 分钟自动停
# 输出: ~/memwatch_<时间戳>.log，事后可用以下命令看谁一直在涨:
#   grep -E "MB  " ~/memwatch_*.log | awk '{print $2, $3}' | sort | uniq -c | sort -rn | head
INTERVAL=${1:-5}
DURATION=${2:-0}
CT=ugv_jetson_ros_humble
OUT="$HOME/memwatch_$(date +%Y%m%d_%H%M%S).log"
echo "记录到: $OUT  (间隔 ${INTERVAL}s, 时长 ${DURATION}s, 0=不限)"
{
  echo "# ugv_memwatch 开始 $(date '+%F %T')  间隔=${INTERVAL}s 时长=${DURATION}s"
  echo "# 列含义: MB=该进程常驻内存(RSS)  命令=进程名"
} >> "$OUT"
end=$((SECONDS + DURATION))
while :; do
  {
    echo "===== $(date '+%F %T') ====="
    free -m | grep -E "Mem|Swap" | sed 's/^/  /'
    docker stats --no-stream --format '  [容器整体] {{.MemUsage}} ({{.MemPerc}})  CPU {{.CPUPerc}}' "$CT" 2>/dev/null
    docker exec "$CT" bash -lc 'ps -eo rss,args --sort=-rss --no-headers | head -n 8 | awk "{mb=\$1/1024; \$1=\"\"; printf \"  %6.1fMB  %s\n\", mb, substr(\$0,1,95)}"' 2>/dev/null
  } >> "$OUT" 2>&1
  sleep "$INTERVAL"
  [ "$DURATION" -gt 0 ] && [ "$SECONDS" -ge "$end" ] && break
done
echo "已结束，日志: $OUT"

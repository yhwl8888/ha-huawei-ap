#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 华为商用 AP 诊断工具（零依赖，仅用系统 OpenSSH）
#
# 用途：把 Home Assistant 集成注入前，先在设备上验证 SSH 通道与各条 CLI 命令
#       是否可用，并打印真实输出，便于核对解析结果。
#
# 用法：
#   ./probe_huawei_ap.sh --host 192.168.1.50 --password '你的密码'
#   ./probe_huawei_ap.sh -H 192.168.1.50 -u admin -p '密码' --dump raw.txt
#   ./probe_huawei_ap.sh -H 192.168.1.50 -p '密码' --login-only
#
# 说明：密码只写入临时文件（base64 编码）供 SSH_ASKPASS 读取，脚本退出即删除。
# ---------------------------------------------------------------------------
set -uo pipefail

HOST=""
USER_NAME="admin"
PASSWORD=""
PORT=22
DUMP=""
LOGIN_ONLY=0

usage() {
  cat <<'EOF'
华为商用 AP 诊断工具

  -H, --host <ip>         AP 地址（必填）
  -u, --user <name>       SSH 用户名（默认 admin）
  -p, --password <pass>   SSH 密码（必填）
      --port <n>          SSH 端口（默认 22）
      --dump <file>       把原始输出写入文件
      --login-only        只验证登录
  -h, --help              显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -H|--host)     HOST="${2:-}"; shift 2 ;;
    -u|--user)     USER_NAME="${2:-}"; shift 2 ;;
    -p|--password) PASSWORD="${2:-}"; shift 2 ;;
    --port)        PORT="${2:-22}"; shift 2 ;;
    --dump)        DUMP="${2:-}"; shift 2 ;;
    --login-only)  LOGIN_ONLY=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "未知参数: $1"; usage; exit 1 ;;
  esac
done

if [[ -z "$HOST" || -z "$PASSWORD" ]]; then
  echo "错误: --host 与 --password 为必填项"
  usage
  exit 1
fi

TMP_BASE="${TMPDIR:-/tmp}"
ASKPASS="${TMP_BASE}/huawei_ap_askpass_$$.sh"
RAW="${TMP_BASE}/huawei_ap_raw_$$.txt"
: >"$RAW"
cleanup() { rm -f "$ASKPASS" "$RAW" 2>/dev/null; }
trap cleanup EXIT

# base64 避免密码里的引号/美元符等特殊字符被 shell 解释
ENC="$(printf '%s' "$PASSWORD" | base64 | tr -d '\n')"
printf '#!/bin/sh\nprintf "%%s" "%s" | base64 -d\n' "$ENC" > "$ASKPASS"
chmod +x "$ASKPASS"

SSH_OPTS=(
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/dev/null
  -o PreferredAuthentications=password
  -o PubkeyAuthentication=no
  -o ConnectTimeout=10
  -o KexAlgorithms=+diffie-hellman-group14-sha1
  -o HostKeyAlgorithms=+ssh-rsa
  -o LogLevel=ERROR
)

run_session() {
  local -a cmds=("$@")
  {
    # VRP needs a moment after screen-length, and the very first command typed
    # into a fresh PTY is swallowed by the terminal setup. Burn both on a
    # harmless blank line so the caller's first real command is not lost.
    printf 'screen-length 0 temporary\n'
    sleep 3
    printf '\n'
    sleep 2
    local c
    for c in "${cmds[@]}"; do
      printf '%s\n' "$c"
      sleep 3
    done
    printf 'quit\n'
    sleep 1
  } | SSH_ASKPASS="$ASKPASS" SSH_ASKPASS_REQUIRE=force DISPLAY=:0 \
      timeout 180 ssh -tt "${SSH_OPTS[@]}" -p "$PORT" "$USER_NAME@$HOST" 2>&1 \
      | tr -d '\r'
}

echo "======================================================================"
echo "华为 AP 诊断  ->  ${USER_NAME}@${HOST}:${PORT}"
echo "======================================================================"

OUT="$(run_session 'display version')"
RC=$?
if [[ -z "$OUT" ]]; then
  echo "[FAIL] 没有任何输出。请检查地址/端口/密码，或确认 SSH 已开启。"
  exit 1
fi
if grep -qiE "permission denied|authentication failed" <<<"$OUT"; then
  echo "[FAIL] SSH 认证失败，请检查用户名与密码。"
  exit 1
fi
if grep -q "Unrecognized command" <<<"$OUT"; then
  echo "[FAIL] 登录成功但命令被拒绝，该账号可能没有管理员权限。"
  exit 1
fi

echo "[OK  ] SSH 登录成功"
echo ""

# ---- 设备摘要 --------------------------------------------------------------
MODEL="$(sed -n 's/.*Board[[:space:]]*Type[[:space:]]*:[[:space:]]*\([A-Za-z0-9-]*\).*/\1/p' <<<"$OUT" | head -1)"
[[ -z "$MODEL" ]] && MODEL="$(sed -n 's/^Huawei[[:space:]]\+\([A-Za-z0-9-]*\)[[:space:]]\+Router.*/\1/p' <<<"$OUT" | head -1)"
VRP="$(sed -n 's/.*Version[[:space:]]\+\([0-9][0-9.]*\).*/\1/p' <<<"$OUT" | head -1)"
BUILD="$(sed -n 's/.*Version[[:space:]]\+[0-9.]*[[:space:]]*(\([^)]*\)).*/\1/p' <<<"$OUT" | head -1)"
UPTIME="$(grep -o 'uptime is .*' <<<"$OUT" | head -1)"
MODE="$(sed -n 's/.*Current Work Mode[[:space:]]*:[[:space:]]*\([A-Za-z]*\).*/\1/p' <<<"$OUT" | head -1)"

echo "设备摘要"
echo "  型号      : ${MODEL:-未知}"
echo "  固件      : ${VRP:-未知} ${BUILD:-}"
echo "  工作模式  : ${MODE:-未知}"
echo "  ${UPTIME:-运行时长未知}"
echo ""

if [[ $LOGIN_ONLY -eq 1 ]]; then
  echo "已按要求只验证登录，结束。"
  exit 0
fi

# ---- 批量执行 --------------------------------------------------------------
COMMANDS=(
  "display cpu-usage"
  "display memory-usage"
  "display temperature all"
  "display station all"
  "display ap all"
  "display radio all"
  "display interface brief"
)

echo "----------------------------------------------------------------------"
echo "命令可用性"
echo "----------------------------------------------------------------------"
BODY="$(run_session "${COMMANDS[@]}")"
{
  echo "$OUT"
  echo "$BODY"
} >"$RAW"

OK_COUNT=0
for cmd in "${COMMANDS[@]}"; do
  # 抓取该命令之后的段落：从命令回显行到下一条命令回显前
  SNIPPET="$(awk -v cmd="$cmd" '
    $0 ~ ">" cmd "$" {found=1; next}
    found && /^<.*>/ {exit}
    found {print}
  ' <<<"$BODY")"

  if [[ -z "$SNIPPET" ]]; then
    echo "  [MISS] $cmd  (无输出)"
  elif grep -qE "^[[:space:]]*\^[[:space:]]*$|Error: (Unrecognized|Ambiguous|Incomplete)" <<<"$SNIPPET"; then
    ERR="$(grep -oE 'Error: .*' <<<"$SNIPPET" | head -1)"
    echo "  [FAIL] $cmd  -> $ERR"
  else
    LINES="$(wc -l <<<"$SNIPPET" | tr -d ' ')"
    echo "  [ OK ] $cmd  (${LINES} 行)"
    OK_COUNT=$((OK_COUNT + 1))
  fi
done

echo ""
echo "----------------------------------------------------------------------"
echo "关键数据"
echo "----------------------------------------------------------------------"
CPU="$(awk '/display cpu-usage/{f=1;next} f&&/^<.*>/{exit} f' <<<"$BODY" | grep -oE 'CPU[[:space:]]+Usage:[[:space:]]*[0-9.]+%' | head -1)"
MEM="$(awk '/display memory-usage/{f=1;next} f&&/^<.*>/{exit} f' <<<"$BODY" | grep -oE 'Memory Using Percentage Is:[[:space:]]*[0-9]+%' | head -1)"
TEMP="$(awk '/display temperature all/{f=1;next} f&&/^<.*>/{exit} f' <<<"$BODY" | grep NORMAL | awk '{print $NF}' | sort -rn | head -1)"
STA="$(awk '/display station all/{f=1;next} f&&/^<.*>/{exit} f' <<<"$BODY" | grep -oE 'Total: [0-9]+ 2\.4G: [0-9]+ 5G: [0-9]+ 6G: [0-9]+' | head -1)"
AP="$(awk '/display ap all/{f=1;next} f&&/^<.*>/{exit} f' <<<"$BODY" | grep -oE '^Total: [0-9]+' | head -1)"

echo "  ${CPU:-CPU 未取到}"
echo "  ${MEM:-内存 未取到}"
echo "  最高温度 : ${TEMP:-?} °C"
echo "  ${STA:-终端统计未取到}"
echo "  ${AP:-AP 数量未取到}"

echo ""
echo "----------------------------------------------------------------------"
echo "终端列表（前 10 条）"
echo "----------------------------------------------------------------------"
awk '/display station all/{f=1;next} f&&/^<.*>/{exit} f' <<<"$BODY" \
  | grep -E '^[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}' | head -10 | sed 's/^/  /'

echo ""
echo "======================================================================"
if [[ $OK_COUNT -eq ${#COMMANDS[@]} ]]; then
  echo "结论：全部 ${OK_COUNT} 条命令可用，集成可直接接入。"
else
  echo "结论：${OK_COUNT}/${#COMMANDS[@]} 条命令可用，其余会被集成自动跳过。"
fi
echo "======================================================================"

if [[ -n "$DUMP" ]]; then
  cp "$RAW" "$DUMP"
  echo "原始输出已保存: $DUMP"
fi

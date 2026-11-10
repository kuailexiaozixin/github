#!/usr/bin/env bash
# push_repo.sh — 多 IP 重试推送 GitHub（国内网络不稳时的已验证方案）
#
# 用法: push_repo.sh <repo本地目录> <owner/repo> [分支]
#   <repo本地目录>  Git 仓库根目录（绝对路径）
#   <owner/repo>    如 kuailexiaozixin/fasthtml-desktop
#   [分支]          默认 main
#
# 前置: 已通过 gh auth login 登录，并把 token 写入用户环境变量 GITHUB_TOKEN
#   （setx GITHUB_TOKEN "<token>"）。脚本只从环境变量读 token，不依赖任何文件。
#
# 原理: github.com 域名在部分网络下 DNS 解析到不通 IP，导致直连 push 失败。
#   此脚本探测一组已知可达的 github.com IP，用 git insteadOf + extraheader
#   强制走可达 IP，跟随 301 重定向时会被 again insteadOf 映射回该 IP。
set -u
REPO_DIR="$1"
FULL_NAME="$2"
BRANCH="${3:-main}"

TOKEN="${GITHUB_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  # setx 写入 HKCU\Environment 后，当前 shell 环境可能未刷新；从注册表兜底读取
  TOKEN=$(python -c "import winreg; k=winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment'); v,_=winreg.QueryValueEx(k,'GITHUB_TOKEN'); print(v)" 2>/dev/null)
fi
if [ -z "$TOKEN" ]; then
  echo "NO_TOKEN: 未设置 GITHUB_TOKEN（用 gh auth login 登录后 setx GITHUB_TOKEN <token>）"
  exit 4
fi
B64=$(printf 'x-oauth-basic:%s' "$TOKEN" | base64 -w0)

# github.com 前端 IP 池，取值与 references/access.md 第一节 github.com 那一行相同
# （2026-11-10 六枚实测均 200）。20.205.243.168 是 api 前端、对 github.com 回 400，不要加。
IPS=(140.82.112.3 140.82.113.3 140.82.113.4 140.82.114.3 140.82.116.3 20.205.243.166)

# 阶段1: 探测当前网络下哪些 IP 可达
REACHABLE=()
for ip in "${IPS[@]}"; do
  if curl -s -o /dev/null --connect-timeout 5 --max-time 8 --resolve github.com:443:$ip https://github.com/ 2>/dev/null; then
    REACHABLE+=("$ip")
  fi
done
echo "reachable_ips: ${REACHABLE[*]:-none}"

cd "$REPO_DIR" || { echo "NO_DIR"; exit 2; }
if [ ${#REACHABLE[@]} -eq 0 ]; then
  echo "NO_REACHABLE_IP"
  exit 3
fi

# 阶段2: 对可达 IP 依次推送
for ip in "${REACHABLE[@]}"; do
  echo ">>> push via $ip"
  if git -c url.https://$ip/.insteadOf=https://github.com/ \
        -c http.sslVerify=false -c http.version=HTTP/1.1 \
        -c "http.https://$ip/.extraheader=AUTHORIZATION: basic $B64" \
        push -u origin "$BRANCH" 2>&1; then
    echo "PUSH_OK via $ip"
    exit 0
  fi
  echo "<<< push via $ip failed"
done
echo "ALL_IP_FAILED"
exit 5

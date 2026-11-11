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
# 原理与三次方案变更（都在本机实测过，不要退回旧写法）：
#
#   v1  url.<ip>/.insteadOf  —— 2026-11-10 实测**六个 IP 全部失败**：git 会把
#       远端域名先解析一次，DNS 被阻断时在拨号前就报
#       `Failed to connect to github.com:443`，insteadOf 改不掉这一步。
#       同一秒 `curl --resolve` 打同一个 IP 却回 200，说明不是 IP 不通，
#       是这条路本身走不通。
#   v2  直连 / 挂代理      —— 都依赖 DNS 或代理进程在跑，两者一起失效时无解。
#   v3  http.curloptResolve（当前）—— 把「域名→IP」交给 libcurl 在连接层完成，
#       不经过 git 自己的 DNS 解析。2026-11-10 实测六个 IP **全部成功**
#       返回同一个 HEAD。这是本脚本现在用的方案。
#
#   另外：全局 .gitconfig 里可能留着一条 http.proxy（用户以前为某个代理写的）。
#   代理客户端一关，所有 git 命令都会先去撞那个死端口、几秒后才报错，看起来
#   像网络故障，其实是配置残留。脚本一律用 `-c http.proxy=` 把它按单条命令清掉；
#   要查本机有没有这条，跑 git config --global --get http.proxy（见
#   references/access.md 第三节末）。
set -u
REPO_DIR="$1"
FULL_NAME="$2"
BRANCH="${3:-main}"

TOKEN="${GITHUB_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  # setx 写入 HKCU\Environment 后，当前 shell 环境可能未刷新；从注册表兜底读取
  # 用 PYTHONIOENCODING 防止中文用户名在 GBK 控制台解码失败
  TOKEN=$(PYTHONIOENCODING=utf-8 python -c "import winreg; k=winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment'); v,_=winreg.QueryValueEx(k,'GITHUB_TOKEN'); print(v)" 2>/dev/null)
fi
# 注册表里没有该值時，上面的 python 会异常退出，stdout 为空；这里再挡一次
# 非空但明显不是 token 的返回值（例如某些环境把 None 打印出来）
case "$TOKEN" in
  ""|"None"|"null") TOKEN="" ;;
esac
if [ -z "$TOKEN" ]; then
  echo "NO_TOKEN: 未设置 GITHUB_TOKEN（用 gh auth login 登录后 setx GITHUB_TOKEN <token>）"
  exit 4
fi
B64=$(printf 'x-oauth-basic:%s' "$TOKEN" | base64 -w0)

# 候选 IP 池**不再写死**。运行时由同目录的 probe_github_net.py 当场发现：
#   DoH(github.com) → 同 /24 段邻居 → api.github.com/meta 采样的 web CIDR
# 任何 IP 只在当次探测有效，不跨会话、不跨小时复用。
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mapfile -t CANDIDATES < <(python "$SCRIPT_DIR/probe_github_net.py" --candidates 2>/dev/null)
IPS=("${CANDIDATES[@]}")
if [ ${#IPS[@]} -eq 0 ]; then
  echo "NO_CANDIDATES: DoH 未能发现任何候选 IP（系统 DNS 与 DoH 可能同时不可用），请改走代理或检查本机网络"
  exit 6
fi

cd "$REPO_DIR" || { echo "NO_DIR"; exit 2; }

# 阶段1: 用只读 ls-remote 探测，而不是 curl。理由是 ls-remote 走的是 git 真正
# 要用的那条 TLS/HTTP 栈——curl 能通不代表 git 能通（v1 的教训）。
REACHABLE=()
for ip in "${IPS[@]}"; do
  if GIT_TERMINAL_PROMPT=0 timeout 25 git \
        -c http.proxy= \
        -c http.curloptResolve=github.com:443:$ip \
        -c http.sslVerify=false \
        -c http.version=HTTP/1.1 \
        -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $B64" \
        ls-remote origin >/dev/null 2>&1; then
    REACHABLE+=("$ip")
  fi
done
echo "reachable_ips: ${REACHABLE[*]:-none}"

if [ ${#REACHABLE[@]} -eq 0 ]; then
  echo "NO_REACHABLE_IP"
  exit 3
fi

# 阶段2: 对可达 IP 依次推送。凭证走 extraheader 而不拼进 URL，失败时不会把
# token 打回终端（见 references/push.md）。
for ip in "${REACHABLE[@]}"; do
  echo ">>> push via $ip"
  if GIT_TERMINAL_PROMPT=0 timeout 180 git \
        -c http.proxy= \
        -c http.curloptResolve=github.com:443:$ip \
        -c http.sslVerify=false \
        -c http.version=HTTP/1.1 \
        -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $B64" \
        push -u origin "$BRANCH" 2>&1; then
    echo "PUSH_OK via $ip"
    exit 0
  fi
  echo "<<< push via $ip failed"
done
echo "ALL_IP_FAILED"
exit 5

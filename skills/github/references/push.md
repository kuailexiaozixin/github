# 推送通路的选择依据（push 参考）

本篇只回答"为什么这么选"，不给流程。流程与命令在 `github-push/SKILL.md`。

## 为什么推送与核对要用两个域名

`git push` 打的是 `github.com`（智能 HTTP 协议），核对远端提交打的是 `api.github.com`（REST）。两个域名各自解析、各自故障，因此"推不动"不代表"读不到"，反之亦然。这条独立性是本技能把核对放在 api 侧的原因：推送通道拥塞时，读取通道通常还能用，能在几十秒内确认提交到底有没有落库，不必等 `git fetch` 重试。

同一独立性也解释了为什么 `gh` 命令与 `git` 命令的失败要分开看：`gh` 的读写走 `api.github.com`，`git` 走 `github.com`（`gh repo clone` 这类把 git 动作转交给本机 `git` 的子命令除外，它跟着 `github.com` 那条通道）。`gh api` 成功不代表能 push，push 失败也不代表 `gh` 不可用。

## 为什么脚本关闭证书校验

`push_repo.sh` 用 `url.https://<ip>/.insteadOf=https://github.com/` 把域名替换成 IP 发起请求。IP 与证书里的域名不匹配是必然的，因此脚本必须带 `http.sslVerify=false`，代价是这条路径上不验证服务端证书，凭证（Basic 认证里的 token）在中间人场景下可被读取。判断标准：只有当直连与代理两条路都确认不通时才用这条路；能直连就不要用顶 IP。

脚本用的是 `git -c`，配置只活在单条命令里，不落进仓库的 `.git/config`，因此执行后无需清理，也不会污染后续操作。

## 为什么 token 走 extraheader 而不是 URL

脚本用 `http.https://<ip>/.extraheader=AUTHORIZATION: basic <base64>` 携带凭证，而不是把 token 拼进远端 URL。差别在于失败时 git 会回显完整 URL，token 就此进入终端输出与任何日志采集；extraheader 的回显只有 `AUTHORIZATION: basic ...` 这一层，不会带出凭证值。这是脚本层面保证"token 不落屏"的机制，不能改回 URL 内嵌写法。

Basic 用户名固定为 `x-oauth-basic`，配合 `gho_` 前缀的 OAuth token 使用；classic PAT（`ghp_` 前缀）同样接受这个占位用户名。

## 为什么 token 从注册表兜底读

`setx` 写入的是 `HKCU\Environment`，只对新启动的进程生效。已经开着的 shell 里读 `GITHUB_TOKEN` 会读到空，脚本因此加了 `winreg` 兜底：环境变量取不到时直接查注册表。这个兜底解决的是"刚配完 token 就运行脚本"这一个场景；如果注册表里也没有，脚本按 `NO_TOKEN` 退出，不会静默降级成匿名推送。

## 为什么代理要"当场探"而不是写死

同一台机器两天的读数相反：2026-09-25 五个常见端口全部无监听、`github.com` 直连可用；2026-11-10 则 7897 在监听、`curl` 直连三个 host 全是 000，而 `git` 仍"能用"——因为本机 git 全局配置里写着 `http.proxy=http://127.0.0.1:7897`。有没有代理取决于当场开没开客户端、git 有没有单独配过，都不由机器决定。所以第 2 步先探端口、并先查 `git config --global --get http.proxy`，再决定走哪条。

## IP 池怎么维护

`push_repo.sh` 的 `IPS` 数组是推送脚本用的那一份，取值与 `references/access.md` 第一节 github.com 那一行相同——**两处必须同时改**：脚本要独立可跑，不能运行时去解析 markdown；只改一边就会出现「文档说这枚可用、脚本还在试那枚 400」的分叉。api / raw / codeload 各 host 的 IP 只在 access.md 的表里，脚本不涉及。改完按 `github-push/SKILL.md` 第 4 步跑一次，退出码为 0 才算完。

## 相关

流程：`github-push/SKILL.md`。IP 数据与重测：`references/access.md`。

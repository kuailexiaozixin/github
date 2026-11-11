# 推送通路的选择依据（push 参考）

本篇只回答"为什么这么选"，不给流程。流程与命令在 `github-push/SKILL.md`。

## 为什么推送与核对要用两个域名

`git push` 打的是 `github.com`（智能 HTTP 协议），核对远端提交打的是 `api.github.com`（REST）。两个域名各自解析、各自故障，因此"推不动"不代表"读不到"，反之亦然。这条独立性是本技能把核对放在 api 侧的原因：推送通道拥塞时，读取通道通常还能用，能在几十秒内确认提交到底有没有落库，不必等 `git fetch` 重试。

同一独立性也解释了为什么 `gh` 命令与 `git` 命令的失败要分开看：`gh` 的读写走 `api.github.com`，`git` 走 `github.com`（`gh repo clone` 这类把 git 动作转交给本机 `git` 的子命令除外，它跟着 `github.com` 那条通道）。`gh api` 成功不代表能 push，push 失败也不代表 `gh` 不可用。

## 顶 IP 为什么用 curloptResolve 而不是 insteadOf

**这一节推翻过一版结论，记下过程，免得再改回去。**

早期版本用 `url.https://<ip>/.insteadOf=https://github.com/` 把域名替换成 IP。2026-11-10 实测这条路**六个 IP 全部失败**：

```
fatal: unable to access 'https://140.82.113.4/kuailexiaozixin/github.git/':
  Failed to connect to github.com:443 after 21301 ms
```

注意报错里的主机名是 `github.com` 而不是那个 IP——`insteadOf` 只改 URL 字符串，git 仍要对**原域名**解析一次，DNS 被阻断时连接在拨号前就失败。同一秒用 `curl --resolve` 打同一个 IP 却回 200，所以问题不在 IP，在这条写法本身。

换成 `http.curloptResolve=github.com:443:<ip>`（git ≥ 2.55）之后，**六个 IP 全部成功**返回同一个 HEAD。区别是它在 libcurl 的连接层直接给出「域名→IP」映射，不经过 git 自己的解析。

代价仍是必须 `http.sslVerify=false`：IP 与证书里的域名不匹配是必然的，这条路径上不验证服务端证书，凭证在中间人场景下可被读取。判断标准没变——只有直连与代理都确认不通才用它，能直连就不要顶 IP。

脚本用的是 `git -c`，配置只活在单条命令里，不落进仓库的 `.git/config`，执行后无需清理。

## 为什么 token 走 extraheader 而不是 URL

脚本用 `http.https://<ip>/.extraheader=AUTHORIZATION: basic <base64>` 携带凭证，而不是把 token 拼进远端 URL。差别在于失败时 git 会回显完整 URL，token 就此进入终端输出与任何日志采集；extraheader 的回显只有 `AUTHORIZATION: basic ...` 这一层，不会带出凭证值。这是脚本层面保证"token 不落屏"的机制，不能改回 URL 内嵌写法。

Basic 用户名固定为 `x-oauth-basic`，配合 `gho_` 前缀的 OAuth token 使用；classic PAT（`ghp_` 前缀）同样接受这个占位用户名。

## 为什么代理端口不写死、也不维护「代理池」

固定端口的写法（`127.0.0.1:7897`）在这台机器上一天之内就被证伪两次：2026-09-25 五个常见端口全关；2026-11-10 上午 7897 在监听，下午代理客户端一关又变成 CLOSED。端口能不能用取决于「此刻本机有没有开代理客户端、它监听哪个口」，这是**运行时状态**，写进文档只能写「怎么探」。

也考虑过维护一个端口池轮询——不成立，理由是代理不是 GitHub 提供的东西：

- 代理端口由本机的代理客户端决定（Clash / v2ray / 系统代理各不相同，用户随时会改），**不是一组「GitHub 的可用入口」**，扫不到就说明这台机器此刻没有代理，换多少端口都扫不出来。
- 无脑扫全网段既慢又会误撞到本机不相干的服务（数据库、调试端口），拿它们的响应当「代理可用」判据。

所以做法是：给一组**常见候选端口**做 150ms 级快探（覆盖绝大多数客户端的默认口），探到就用、探不到就走下一条通路。这不是「固定的一个值」，也不是「无限池」，而是「有限候选 + 当场判定」。

**真正需要遍历选择的是 IP 池，不是端口。** GitHub 的 `github.com` / `api.github.com` 前端有多组 IP，每一组的可达性随时在变（2026-11-10 实测六枚 github.com 前端里五枚 200、一枚 000），这才是该逐个探测并按结果挑一个用的地方——`push_repo.sh` 探的就是这个。

## 为什么 token 从注册表兜底读

`setx` 写入的是 `HKCU\Environment`，只对新启动的进程生效。已经开着的 shell 里读 `GITHUB_TOKEN` 会读到空，脚本因此加了 `winreg` 兜底：环境变量取不到时直接查注册表。这个兜底解决的是"刚配完 token 就运行脚本"这一个场景；如果注册表里也没有，脚本按 `NO_TOKEN` 退出，不会静默降级成匿名推送。

## 为什么代理要"当场探"而不是写死

同一台机器两天的读数相反：2026-09-25 五个常见端口全部无监听、`github.com` 直连可用；2026-11-10 则 7897 在监听、`curl` 直连三个 host 全是 000，而 `git` 仍"能用"——因为本机 git 全局配置里写着 `http.proxy=http://127.0.0.1:7897`。有没有代理取决于当场开没开客户端、git 有没有单独配过，都不由机器决定。所以第 2 步先探端口、并先查 `git config --global --get http.proxy`，再决定走哪条。

## IP 池怎么维护

`push_repo.sh` 的 `IPS` 数组是推送脚本用的那一份，取值与 `references/access.md` 第一节 github.com 那一行相同——**两处必须同时改**：脚本要独立可跑，不能运行时去解析 markdown；只改一边就会出现「文档说这枚可用、脚本还在试那枚 400」的分叉。api / raw / codeload 各 host 的 IP 只在 access.md 的表里，脚本不涉及。改完按 `github-push/SKILL.md` 第 4 步跑一次，退出码为 0 才算完。

## 相关

流程：`github-push/SKILL.md`。IP 数据与重测：`references/access.md`。

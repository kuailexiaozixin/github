---
name: github
description: "GitHub 全场景技能（统一入口，含 9 个子技能）。覆盖国内网络下访问与克隆、推送与认证、仓库运维主线、分支库（fork）的建与跟、Projects 看板、Codespaces 云端环境、开源项目搜索筛选、agent 技能管理、gh 自身的登录配置与扩展、浏览器打不开 GitHub 时的系统代理/DNS/hosts 诊断与修复。触发关键词：访问 GitHub、克隆仓库、git clone 慢/失败、下载 GitHub 文件、GitHub 网络不通、push/推送、git push 失败、多IP推送、GitHub 认证、gh auth、gh 命令、GitHub 维护、处理 issue、分诊、管理 PR、合并 PR、CI 失败、发布 release、上传产物、安全告警、Dependabot、ruleset、fork、分支库、上游同步、gh repo sync、看板、Project 排期、codespace、云端开发环境、搜开源项目、开源项目推荐、github搜索、/github-search、gh skill、技能管理、技能市场、MCP 市场、MCP 连接器、安装技能、安装 MCP、浏览器打不开 GitHub、无法访问 GitHub 网站、恢复浏览器访问、修复访问。"
---

# GitHub 全场景技能

围绕 GitHub 的任务入口。本文件只做一件事：把请求送到正确的子技能，并说明这份技能集合是在什么环境前提下实测出来的。命令、参数、出口判据全部在子技能里，本文件不含命令。

## 前置准备（只列材料）

- 一份 `gh` 可执行文件的路径（本机 `gh` 不在 PATH，取法见 `github-push/SKILL.md` 第 0 步）
- 一份凭证（三种来源与各自权限见下面第 3 步）
- 一句话任务描述，或一个 issue / PR / 仓库链接

## 1 判定任务落在哪一层

**输入**：用户的请求原文。

**动作**：按请求要产出的东西选一个子技能，**九选一分派，命中即停**，不要同时打开两份：

- 要**拿**代码、仓库、单个文件，或反映访问慢/失败，或**修**"浏览器打不开 GitHub"（系统代理/DNS/hosts 配置层）：`github-access/SKILL.md`
- 要**交**代码（push、打 tag、核对远端收到）：`github-push/SKILL.md`
- 要**管**一个已有仓库（issue、PR、CI、release、仓库设置、安全告警）：`github-ops/SKILL.md`
- 要**在别人的仓库上做长期改动**（建 fork、跟上游同步、改动放在自己的分支上）：`github-fork/SKILL.md`
- 要**排期**、立项、看板上把工作项推进到收口：`github-project/SKILL.md`
- 要**云端环境**（codespace 建/连/端口/账单）：`github-codespace/SKILL.md`
- 要**找**项目（"有没有现成的开源 xx"）：`github-search/SKILL.md`
- 要**装配 agent 技能**（安装/发布/更新 skills）：`github-skill/SKILL.md`
- 要动 **gh 自身**（登录、补 scope、配 git 凭证助手、别名、扩展、补全）与**账号级对象**（gist、SSH/GPG 公钥）：`github-cli/SKILL.md`

技能仓库的发布不走推送主线，一律用 `gh skill publish`，对应 `github-skill`。

子技能之间**允许命令重叠**，这是有意的设计：每份子技能都要能独立读完一条主线，不靠跳转才成立。所以同一条命令会在两三份文件里出现（例如 `gh repo fork`/`gh repo sync` 同时在 github-ops 的仓库生命周期与 github-fork 的分支库跟进里）。重叠处每份都写自己的出口判据，不写"权威在哪一份"，改命令时按校验脚本一次扫全包，不依赖单点引用。

**产出**：一个子技能文件路径，以及该子技能里要进入的步骤号。

**出口**：打开该文件，从它的第 0 或第 1 步开始执行。在本文件里找不到答案不是问题，答案本就不在这里；判不出属于哪一层时，问用户一句要拿还是交、是要结果还是要环境，再回到本步。

## 2 跨层任务按数据依赖串联

**输入**：第 1 步判出的多个意图。

**动作**：一个请求可能横跨多个子技能，顺序由数据依赖决定，不由偏好决定。常见的四条链：拉到本地改完再交（access 取码、push 交付、ops 发 release）；找到候选再验（search 出榜、access 读文件、search 第 5 步核质量）；建完仓库就挂看板（ops 建库、project 建字段灌卡）；在别人的仓库上长期改动（fork 建库并纠正默认远端、fork 第 4 步跟上游、本地改完由 push 交付、要提回上游转 ops 第 3 步）。前一步的出口判据满足才进下一步，不满足就停在原地解决，不要跳到下游步骤。

**产出**：本次实际要跑的几个子技能及各自步骤范围。

**出口**：每条链的终点子技能自己的收口步通过。

## 3 环境事实（本技能全部命令在这些前提下实测）

以下都是本机实测值，不是通用设定：标 2026-09-25 的是当天读数，标 2026-11-10 的是复测读数；两者不一致时以 2026-11-10 为准。换网、换机、升级 gh 之后，先复测对应通路再照文档执行。

- `gh` 版本 2.101.0 (2026-09-15)。全部子技能里的参数、`--json` 字段名、退出码都取自这一版本机 `--help` 原文。升级后必须重跑受影响段落的 help 对照。本机没有 winget，`gh` 也没有 `upgrade` 子命令——换版本只能下官方 release 的 zip 解出 `bin/gh.exe`，两份安装一起换。
- 两份 gh 安装（`AppData\Local\Programs\gh\bin` 与 `D:\WPS*\gh\bin`）是**彼此独立的拷贝，不是链接**，换版本必须两份一起换。PATH 分两地说：2026-09-25 两条都无输出；**2026-11-10 复测时用户 PATH 的最后一项已含 `C:\Users\<用户名>\AppData\Local\Programs\gh\bin`（写于当日 07:04），新起的进程 `where gh` 能解析到**，但 07:04 之前已启动的终端（含多数 IDE 内置终端）仍是旧环境，裸敲 `gh` 照样报「无法识别」。所以文档里的 `gh` 仍一律先绑定绝对路径——不是因为它不在 PATH，而是因为**无法从当前 shell 判断它继承的是哪一代 PATH**；绑定之后两条分支都对。
- 凭证三处：环境变量 `GITHUB_TOKEN` 是 gh 的 OAuth token（前缀 `gho_`，scopes 为 `gist, read:org, repo, workflow`，**不含 `project`**，看板操作会失败，需按 `github-cli` 补 scope）；系统钥匙串同一账号的副本；技能根目录 `github/.env` 里一枚只读 classic PAT（前缀 `ghp_`，读公开仓库与提升 API 额度用）。token 值不打印、不落工作区。
- **凭证能力边界（2026-11-10 复测，任何写操作前必看）**：`.env` 那枚 `ghp_` 是**零 scope** 的 classic PAT，只能读公开仓库，禁止用于建仓、推送、发 release 或任何写操作；把它 export 成 `GITHUB_TOKEN` 后 `GET /user` 照样返回 200，但 `X-OAuth-Scopes` 为空，写端点一律回 404 `Not Found`（GitHub 对无权限资源统一回 404，不是网络故障）。写操作一律用含 `repo` 的环境变量凭证。`X-OAuth-Scopes` 为空**不能**据此判定「细粒度 PAT」：零 scope 的 classic PAT 同样为空；判别凭证类型只看前缀（`ghp_` classic / `github_pat_` 细粒度 / `gho_` OAuth）或 `github-push` 第 1 步的 scope 核对。细粒度 PAT（`github_pat_`）也能建仓，但需 `Administration`(write) 或 `Repository creation`(write) 之一，见 `github-ops` 建库条目。
- 额度实测：匿名 Search 10 次/分钟、Core 60 次/小时；带任一 token 为 Search 30 次/分钟、Core 5000 次/小时；代码域检索匿名直接 401，必须带 token。
- **直连与代理要分开记，不要合成一句「网络可用」。** 2026-11-10 复测：`curl` 直连 `github.com`／`api.github.com`／`codeload.github.com` 三个都 000（各挂 5 秒超时），只有 `raw.githubusercontent.com` 回 301；同一时刻 `git ls-remote https://github.com/cli/cli HEAD` **直连可用**、`gh api user` **直连不通**、两者各自挂上 `http://127.0.0.1:7897` 之后都通。成因是本机 git 全局配置写死了 `http.proxy=http://127.0.0.1:7897`（`git config --global --get http.proxy` 可查），git 因此在走代理、curl 与 gh 不走——**「git 通但 gh 不通」不代表网络没问题**，先看这条配置。五个候选端口当日只有 7897 在监听（7890／1080／1081／10808／10809 全 CLOSED）。
- 2026-09-25 那天 `github.com` 与 `api.github.com` 直连都可用、五个代理端口都没监听。两组读数不矛盾，是两天网络状态不同：代理开没开、出口通不通都随当天变，所以每次任务都要按当场探测结果选通路，不要照抄前一天。

## 4 开工前的连通性自检（30 秒，任何 GitHub 任务都先跑）

**不要假定「上次能连所以这次也能」。** 这台机器一天之内出现过：直连通、直连通而 `gh` 不通、只有代理通、直连与代理都不通但顶 IP 通、以及代理客户端关掉后 `git` 撞死端口。任何写死的通路都会在某一刻失效。

```bash
# 三行分别量：git 直连 / gh 直连 / 本机代理端口
GIT_TERMINAL_PROMPT=0 timeout 15 git -c http.proxy= ls-remote https://github.com/cli/cli HEAD   # 有 SHA = 直连通
timeout 20 "$USERPROFILE/AppData/Local/Programs/gh/bin/gh.exe" api user --jq .login              # 有账号名 = gh 通
PYTHONIOENCODING=utf-8 python -c "
import socket
for p in (7897,7890,7896,1080,10808,10809,8080,8888):
    s=socket.socket(); s.settimeout(0.15)
    print(p,'OPEN' if s.connect_ex(('127.0.0.1',p))==0 else 'CLOSED'); s.close()"
```

按结果分派，**三条互不替代**：

| git 直连 | gh | 代理 | 含义与做法 |
|---|---|---|---|
| 通 | 通 | — | 最省事，直接干活 |
| 通 | 不通 | — | `gh` 那条要挂代理（`gh` 不读 git 的 `http.proxy`），见 `github-push` 第 2 步 |
| 不通 | — | OPEN | 挂代理做；`git` 必须加 `-c http.proxy=`，否则仍会去撞 `.gitconfig` 里那条 |
| 不通 | 不通 | CLOSED | 走顶 IP：`git -c http.curloptResolve=...`；`gh` 的任务改用 curl 顶 IP 取同端点 |
| 全不通 | 全不通 | CLOSED | 三条通路各试两轮后判定本机网络不可达，把三份失败原文交用户 |

细节与 IP 取值见 `github-push` 第 2 步、`references/access.md` 第一/三/四节。浏览器打不开而命令行能通（或都通不了）、怀疑系统代理/DNS 配置层问题时，走 `github-access` 第 7 步诊断与修复。

## 红线

- 破坏性动作（force push、删远端分支、删仓库、删已发布 release、`gh repo sync --force`）执行前须向用户确认，说明会丢什么。
- 不用 `--no-verify` 绕过钩子，不在智能体会话里执行 `gh auth token` 或 `gh auth status -t`。
- 凭证值不打印、不写入仓库或工作区文件、不在子任务之间传阅。

## 参考文件的职责

`references/access.md` 是唯一一份网络数据（按 host 的 IP 表、镜像/代理状态、重测脚本）。`references/ops.md`、`references/push.md`、`references/search.md` 分别是运维、推送、搜索三条主线的论证来源，只回答"阈值与取舍为什么这样定"，命令一律在对应子技能正文里。

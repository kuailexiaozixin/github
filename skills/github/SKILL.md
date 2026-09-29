---
name: github
description: "GitHub 全场景技能（统一入口，含 9 个子技能）。覆盖国内网络下访问与克隆、推送与认证、仓库运维主线、分支库（fork）的建与跟、Projects 看板、Codespaces 云端环境、开源项目搜索筛选、agent 技能管理、gh 自身的登录配置与扩展。触发关键词：访问 GitHub、克隆仓库、git clone 慢/失败、下载 GitHub 文件、GitHub 网络不通、push/推送、git push 失败、多IP推送、GitHub 认证、gh auth、gh 命令、GitHub 维护、处理 issue、分诊、管理 PR、合并 PR、CI 失败、发布 release、上传产物、安全告警、Dependabot、ruleset、fork、分支库、上游同步、gh repo sync、看板、Project 排期、codespace、云端开发环境、搜开源项目、开源项目推荐、github搜索、/github-search、gh skill、技能管理。"
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

- 要**拿**代码、仓库、单个文件，或反映访问慢/失败：`github-access/SKILL.md`
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

以下都是 2026-09-25 在本机的实测值，不是通用设定。换网、换机、升级 gh 之后，先复测对应通路再照文档执行。

- `gh` 版本 2.101.0 (2026-09-15)。全部子技能里的参数、`--json` 字段名、退出码都取自这一版本机 `--help` 原文。2026-09-25 从 2.97.0 升上来，升级前后各跑一遍命令树与参数面差分，结论是**纯新增**：子命令零增减、`JSON FIELDS` 零变化，只有 9 条命令多了参数（`--attach` 见于 `issue/pr` 的 `create|edit|comment`，`--worktree` 见于 `pr checkout` 与 `issue develop`，`--search-type` 见于 `search issues`）。升级途径：官方 `gh_2.101.0_windows_amd64.zip`，SHA-256 与 `gh_2.101.0_checksums.txt` 逐字节比过一致（`bc6c8143…192794`），解出 `bin/gh.exe` 覆盖两份安装位。本机没有 winget，`gh upgrade` 这条命令在 gh 里也不存在，别找。
- 两份 gh 安装（`AppData\Local\Programs\gh\bin` 与 `D:\WPS灵犀过程文件\gh\bin`）是**彼此独立的拷贝，不是链接**，换版本必须两份一起换；`where gh` 与 `command -v gh` 均无输出，**都不在 PATH**，文档里的 `gh` 一律要先绑定绝对路径。
- 凭证三处：环境变量 `GITHUB_TOKEN` 是 gh 的 OAuth token（前缀 `gho_`，scopes 为 `gist, read:org, repo, workflow`，**不含 `project`**，看板操作会失败，需按 `github-cli` 补 scope）；系统钥匙串同一账号的副本；技能根目录 `github/.env` 里一枚只读 classic PAT（前缀 `ghp_`，读公开仓库与提升 API 额度用）。token 值不打印、不落工作区。
- 额度实测：匿名 Search 10 次/分钟、Core 60 次/小时；带任一 token 为 Search 30 次/分钟、Core 5000 次/小时；代码域检索匿名直接 401，必须带 token。
- 网络：`github.com` 与 `api.github.com` 当日直连可用；五个常见本地代理端口当日**无监听**，代理按"探测通过才用"处理。IP 池、镜像可用性、重测步骤统一记在 `references/access.md`，其它文档只指过去。

## 红线

- 破坏性动作（force push、删远端分支、删仓库、删已发布 release、`gh repo sync --force`）执行前须向用户确认，说明会丢什么。
- 不用 `--no-verify` 绕过钩子，不在智能体会话里执行 `gh auth token` 或 `gh auth status -t`。
- 凭证值不打印、不写入仓库或工作区文件、不在子任务之间传阅。

## 参考文件的职责

`references/access.md` 是唯一一份网络数据（按 host 的 IP 表、镜像/代理状态、重测脚本）。`references/ops.md`、`references/push.md`、`references/search.md` 分别是运维、推送、搜索三条主线的论证来源，只回答"阈值与取舍为什么这样定"，命令一律在对应子技能正文里。

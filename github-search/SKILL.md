---
name: github-search
description: "GitHub 开源项目搜索与筛选子技能——按需求把 GitHub 上可用的开源项目找出来并给出结构化推荐。覆盖需求收敛门控、gh search 五条检索路（repos/code/issues/prs/commits）的参数与输出字段、排除限定词的传参写法、Search API 兜底、硬过滤、质量精炼、报告交付与迭代。触发关键词：搜开源项目、开源项目推荐、github搜索、/github-search、帮我找开源项目、找 GitHub 仓库、有没有现成的库、搜一下 star 数。"
---

# GitHub 开源项目搜索与筛选（search）

拿着一句需求，从 GitHub 上找出可信的开源项目并给出取舍理由。难点不是命令，是两处：一是需求没收口就开搜，结果集必然要重来；二是 `gh search` 的排除写法在命令行上会被当成参数，实测直接写 `-label:bug` 会报 `Invalid search query ""`，加 `--` 之后还必须把参数写在 `--` 前面，否则参数会被吞进查询词。

本技能只负责"找"。找到之后要拉下来看代码，走 `github-access`。

## 前置准备（只列材料）

- 一份可用凭证，三选一，优先级见第 0 步
- 一句话需求原文，以及用户对形态、栈、规模的倾向（第 1 步要问）
- 若要读候选仓库的 README 与提交，按 `github-access` 的通路取，本技能不克隆仓库

## 0 取凭证，确认额度

**输入**：当前会话环境。

**动作**：额度决定能不能搜代码、能搜多少次，先量再搜。三条凭证来源按下面顺序取，**先命中先用**：

1. 环境变量 `GITHUB_TOKEN`（2026-09-25 实测本机有值，`gh auth status --json hosts` 显示 scopes 为 `gist, read:org, repo, workflow`）
2. 本技能根目录的 `github/.env` 里那一行 `GITHUB_TOKEN`（注意位置在 `github/` 目录、与母 `SKILL.md` 同级，不在 `github-search/` 下）。这份是 classic PAT，前缀 `ghp_`、长度 40、**scope 为空**（2026-11-10 用 `X-OAuth-Scopes` 头核对），实测读公开仓库够用——**但也只够读**：拿它建仓、推送、发 release 一律回 404 `Not Found`。本条的顺序只适用于**检索**这一条主线；任何写操作回 `github-push` 第 1 步取含 `repo` 的凭证，不要沿用这里的"先命中先用"。
3. 都没有：匿名模式

取到之后用一条请求核对真实额度，不要凭记忆：

```bash
"$GH" api rate_limit --jq '{search:.resources.search,core:.resources.core}'
```

2026-09-25 实测三档数字：匿名 `search` 10 次/分钟、`core` 60 次/小时；带任一 token `search` 30 次/分钟、`core` 5000 次/小时；匿名的 `code_search` 走 60 次/小时档，因此代码检索必须带 token。

**产出**：一个已确认额度档位的会话，以及 `$GH`（路径见 `github-push` 第 0 步，本机 `gh` 不在 PATH）。

**出口**：`rate_limit` 返回的 `remaining` 大于本次计划发出的请求数。低于第 2 步估算的 query 组数时，先减量再搜，不要中途撞 403 才停。

token 值不打印、不回显，只报 scopes 与剩余次数。

## 1 需求收敛（硬性门控）

**输入**：用户的原始描述。

**动作**：无论描述多清晰都要走完本步并取得确认，用户说"直接搜就行"时同样先输出摘要。最少确认五项：主题、数量（Top N）、最低 stars（默认 100）、排序模式（相关性优先或星标优先，默认相关性）、目标形态（可直接用的产品 / 可二次开发的框架 / 资料清单）。建议补充：偏好技术栈、使用场景、排除项（教程、归档、纯论文复现）、部署偏好。

**产出**：固定格式的摘要，供用户确认。

```text
核心诉求：
- 主题：xxx
- 数量：Top N
- 最低 stars：>= 100
- 排序模式：相关性优先 / 星标优先
- 目标形态：xxx
- 偏好：xxx（可空）
- 排除：xxx（可空）
```

**出口**：用户确认这份摘要，或按用户改后的值重出一版。未确认不进入第 2 步。

## 2 拆检索词

**输入**：第 1 步确认后的摘要。

**动作**：写 5 到 10 组 query，每组由核心词、同义词、场景词（coding / mcp / tool / awesome）、技术词（agent / sdk / framework）拼成。排除条件不写进 query 的负例，留到第 4 步过滤——负例走命令行要额外转义，容易出错。

估算请求数：一组 query 一次 `gh search repos`，5 到 10 组即 5 到 10 次，再加候选池精读时的 `gh repo view`，总量对照第 0 步的 `remaining`。

**产出**：query 列表，每条标出要检索的路（见第 3 步）。

**出口**：条目数与额度匹配，进入检索。

## 3 检索

**输入**：第 2 步的 query 列表。

**动作**：`gh search` 只有 `repos`、`code`、`issues`、`prs`、`commits` 五条子命令，按要找的对象**五选一**，一轮里通常只会用到 `repos` 与 `code`。找仓库本身一律走 `repos`。

```bash
# 路线一：找仓库
"$GH" search repos "ai agent" --language python --stars ">=500" --archived=false \
  --sort stars --order desc --limit 50 \
  --json fullName,stargazersCount,pushedAt,license,language,description,url,isArchived

# 限定词直接作为查询词传，与参数混用等价
"$GH" search repos topic:github 'stars:>5000'

# 路线二：搜代码内容（需 token，帮助文档明确说这是旧版引擎，结果可能与网页不一致、不支持正则）
"$GH" search code panic --repo cli/cli --limit 20 --json path,url,repository

# 路线三/四：搜 issue 与 PR（判断一个项目是否活跃时用）
"$GH" search issues --owner github --archived=false --state open --limit 20 --json url,title
"$GH" search issues "登录页打不开" --search-type semantic     # 2.101.0 起：{lexical|semantic|hybrid}，默认 lexical
"$GH" search prs --repo cli/cli --merged --limit 20 --json url,updatedAt

# 路线五：搜提交（必须有文字查询词）
"$GH" search commits readme --repo cli/cli --limit 20 --json sha,url
```

三条实测出来的传参规则，违反任何一条都会静默改变结果：

- 排除某个限定词要写成 `-- <限定词>`，且**所有参数放在 `--` 之前**：`"$GH" search repos --limit 2 --json fullName -- -topic:linux` 正常返回 JSON；把 `--limit 2` 挪到 `--` 之后，参数被当成查询词的一部分，限制失效、返回默认 30 条。裸写 `-topic:linux`（不加 `--`）报 `Invalid search query ""`。
- `gh search commits` 只给限定词不给文字会报错：`Search text is required when searching commits`。
- `--order` 只在同时给了 `--sort` 时生效，`--sort` 的取值按子命令不同：`repos` 为 `forks|help-wanted-issues|stars|updated`（默认 `best-match`），给错值 gh 会直接打印合法集合。`--limit` 默认 30。

各路线 `--json` 可选字段（取自本地 gh 2.101.0 帮助原文）：

| 路线 | 可选字段 |
|---|---|
| repos | createdAt, defaultBranch, description, forksCount, fullName, hasDownloads, hasIssues, hasPages, hasProjects, hasWiki, homepage, id, isArchived, isDisabled, isFork, isPrivate, language, license, name, openIssuesCount, owner, pushedAt, size, stargazersCount, updatedAt, url, visibility, watchersCount |
| code | path, repository, sha, textMatches, url |
| issues | assignees, author, authorAssociation, body, closedAt, commentsCount, createdAt, id, isLocked, isPullRequest, labels, number, repository, state, title, updatedAt, url |
| prs | 同 issues，另有 isDraft |
| commits | author, commit, committer, id, parents, repository, sha, url |

**产出**：每组 query 的原始结果，30 到 50 条一组。

**出口**：拿到至少一组非空结果。全为空时回第 2 步换词，不要靠放宽 stars 阈值来凑数。

## 4 合并候选池并硬过滤

**输入**：第 3 步的原始结果。

**动作**：合并所有路线的结果，按 `owner/repo` 去重，记录检索时间与本次消耗的额度。然后套默认硬过滤：`stargazersCount >= 100`、`isArchived == false`、公开仓库；第 1 步确认过的语言与排除项在这一步一并套。用户明确要"包含归档项目"时才放开第二条。

**产出**：候选池，每行含 `owner/repo`、stars、description、url、archived、language、pushedAt、license（主题词不在检索输出里，第 5 步逐个补，见下）。

**出口**：候选池规模大于 Top N。小于等于 Top N 说明过滤过头或词太窄，回第 2 步补词，不要直接交付不足的清单。

## 5 质量精炼

**输入**：候选池。

**动作**：对进入前 2N 的候选逐个核，2N 是给第 6 步留剔除余量；不逐个核就交不出理由。

```bash
"$GH" repo view <owner/repo> --json name,description,repositoryTopics,stargazerCount,pushedAt,isArchived,licenseInfo,primaryLanguage,latestRelease
"$GH" api "repos/<owner>/<repo>/contributors?per_page=5" --jq '[.[].login]'      # 参与者是否只有一人
"$GH" api "repos/<owner>/<repo>" --jq '{open:.open_issues_count,pushed:.pushed_at,archived:.archived,lic:.license.spdx_id}'
"$GH" issue list --repo <owner/repo> --state open --limit 5 --json number,title  # issue 是否有人回
```

核对五项：文档完整度（有无 README 之外的使用文档）、维护活跃度（`pushed_at` 距今多久、issue 响应）、star 与活跃是否背离（高 star 多年不更新要标注）、许可证（`gh search repos --json license` 拿到的是对象 `{key,name,url}`，`gh repo view --json licenseInfo` 拿到 `{key,name,nickname}`，要 SPDX 串走 `gh api <repo> --jq .license.spdx_id`）、依赖与生态（有无 release、有无 CI）。

两个字段名会直接报错：`gh search repos --json` 里没有 `topics`（实测 `Unknown JSON field: "topics"`），主题词改用 `gh repo view <owner/repo> --json repositoryTopics`，返回 `[{name:"cli"},...]`；`gh repo view --json` 里也没有 `license`，那份字段名叫 `licenseInfo`。

排除：README 缺失或只有安装说明、一年以上无提交、纯教程无代码、star 增长与提交活动明显不匹配。

给每个入选项标"仓库归属类型"（通用框架层、应用产品层、记忆层/上下文基础设施、MCP 服务层、目录清单层、垂直场景方案层、方法论/研究层七类），重排权重与深读最低要求见 `references/search.md` 第 5 到第 7 步。

**产出**：排序后的精炼清单，每项附一句契合第 1 步目标形态的理由。

**出口**：条目数等于 Top N，或明确说明"合格项只有 M 个"并列出被排除的原因。

## 6 交付与迭代

**输入**：第 5 步的精炼清单。

**产出**：Markdown 报告，格式固定。

```text
# <主题>推荐（Top N）

## 1. <owner/repo>
- 一句话定位
- stars / 语言 / 最近更新 / 许可证
- 推荐理由（对应第 1 步的目标形态与偏好）
- 链接：https://github.com/<owner>/<repo>
- 注意事项（归档风险、单人维护、许可证限制等）
```

按契合度排序，不按 star 排序；第 1 步选了"星标优先"才按 star 排，两种排序在报告开头写明是哪一种。上面是单条推荐的最低格式；完整报告的六段结构（需求摘要、检索词清单、筛选与重排规则、召回/去重/过滤后的数量、Top N 表格、结论与下一步）与表格列定义见 `references/search.md` 第 8 步。综合排序权重（相关性 35%、场景适用性 30%、活跃度 15%、工程成熟度 15%、stars 5%）、仓库归属类型字典（通用框架层到方法论研究层七类）、以及"是什么 + 为什么推荐"两段式的介绍写法，都取 `references/search.md` 的既有约定，不要每次重定一套。

**出口**：交付后问一句是否按新参数重搜、深挖其中某几个、或换主题。用户没继续就收口，不要把同一批候选换个说法再交一遍。

## 拿不到结果时

- `gh api` 连不上：多半是本机 `gh` 走了 `api.github.com` 的系统 DNS，按 `references/access.md` 的按 host IP 表探测可用 IP，再用 curl 顶 IP 发同一条请求。
- 返回 403 且 `remaining` 为 0：撞额度，等 `reset` 时间或换凭证，不要重试。
- 需要 `gh search` 没有的对象（用户、话题、组织仓库列表）：走 Search API 端点，实测 `"$GH" api "search/users?q=monalisa"` 与 `"$GH" api "search/topics?q=mcp"` 均可用（2026-09-25）。
- 需要一次拿回全部命中并自己排序：同一条 query 改走 `https://api.github.com/search/repositories?q=...&sort=stars&order=desc&per_page=50`，`q` 里的限定词与 `gh` 参数等价（`in:name,description`、`stars:>=500`、`language:python`、`archived:false`、`fork:false`、`pushed:>2026-01-01`、`topic:xxx`、`license:mit`）。

## 相关

`github-access` 负责把选中的仓库拉到本地；`github-ops` 负责选定之后建 issue、发 PR。

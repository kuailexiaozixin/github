---
name: github-ops
description: "GitHub 仓库运维子技能——用 gh 跑完一次仓库维护任务：定位仓库、分诊 issue、处理 PR、排障 CI、发 release、校准仓库设置与安全告警、收口。覆盖 issue/pr/run/workflow/release/repo/label/discussion/secret/variable/ruleset/attestation/agent-task/cache/api/status/browse/org 全部子命令；gist 与 SSH/GPG 公钥属账号级对象，在 github-cli 第 5 步。触发关键词：gh 命令、GitHub 维护、处理 issue、分诊、管理 PR、审查 PR、合并 PR、CI 失败、重跑工作流、发布 release、上传产物、GitHub 安全告警、Dependabot、secret scanning、ruleset、规则集、attestation、制品证明、gh api、fork 仓库、归档仓库。"
---

# GitHub 仓库运维（ops）

一次仓库维护任务的主线依次是定位仓库、分诊 issue、处理 PR、排 CI、发 release、校准仓库设置、处理安全告警与配置项，最后收口。逐步往下走，每步给出出口再进下一步。

命令形态逐条取自本机 gh 2.101.0 的 `<命令> --help`。看板（`gh project`）与云端环境（`gh codespace`）各自独立成线，见 github-project、github-codespace；gh 自身的登录、配置、别名、扩展见 github-cli；找代码找仓库见 github-search。

## 前置准备（只列材料）

- 目标仓库的 `owner/repo`，以及自己在其中的角色（只读 / 写 / 管理）——决定后面哪些命令会 403
- 已登录的 gh，token 至少含 `repo`；要动看板补 `project`，要建/改工作流文件补 `workflow`（补法见 github-cli 第 4 步的 `gh auth refresh`）
- 本地对应的 git 仓库目录（`gh pr checkout`、`gh repo sync` 这类命令要在仓库目录里跑，或显式带 `-R`）
- 若这一步要发布：构建产物所在目录，以及本次版本号

## 1 定位仓库与自己的位置

**输入**：`owner/repo`，或手头一个 issue/PR 链接。

```bash
gh repo view <owner>/<repo> --json name,defaultBranchRef,visibility,isArchived,parent
gh repo set-default <owner>/<repo>        # 在当前 git 目录记住默认仓库，后面可省 -R
gh org list                               # 确认组织登录名（gh 只有 list，没有 org view）
gh status                                 # 我名下待办的 issue/PR/评审请求/提及，跨仓库汇总
```

**动作**：`set-default` 之后，本目录内的 `gh issue/pr/run/release` 都默认打到这个仓库；跨仓库操作一律显式加 `-R <owner>/<repo>`。`gh status` 的两个可选项是 `-e <owner/repo>` 排除仓库、`-o <org>` 只看某组织。

**产出**：默认分支名、可见性、是否已归档、（若是分支库）上游仓库。

**出口**：`gh repo view` 无报错即定位成功。`isArchived` 为 true 时仓库只读，issue/PR 写操作都会失败——先按第 6 步判断是否要 `unarchive`，不要在这上面反复试。

## 2 分诊 issue

**输入**：待分诊的 issue 编号或列表。先约定标签体系，没有就建：

```bash
gh label list --repo <owner>/<repo>
gh label create bug --description "缺陷" --color D73A4A --repo <owner>/<repo>
gh label create bug --color 0E8A16 --force          # 已存在同名标签时用 --force 改颜色描述，不报错
gh label edit bug --color FF0000                              # 只改颜色
gh label edit bug --name big-bug --description "严重缺陷"      # 改名与改说明，改名不影响已贴在 issue 上的关联
gh label delete bug --yes                                     # 删标签会同时从所有 issue 上摘掉该标签，先确认没有查询依赖它
gh label clone <source-owner>/<source-repo> --repo <owner>/<repo>   # 把别家的标签体系搬来
gh label clone <source-owner>/<source-repo> --force                  # 同名标签以源仓库为准
```

标签颜色是 6 位十六进制（不带 `#`）。`label clone` 只增不删：源仓库没有的标签不会被清掉。

**动作**：按读正文、查重、打标签、回复、建关系这个顺序过一遍。

```bash
gh issue list --repo <owner>/<repo> --state open --limit 50
gh issue list --search "关键词" --state all --limit 20       # 查重；--state all 才含已关闭
gh issue view <number> --json labels,assignees,state,comments
gh issue edit <number> --add-label "bug,high-priority" --add-assignee @me
gh issue edit <number> --remove-label "needs-repro" --type bug --parent <主issue>
gh issue comment <number> --body "请补充复现步骤与版本"
gh issue comment <number> --edit-last --body "更正上面一句" --yes   # 改自己最后一条评论
gh issue create --title "..." --body-file report.md --label bug --type bug
gh issue create --title "..." --body "..." --parent 100 --blocking 101 --blocked-by 102
gh issue create --title "..." --body "复见图" --attach ./login.png#登录报错      # 附件与 alt 文本用 # 分隔
gh issue create --title "..." --body "..." --attach ./before.png --attach ./after.png   # 可给多次
```

`--attach` 在 2.101.0 起同时存在于 `issue`、`pr` 的 `create`/`edit`/`comment` 六条命令上，格式都是 `<文件>#<图片 alt 文本>`，省掉 `#` 后面那段就用文件名当 alt；它只收图片或视频，其它类型仍要把链接写进 `--body`。

`issue create` 的关系参数可以一次给全：`--parent` 挂到主 issue、`--blocking/--blocked-by` 建阻塞关系、`--type` 设 issue 类型；`--recover <文件>` 用于上次创建中途失败（附件已传但提交失败）时接着用，不必重传附件。

**分支处理**：

- **决定自己修**：`gh issue develop <number> --name fix/issue-<number> --checkout`。`--base <分支>` 指定新分支从哪个远端分支切出，`--branch-repo <owner/repo>` 把分支建到别的仓库，`--list` 查已关联的分支；2.101.0 起还有 `--worktree <路径>`，配合 `--checkout` 等于建分支同时开一个独立 worktree，不用把当前工作区切走。出口：`--list` 输出里有目标分支。
- **提错了仓库**：`gh issue transfer <number> <destination-owner/repo>`。评论、标签、附件跟着走，编号会变。出口：命令回显新的 issue URL。
- **重复问题**：`gh issue close <number> --duplicate-of <other-number>`，它比 `--comment` 更准，会在两条 issue 间留下重复关系。出口：`state` 为 closed 且 `stateReason` 为 `DUPLICATE`。
- **讨论失控**：`gh issue lock <number> --reason off_topic`（可选值 `off_topic|too heated|resolved|spam`），事后 `gh issue unlock <number>`。出口：`gh api repos/{owner}/{repo}/issues/<number> --jq .locked` 为 false（`gh issue view` 的 JSON 字段里没有 `locked`，只能走 api 核）。
- **需要第一眼看到**（安全公告、征集复现）：`gh issue pin <number>`，取消置顶用 `gh issue unpin <number>`，两者都接受 issue URL 作为参数。出口：仓库首页 Pinned 区出现（或消失）该 issue。
- **误关或复发**：`gh issue reopen <number> --comment "2026-09-25 在 v1.8.4 复现，重开"`。带一句说明，免得别人以为是机器人误操作。

要用户提供最小复现时，让对方发 gist 而不是把 200 行代码贴进评论。gist 是账号下的对象、不挂在仓库上，建、查、改名、删除都在 github-cli 第 5 步。

**讨论区是另一套对象**：开了 Discussions 的仓库，使用提问走讨论区而不是 issue，`gh issue list` 看不到它们。讨论有编号与节点 ID 两种定位方式：

```bash
gh discussion list --repo <owner>/<repo>                        # 默认只列 open；--state closed|all 才含已关闭
gh discussion list --category Q&A --answered=false --json number,title,url   # 挑未回答的（--category 名称或 slug）
gh discussion list -S "install" --sort created --order asc -L 50
gh discussion view <number> --comments --order oldest --limit 10    # 正文与顶层评论
gh discussion view DC_abc123                                     # 用评论节点 ID 看某一条的回复串
gh discussion view <number> --web                                 # 交浏览器
gh discussion create --title "如何离线安装" --category "Q&A" --body "..."   # 三者缺一即转交互问答
gh discussion comment <number> --body "感谢反馈"                    # 顶层评论
gh discussion comment <comment-id|comment-url> --body "..."        # 回复某条评论
gh discussion comment <comment-id> --edit --body "改过的内容"
gh discussion comment <comment-id> --delete --yes
gh discussion edit <number> --title "..." --category Ideas --add-label "good-first-issue" --remove-label stale
```

`--answered` 只在 Q&A 类目有意义，其它类目没有"已回答"状态。`discussion edit` 没有关闭与置顶参数，关闭讨论走 `gh api` 的 GraphQL 或网页。出口：`gh discussion list --answered=false --json number` 的条数按处理进度下降。

**产出**：每条 issue 有类型、有标签、有归属人，关系挂好。

**出口**：`gh issue list --state open --json number,labels --jq '.[] | select((.labels|length)==0)'` 无输出。`gh issue delete` 只用于删垃圾/测试 issue——删掉后引用它的链接全部失效，正常关闭的不要删。

## 3 处理 PR

**输入**：待审 PR 编号。

```bash
gh pr list --state open --limit 50
gh pr list --state merged --base main --search "merged:>2026-09-01"   # 回溯合并记录
gh pr view <number> --json mergeable,mergeStateStatus,reviewDecision,additions,deletions
gh pr checks <number>                    # CI 各项；--watch 跟到结束，--required 只看必需项
gh pr diff <number> --name-only          # 只看改了哪些文件；--patch 输出可 git apply 的补丁
gh pr checkout <number>                  # 切到 PR 分支本地跑；--detach 只看不改
gh pr checkout <number> --worktree ../wt-<number>   # 2.101.0 起：另开一个 worktree，不动当前工作区
gh pr review <number> --approve
gh pr review <number> --request-changes --body "缺测试"
gh pr comment <number> --body "..."
gh pr edit <number> --add-reviewer monalisa,<org>/<team> --add-label "bugfix" --base develop
gh pr close <number> --comment "方向不对，改走 <issue>"
```

**动作**：先审，再处理卡点，最后合并。

```bash
gh pr merge <number> --squash --delete-branch     # 压扁合并（仓库约定 squash 时用）
gh pr merge <number> --merge / --rebase           # 其余两种
gh pr merge <number> --auto --squash              # 挂自动合并：CI 与评审齐了自动合
gh pr merge <number> --disable-auto               # 撤掉自动合并
```

**分支处理**：

- **CI 绿了但落后于 base**（`mergeable` 为 `BEHIND`/`DIRTY`）：`gh pr update-branch <number>`，默认用 merge 把 base 并进 PR 分支；历史里不想留 merge 提交就加 `--rebase`。出口：`--json mergeable` 变 `CLEAN`。
- **草稿转正式**：`gh pr ready <number>`；还要继续改就 `gh pr ready <number> --undo` 退回草稿。
- **合错了**：别 reset 主干，用 `gh pr revert <number> --title "Revert ..." --body "引入 <issue> 回归"` 生成一条反向 PR，走正常评审合并；还不确定怎么修就先 `--draft`。
- **误关或作者回来**：`gh pr reopen <number> --comment "分支已 rebase 到 main，重开"`。
- **讨论过热**：`gh pr lock <number> --reason "too heated"`，事后 `gh pr unlock <number>`。
- **要在自己分支库改别人的仓库**：`gh pr create --repo <owner>/<repo> --head <你的用户名>:<分支>`。`--head` 的 `<user>` 只能是个人用户名，填组织名 gh 不支持；本地分支没推时别用 `--head`，让它自己问你要不要 fork。
- **要把一条改动直接交给 agent 做**：`gh agent-task`（preview，需要仓库侧已开通 agent 能力）。`gh agent-task create "fix errors" --base <分支>` 建任务，`-F task-desc.md` 从文件取描述（`-F -` 从标准输入），`--custom-agent my-agent` 用 `.github/agents/my-agent.md` 里定义的自定义 agent，`--follow` 当场跟日志。查进度用 `gh agent-task list --json id,state,pullRequestNumber,pullRequestState`，看单次会话用 `gh agent-task view <session-id>`，也接受 PR 编号、`OWNER/REPO#12345` 或分支名定位，`--log` 取会话日志、`-w` 交浏览器。出口：`agent-task list` 里该任务的 `pullRequestNumber` 出现且状态推进。

`--delete-branch` 会在合并后删掉分支；这条分支还要给别的 PR 用时去掉该参数，否则下一次 `gh pr checkout` 报分支不存在。

**产出**：PR 要么合并、要么给出明确的修改要求，队列里不留"看了没回"的。

**出口**：`gh pr list --json number,updatedAt --jq '.[] | select(.updatedAt < "2026-09-18T00:00:00Z")'` 无输出，即没有 7 天没动静的 PR。长期不活跃的处理策略：issue 满 14 天无活动打 `stale`，PR 满 7 天无活动发一次询问，issue 满 30 天无回应关闭。三条线为什么取这三个数，见 `references/ops.md`。

## 4 排 CI

**输入**：失败的分支或 run ID。

```bash
gh run list --status failure --limit 10        # 最近失败
gh run list --workflow <name> --limit 20       # 按工作流看
gh run list --branch <branch>                  # 按分支看
gh run view <run-id> --log-failed              # 先只看失败步骤的日志
gh run view <run-id> --log --job <job-id>      # 需要上下文时看整个 job
gh run rerun <run-id> --failed                 # 只重跑失败 job
gh run watch <run-id> --exit-status            # 脚本里等结果：非 0 退出即失败
```

**动作**：定因，再决定重跑还是修。flaky 与真失败的分辨点在日志里那一步的报错类型：网络超时/依赖镜像拉取失败多为环境性，断言失败/编译错误是真失败。真失败要回到第 3 步提修复，不能只重跑了事。

```bash
gh workflow list                                        # 含禁用状态
gh workflow view <name> --ref main                       # 触发规则、最近运行
gh workflow run <name> --ref main -f key=value            # 手动触发并传 input
gh workflow run <name> -F key=@value.txt                   # -F 支持 @文件 读值
gh workflow run <name> --json < inputs.json                # input 多时从 STDIN 喂 JSON
gh workflow run <workflow-id>                              # 也可用 ID；--ref 指定跑哪个分支/标签上的工作流文件
gh workflow enable <name> / gh workflow disable <name>    # 启停（禁用后不再触发也不出现在默认列表）
```

- **排队跑错分支、或这次运行没必要**：`gh run cancel <run-id>`（交互确认）；脚本里免确认加 `--force`。出口：`gh run view <run-id> --json status,conclusion` 为 `completed/cancelled`。若提示 already finished，不是错误，看一眼同一命令的 status 就收工。
- **取消/失败记录太多**：确认无留档价值后 `gh run delete <run-id>`（删记录，不删产物）。
- **要取产物验收**：`gh run download <run-id>`。`-n <name>`/`-p <glob>` 可重复只取部分，`-D <目录>` 指定落地目录，不带 `<run-id>` 时取的是**最近一次**运行——跨 run 找产物务必带 ID。
- **Actions 缓存占满/构建用到脏缓存**：`gh cache list --branch <branch>`，`gh cache delete <cache-id>` 或 `gh cache delete --all`。批量删在脚本里加 `--succeed-on-no-caches`，没有缓存时才不会非 0 退出。

**产出**：主干 CI 全绿，或写下"哪个工作流因何失败、由哪个 PR 修"。

**出口**：`gh run list --branch main --limit 5 --json conclusion` 全为 success。

## 5 发 release

**输入**：版本号、构建产物目录、main 已全绿（第 4 步的出口）。

```bash
gh release list --limit 20
gh release view v1.2.0 --json assets,tagName,isDraft,isPrerelease
gh release create v1.2.0 --target main --generate-notes            # 自动 changelog
gh release create v1.2.0 --notes-file CHANGELOG.md                 # 自己写
gh release create v1.3.0-rc1 --prerelease --title "..."            # 预发布
gh release create v1.0.0 dist/*.exe --title "v1.0.0"               # 建库同时带产物
gh release create v2.0.0 --verify-tag                             # 以已存在的 tag 为准，防手抖写错版本号
```

**动作**：不带文件参数的 `create` 只建了个空壳 release，页面里没有可下载文件。补文件不要重建 release：

```bash
gh release upload v1.0.0 dist/app.exe dist/app.zip --repo <owner>/<repo>
gh release upload v1.0.0 dist/app.exe --clobber --repo <owner>/<repo>   # 覆盖同名资产
gh release delete-asset v1.0.0 app-win-x86.exe --repo <owner>/<repo> --yes   # 只删单个资产
gh release download v1.0.0 --pattern "*.exe" --clobber                # 反向拉取到本地验收
gh release edit v1.2.0 --notes "..." / --latest / --draft
```

**产出**：`gh release view v1.0.0 --json assets --jq '.assets[].name'` 列出的文件与本次要发的一致。

**出口**：下载后先跑 `--version` 验证；经代理中转可能拿到截断文件。核对证明：

```bash
gh release verify v1.0.0 --repo <owner>/<repo>                    # 校验该 release 的构建证明
gh release verify-asset v1.0.0 ./app.exe --repo <owner>/<repo>    # 校验本地文件确实出自该 release
gh attestation verify ./app.exe --repo <owner>/<repo>             # 更完整的证明链
gh attestation download <file> --repo <owner>/<repo>              # 只取证明不看签名
gh attestation trusted-root > trusted_root.jsonl                  # 离线/内网取信任根，配 --custom-trusted-root
# 用户报"下载的文件对不对"时，用上面三条回答，不要靠比对哈希猜
```

**误发处理**：`gh release delete <tag>` 只删 release，`--cleanup-tag` 连 tag 一起删；删已发布的版本前先确认没人已经在依赖它，这是不可恢复动作，需用户明确确认。

## 5.5 npm Trusted Publishing（OIDC）——免 token 自动发布

当仓库包含 npm 包且需要自动发布时，用 GitHub Actions OIDC 签名替代 NPM_TOKEN，无需在 GitHub Secrets 中存储任何 npm 凭证。

**前提**：npm registry 策略变更（2026-11 起），直接 `npm publish` 需 bypass-2FA token 或交互式 2FA；stage-only token 只能 `npm stage publish`（进暂存队列，需网页批准）。Trusted Publishing 是唯一免人工干预的长期方案。2027-01 起 bypass-2FA granular token 将不能再直接 publish。

**配置步骤**：

1. **创建 `.github/workflows/publish.yml`**（参考模板）：

```yaml
name: publish
on:
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Dry run only (no publish)"
        required: false
        default: false
        type: boolean
  push:
    tags: ['v*']
permissions:
  contents: read
  id-token: write          # OIDC 签名必需
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 24
          registry-url: 'https://registry.npmjs.org'   # 启用 OIDC
      - run: |
          npm install -g npm@latest
          node -v && npm -v
      - run: npm install --ignore-scripts --no-audit --no-fund
      - run: npm publish
        if: ${{ github.event_name != 'workflow_dispatch' || !inputs.dry_run }}
      - run: npm pack --dry-run
        if: ${{ github.event_name == 'workflow_dispatch' && inputs.dry_run }}
```

关键要点：
- `id-token: write` 是 OIDC 签名前提，缺少则 npm 无法交换 token
- `registry-url: 'https://registry.npmjs.org'` 让 setup-node 自动注入 OIDC 认证
- 触发器用 `push: tags: [v*]` 而非 `release: published`（tag 推上去即触发，不依赖 GitHub Release 对象）
- 不需要 `NPM_TOKEN` secret，也不需要任何 GitHub 侧的 npm 凭证

2. **在 npmjs.com 配置 Trusted Publisher**（仓库 owner 操作）：
   - 包设置页 → Settings → Access → Trusted Publishers → Add Trusted Publisher
   - Provider: `github`
   - Owner: 仓库所属用户名/组织
   - Repository: 仓库名（不含 owner 前缀）
   - Workflow: `publish.yml`（必须与文件名精确匹配）
   - 可选 Environment: 绑定到 GitHub Environment 增加审批层

3. **验证窗口**：首次配置有 48h 验证窗口，需在此期间完成一次 `npm publish` 验证。验证通过后状态变为 Active，之后所有 publish 全自动。

4. **发布流程**：推 `v*` tag → GitHub Action 自动运行 → `npm publish` 走 OIDC 签名直发 → 无需 2FA、无需网页批准、无需 token。

**验证成功证据**（2026-11-13 dsh-skill-mcp-market 0.5.23）：
- `_npmUser.name = "GitHub Actions"`
- `_npmUser.email = "npm-oidc-no-reply@github.com"`
- `_npmUser.trustedPublisher = {id: "github", oidcConfigId: "c3e239d7-b6b9-410e-b23c-d78230c9dc1b"}`
- SLSA provenance attestation 自动附加

**注意事项**：
- Trusted Publishing 只认 `npm publish`（直发），**不认** `npm stage publish`
- 若 npm 包已存在（非首次发布），不受 48h 验证窗口限制
- 若 GitHub 仓库有分支保护或 ruleset 限制 tag 推送，需先调整
- 多个仓库发布同一 npm 包时，只需一个仓库配置 trusted publisher
- `workflow_dispatch` 手动触发时 `dry_run: true` 可预览 pack 结果而不实际发布

## 6 校准仓库设置

**输入**：第 1 步记下的仓库与角色（需要管理员权限）。

```bash
gh repo edit <owner>/<repo> --description "..." --add-topic ai --remove-topic old
gh repo edit <owner>/<repo> --enable-secret-scanning --enable-secret-scanning-push-protection
gh repo edit <owner>/<repo> --enable-advanced-security       # 开代码扫描等高级安全能力
gh repo edit <owner>/<repo> --enable-issues --enable-wiki --delete-branch-on-merge
gh repo edit <owner>/<repo> --squash-merge-commit-message pr-title   # 取值 {default|pr-title|pr-title-commits|pr-title-description}
gh repo edit <owner>/<repo> --visibility private --accept-visibility-change-consequences
gh repo rename <新名>                                    # 改当前目录所在仓库；只写新名，不带 owner
gh repo rename <新名> -R <owner>/<repo> -y                # 改指定仓库；-y/--yes 跳过确认提示
gh repo view <owner>/<repo> --web                         # 在浏览器里核对改完的样子
```

`gh repo rename` 的用法是 `gh repo rename [<new-name>] [flags]`，仓库靠 `-R` 选，不吃位置参数：实测 `gh repo rename a b` 报 `accepts at most 1 arg(s), received 2`。改名后远端地址变了，本地各克隆要跟着 `git remote set-url origin <新地址>`，否则下一次推拉报仓库不存在。

**动作**：一次核对全部关键元数据，缺哪补哪。

```bash
gh api repos/{owner}/{repo} --jq '{desc: .description, homepage: .homepage, topics: .topics, lang: .language}'
gh api repos/{owner}/{repo} --jq '{license: .license.spdx_id, hasWiki: .has_wiki, hasIssues: .has_issues, defaultBranch: .default_branch}'
gh api repos/{owner}/{repo}/actions/workflows --jq '.total_count'
```

- **`desc: null`**：缺 description，`gh repo edit --description` 补上。
- **`license` 为 `NOASSERTION`**：GitHub 没认出许可证。常见原因是 `LICENSE` 文件在标准文本后附加了说明段，干扰指纹匹配；把 `LICENSE` 精简为纯标准文本，附加说明移到 README 或 NOTICE，改后该字段应显示具体 SPDX ID。
- **CI workflow 为 0**：建议补一条最小校验工作流。
- **要新建仓库**：`gh repo create <name> --public --source <路径> --remote origin --push`；`-g/--gitignore <模板>`、`-l/--license <关键词>` 在建库时就带上，模板与关键词清单见本步后面的 `gh repo gitignore` 与 `gh repo license` 那组命令。若改用 REST `POST /user/repos` 自己建（例如脚本化发布），先确认凭证：含 `repo` scope 的 classic PAT / OAuth token 可直接建；细粒度 PAT（`github_pat_`）按 GitHub REST 文档需 `Administration`(write) 或 `Repository creation`(write) 之一（后者更窄）；**零 scope 的只读 token 会得到 404 `Not Found`，不是网络故障也不是 403**（GitHub 对无权限资源统一回 404 以防探测）。凭证判别见 `github-push` 第 1 步。
- **要建分支库（fork）**：判断依据是"只看不 fork"：只读代码用 `gh repo clone` 或免克隆读文件（见 github-access 主线）；要改代码提 PR 才 fork，因为 fork 会在你账号下真建一个仓库，之后要自己同步、自己清理。

```bash
gh repo fork <owner>/<repo> --clone=true      # --fork-name 改名；--org 建到组织；--default-branch-only 只跟默认分支
git remote add upstream https://github.com/<owner>/<repo>.git     # 没加 --clone 时自己补 upstream
gh repo sync <你的>/<repo>                                        # 默认同步默认分支
gh repo sync <你的>/<repo> --source <owner>/<repo> --branch main
gh api repos/<你的>/<repo>/commits/<branch> --jq '.sha[:7]'       # 出口核对：与上游同分支 SHA 一致
```

`--force` 会把目标分支硬重置到源，分支库上自己提交的提交会丢，只在"这条分支不打算留东西"时用。上游删库时 `gh repo fork` 报 404（不是网络问题，换 IP 重连无用）；`gh repo sync` 报无 upstream 时按上面第二条补远端。这份 fork 之后怎么长期跟上游、改动该放在哪个分支上，是另一条主线，见 github-fork。

克隆分支库这一步不在本技能：`gh repo clone` 会替你加 `upstream` 远端并把默认远端仓库设成上游，之后不带 `-R` 的 `gh issue`/`gh pr` 会打到原仓库，三种处置与出口判据见 github-access 第 3 步；本技能只负责建完 fork 之后 `gh repo set-default <你的>/<repo>` 把默认仓库纠正回来。

- **保护规则是否真的生效**：不要凭猜：

```bash
gh ruleset list --repo <owner>/<repo>                    # 本仓库规则集；-L 改条数（默认 30）、-w 开网页
gh ruleset list --repo <owner>/<repo> --parents=false     # 只看本仓库自己配置的（默认会把上层级的规则一起列出）
gh ruleset list --org <org>                               # 组织级规则集
gh ruleset view <id> --repo <owner>/<repo>                # 明细；该命令没有 JSON 输出参数
gh ruleset view <id> --org <org>                          # ID 属于组织级规则集时给 --org
gh ruleset view <id> --repo <owner>/<repo> --parents=false   # 只看这一层
gh ruleset check <branch> --repo <owner>/<repo>           # 某分支实际会命中哪些规则；不带参数用当前分支
gh ruleset check --default --repo <owner>/<repo>          # 改查默认分支
```

别名 `gh rs`。`list` 与 `view` 都有 `-p/--parents`，默认 true，即默认把组织级、更高层级生效的规则集一并算进来；只想知道本仓库自己配了什么就写 `--parents=false`（本版 gh 不接受 `--no-parents` 这种否定写法，实测报 `unknown flag`）。`ruleset` 只有 view 类命令，创建与修改规则集要走 `gh api`。

- **不维护但要保持可读**：`gh repo archive <owner>/<repo>`；`gh repo view <owner>/<repo> --json isArchived` 为 true 即生效。恢复用 `gh repo unarchive <owner>/<repo> --yes`。归档与删除的分界：确认无人引用、无 CI 依赖、不需留档才 `gh repo delete --yes`（不可恢复）；只是不想再维护就归档。批量清理先 `gh repo list <owner> --archived` 列出来逐个判断，不要照名字批量删。

**收尾的两类杂项**：

```bash
# 外部工单号自动成链接（工单号 TICKET-123 链到你们内网工单页）
gh repo autolink create TICKET- "https://example.com/TICKET?query=<num>"
gh repo autolink create STORY- "https://example.com/STORY?id=<num>" --numeric    # 只匹配数字
gh repo autolink list --repo <owner>/<repo> --json id,keyPrefix,isAlphanumeric,urlTemplate
gh repo autolink view <id> --repo <owner>/<repo> / gh repo autolink delete <id> --yes
#   <num> 只会被替换第一次出现处；autolink 列表只有仓库管理员能看到

# 给 CI/部署机一把只读公钥（不给人的 token）
gh repo deploy-key add ~/.ssh/gh-deploy.pub --title "CI 只读"        # 默认只读；要能推才加 -w
gh repo deploy-key list --repo <owner>/<repo> --json id,title,readOnly
gh repo deploy-key delete <key-id> --repo <owner>/<repo>
#   用 gh 加的 key 绑在当前认证 token 上：撤销 gh 的授权会连带删掉这些 deploy key

# 建库/建文件时取官方模板，不要手抄
gh repo gitignore list / gh repo gitignore view Python > .gitignore
gh repo license list / gh repo license view MIT > LICENSE.md      # 大小写敏感；也接受 SPDX ID
```

**出口**：元数据三项（description / license / CI 工作流数）符合预期；`gh ruleset check` 的输出与团队约定的保护规则一致。

## 7 处理安全告警与配置项

**输入**：第 6 步已确认有管理员权限。

```bash
# Dependabot 依赖告警
gh api repos/{owner}/{repo}/dependabot/alerts --jq '.[].security_advisory.summary'
gh api repos/{owner}/{repo}/dependabot/alerts --jq '.[] | select(.state=="open") | .number'
# secret scanning 告警（密钥被提交进仓库）
gh api repos/{owner}/{repo}/secret-scanning/alerts --jq '.[] | select(.state=="open") | .secret_type'
# code scanning 告警
gh api repos/{owner}/{repo}/code-scanning/alerts --jq '.[].html_url'
# 仓库自己的安全建议（未公开漏洞的私有讨论）
gh api repos/{owner}/{repo}/security-advisories --jq '.[].summary'
```

**动作**：secret scanning 报警时，光在 GitHub 上删掉那条告警不解决问题——密钥仍留在提交历史里，必须先在服务侧吊销，再改历史。仓库侧的清理是独立工作，不在 gh 命令范围内，先确认用户是否要做。高/严重级告警当天标记；依赖类告警通常表现为 `dependencies` 标签的 PR，走第 3 步合并：`gh pr list --label dependencies --json number,title`。

配置项分两类都在本步（仓库级与环境级），第三条线在别处：

```bash
# Actions 变量（明文，工作流里 vars.X）
gh variable list / gh variable get <NAME> / gh variable set <NAME> --body "..."   # 不给 --body 就从标准输入读
gh variable set <NAME> < value.txt                          # 值在文件里：重定向标准输入，没有 --body-file 这种参数
gh variable set -f .env                                     # -f/--env-file，从 dotenv 文件批量导入
gh variable set <NAME> --env <environment>                  # 部署环境级
gh variable set <NAME> --org <org> --visibility all --repos r1,r2   # 组织级
gh variable delete <NAME> / --env <environment> / --org <org>
# Actions 密钥（加密，工作流里 secrets.X）
gh secret list / gh secret set <NAME> --body "..."          # 同样只有 --body，取值走标准输入或 -f
gh secret set <NAME> < k.txt                                # 从文件读密钥值
gh secret set -f .env / gh secret set -f - < secrets.env    # dotenv 批量导入，`-f -` 表示 dotenv 内容来自标准输入
gh secret set <NAME> --env <environment> / --org <org> --repos r1,r2
gh secret set <NAME> --org <org> --no-repos-selected        # 组织级但先不放行任何仓库
gh secret set <NAME> --app dependabot / --user              # --app {actions|agents|codespaces|dependabot}；--user 为账号级
gh secret set <NAME> --no-store                             # 只打印加密后的 base64 值，不写进 GitHub
gh secret delete <NAME> / --env <environment> / --org <org>
```

`variable` 与 `secret` 都分仓库/环境/组织三层，`-b/--body`、`-e/--env`、`-f/--env-file`、`-o/--org`、`-r/--repos`、`-v/--visibility` 两侧一致；只有 `secret` 另有 `--app`、`--user`、`--no-store`、`--no-repos-selected`（变量的可见性没有"存了但不写"这种选项）。两者都没有 `--body-file`：值在文件里就用 `< 文件` 喂标准输入，一整个 dotenv 用 `-f`。

影响你在 GitHub 上提交身份与签名的账号级公钥（`gh ssh-key`、`gh gpg-key`）不在本步：`gh ssh-key add --help` 首行写的是 "Add an SSH key to your GitHub account"，没有选仓库的参数，属账号域，见 github-cli 第 5 步。本技能留下的都是挂在仓库上的那类：仓库与环境级 variable/secret、第 6 步的 `gh repo deploy-key`、ruleset、autolink。这条分界一句话记法：**对象能不能用 `-R <owner>/<repo>` 定位**，能就在本技能，不能就在 github-cli。

**产出**：open 状态的告警数下降，且每条留下的告警有人跟。

**出口**：`gh api repos/{owner}/{repo}/secret-scanning/alerts --jq '[.[] | select(.state=="open")] | length'` 与 `.../dependabot/alerts` 的同式结果都在团队接受范围内。检查频率不低于每周一次。

## 8 gh 拿不到的数据：gh api

**输入**：REST 路径。上面各步里凡 gh 没有对应子命令的读操作都走这里。

```bash
gh api repos/{owner}/{repo} --jq '.description'
gh api repos/{owner}/{repo}/branches --jq '.[].name'
gh api repos/{owner}/{repo}/tags --jq '.[].name'
gh api repos/{owner}/{repo}/collaborators --jq '.[].login'
gh api repos/{owner}/{repo}/contents --jq '.[].name'
gh api -X POST repos/{owner}/{repo}/issues -f title="..." -f body="..."   # 建 issue 的等价写法
gh api --paginate repos/{owner}/{repo}/issues --jq '.[].number'            # 列表超过 30 条必须加
gh api -X PATCH repos/{owner}/{repo} --input payload.json                  # 复杂负载从文件读
gh api -i repos/{owner}/{repo}                              # 连响应头一起打印（看 rate limit、分页游标）
gh api --cache 1h repos/{owner}/{repo} --jq '.description'  # 重复查询用缓存，省配额
```

`-F/--field` 会做类型推断（数字、布尔、`@文件` 读值），要保持字面字符串用 `-f/--raw-field`。`-H/--header key:value` 加请求头，`--hostname` 指向 GHES。`--slurp` 配合 `--paginate` 把多页结果合成一个数组，`--cache 1h` 对同一端点在时长内复用响应。

**分支：gh 打到 api.github.com 失败时**。这一步不判网络。gh 用的是自己的解析结果，本机 hosts 与 `--resolve` 对它无效，先按 github-access 第 6 步的升级顺序判定是 IP 问题还是权限问题；判定为 IP 问题且要的只是 REST 那份 JSON 时，用顶 IP 的 curl 取同一端点，写法与按 host 分组的 IP 表在 `../references/access.md` 第四节。

**出口**：拿到与 `gh api` 一致的 JSON。两种途径都失败时，不要在这一步连续重试，回 github-access 收口。

## 9 收口

```bash
gh status                                  # 本轮该做的事是否还挂着（不需要在 git 仓库里）
gh issue status                              # 与我有关的 issue，需要站在某个仓库的工作目录里
gh pr status                                 # 同上，PR 版；--conflict-status 顺带列出每条的冲突状态
gh issue status --json number,state          # 分组对象：assigned / createdBy / mentioned
gh browse --repo <owner>/<repo>            # 仓库首页
gh browse 217                              # issue / PR 用编号，同一个参数
gh browse main.go:312                       # 文件带行号
gh browse main.go:312 --blame              # blame 视图
gh browse main.go --branch <分支名>         # 或 --commit <SHA>（不给 SHA 时取最后一次提交）
gh browse -r / -s / -w / -a / -p           # releases / settings / wiki / actions / projects
gh browse --no-browser                      # 只打印目标 URL，不唤起浏览器（要发链接给别人时用）
```

`gh status` 不吃 git 上下文，输出五栏：Assigned Issues、Assigned Pull Requests、Review Requests、Mentions、Repository Activity。`gh issue status` 与 `gh pr status` 相反，要用当前目录的 git remote 推断仓库，站在非 git 目录里报 `failed to run git: fatal: not a git repository`（2026-09-25 实测），换仓库要先 `cd` 过去。

`gh browse` 只负责在浏览器里打开，自己不取内容；取内容用 `gh repo read-file`。想改用别的浏览器靠 `BROWSER` 环境变量。注意 releases 是 `-r/--releases`，没有 `--release`、`--pr`、`--issues` 这类参数。

**自检清单**：所有 open issue 都有标签与归属人；无超过 7 天未回应的 PR；CI 失败已定位原因（不是只重跑过）；release 的资产清单与 changelog 与实际构建一致；open 状态的安全告警每条都有人跟。五项不满足就不要宣布本轮维护结束，每条对应的失效见 `references/ops.md` 末段。

## 红线

- `repo delete`、`release delete`、`run delete`、`cache delete --all`、`label delete`、`issue delete`、`repo sync --force`、`label clone --force`、`release upload --clobber` 都是删数据或覆盖数据，执行前列出受影响对象交用户确认。
- 安全类操作有先后顺序：吊销密钥在服务侧、清理历史在本地、关闭告警在最后。反着做会留下"告警关了密钥还有效"的状态。
- `gh api -X POST/PATCH/DELETE` 直接改远端，没有预览。写操作先用 `GET` 同一端点确认对象存在。

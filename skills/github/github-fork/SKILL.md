---
name: github-fork
description: "GitHub 分支库（fork）子技能——把上游仓库搬到你自己账号下并长期跟进：判要不要 fork、建 fork、把 gh 的默认远端纠正回自己的 fork、日常把 fork 跟上上游、在分支上改与推、要提回上游时交回 github-ops、以及分支库的清理。触发关键词：fork、分支库、派生仓库、跟着上游改、上游同步、gh repo fork、gh repo sync、upstream、origin 指错、提 PR 前先 fork、个人 fork、组织 fork、default-branch-only、删掉我的 fork。"
---

# GitHub 分支库（fork）

一次分支库任务的主线依次是判要不要 fork、建 fork、把 gh 的默认远端纠正回自己的那份、把改动放在分支上、按周期跟上游、要提回上游时交回 github-ops，最后决定这份 fork 留还是删。逐步往下走，每步给出出口再进下一步。

命令形态取自本机 gh 2.101.0 的各 `<命令> --help` 原文。本技能与 github-access（克隆方向）、github-push（推送方向）、github-ops（仓库生命周期）有意重叠：每份子技能都要求能独立读完一条主线，所以 fork 相关的命令在别处也出现，此处是完整的那一份。

## 实测环境（本文件里的判断都在这台机器上跑过）

- gh 2.101.0 (2026-09-15)，两份安装都不在 PATH，用绝对路径或先绑定变量（取法见 github-cli 第 1 步）。
- 样本：上游 `huang-doudou567/tax-policy-search`，本次建的分支库 `kuailexiaozixin/tax-policy-search`。两侧默认分支都是 `master`，不是 `main`；两边 `master` 同为 `1dea425`。
- 本文件写到的默认远端行为、`gh repo sync` 回显、`gh repo set-default` 的落盘键，都是 2026-09-25 在这对仓库上实测得到的，实测细节写在对应步骤里。

## 前置准备（只列材料）

- 上游仓库的 `owner/repo`，以及它的默认分支名（不要假定叫 `main`，用 `gh api repos/<owner>/<repo> --jq .default_branch` 读出来）。
- 当前登录账号名：fork 默认建在这个账号下；要建到组织得另有写权限，用 `--org <组织>`。
- token 的 scope 至少含 `repo`（`gh auth status --json hosts` 读，不带 `-t`；补 scope 见 github-cli 第 4 步）。
- 明确这份 fork 的用途：只是给自己一个可写的地方提 PR，还是要长期带上自己的改动。这两条在第四步分岔，建库时决定不了，但会影响你怎么放提交。

## 1 判要不要 fork

**输入**：你对这个仓库要做的事。

**动作**：按三条判据取一条。

- 只是读代码、看目录、取单个文件：不 fork。fork 会在你账号下真建一个仓库，之后要自己同步、自己清理。用 github-access 的免克隆读法（`gh repo read-file`、`gh repo read-dir`）或整仓克隆。
- 要改代码并且改动要让上游看到：必须有一个上游之外可写的远端分支，也就是要 fork；除非上游给了你分支推送权限（少数项目允许协作者直推分支），那种情况不用建库。
- 要改代码但永远不打算提回上游（自用版、内网定制、带私有补丁）：也要 fork，因为你需要一个能自由推的地方；这条线在第四步单独走，规则与提 PR 那条不同。

**产出**：一句话写明用途（提回上游 / 只自用 / 不 fork）。

**出口**：判为"不 fork"就退出本技能，回 github-access 或 github-push。判为 fork，进第 2 步。

## 2 建 fork

**输入**：上游 `owner/repo`，以及是否连带克隆。

```bash
gh repo fork <owner>/<repo> --clone=true
gh repo fork <owner>/<repo> --clone=true -- <git clone 的额外参数>   # -- 之后原样交给 git clone
gh repo fork <owner>/<repo> --fork-name my-<repo>          # 给分支库改名，不影响上游
gh repo fork <owner>/<repo> --org <组织>                    # 建到组织而不是个人账号
gh repo fork <owner>/<repo> --default-branch-only           # 只带默认分支，不要上游的其它分支
gh repo fork <owner>/<repo> --remote-name myfork      # 给"新 fork 那条远端"改名（默认叫 origin）
gh repo fork <owner>/<repo> --remote                   # 已在本地时只补一条指向 fork 的远端，不克隆
```

**动作**：`gh repo fork --help` 原文对远端行为的说明是：新建的 fork 默认成为你的 `origin` 远端，已存在的 `origin` 会被改名为 `upstream`，并且 **`upstream` 会被设为默认远端仓库**。也就是说建完 fork 的那个目录里，之后不带 `-R` 的 `gh issue`/`gh pr` 命令默认打到上游——这正是第 3 步要处理的事。注意 `--remote-name` 改的是**新 fork 那条远端**的名字（默认 `origin`），不是上游远端的名字；这条命令没有给上游改名的参数，上游名字要到克隆那一步用 `-u/--upstream-remote-name` 定（见第 3 步）。

不带 `--clone` 时只在服务端建库，本地什么都不动；已有克隆的话之后自己 `git remote add upstream <上游地址>`。

**产出**：你账号下的 fork 地址，本地仓库目录（带 `--clone` 时）。

**出口**：三条都过才算建好。

```bash
gh api repos/<你的>/<repo> --jq '{fork: .fork, parent: .parent.full_name, default: .default_branch}'
gh api repos/<你的>/<repo>/commits/<默认分支> --jq '.sha[:7]'
gh api repos/<owner>/<repo>/commits/<默认分支> --jq '.sha[:7]'
```

期望 `fork: true`、`parent` 是上游、两侧同一分支的 SHA 一致。本次实测两侧都是 `1dea425`。上游若已删除或改名，`gh repo fork` 报 404，这不是网络问题，换 IP 重连没有用。

## 3 把 gh 的默认远端纠正回自己的 fork

**输入**：一个 fork 的克隆（无论是 `gh repo fork --clone` 建的，还是第 4 类场景里 `gh repo clone` 别处已有的 fork）。

```bash
git remote -v
gh repo set-default --view
gh repo set-default origin
gh repo set-default <你的>/<repo>
gh repo set-default --unset
```

**动作**：`gh repo clone` 克隆一个 fork 时，help 原文写了两条：上游会作为名为 `upstream` 的额外远端加入（名字可用 `-u/--upstream-remote-name` 改，值写成 `@owner` 就是"用上游的 owner 命名"），并且**上游会被设为默认远端仓库**；不想加这条远端用 `--no-upstream`。

本次实测克隆 `kuailexiaozixin/tax-policy-search` 的结果：`git remote -v` 有 `origin`（我的 fork）与 `upstream`（上游）两条，克隆过程还额外 fetch 了一次 `upstream/master`；`gh` 把默认远端记在 git 配置里，键是 `remote.upstream.gh-resolved`、值 `base`；此时不带 `-R` 的 `gh repo view --json nameWithOwner,isFork` 返回的是 **`huang-doudou567/tax-policy-search`、`isFork: false`**，即 gh 认定你在上游干活。跑 `gh repo set-default origin` 之后，键变成 `remote.origin.gh-resolved base`，`--view` 打印 `kuailexiaozixin/tax-policy-search`，同一条不带 `-R` 的 `gh repo view` 才报出 `isFork: true`。

**产出**：默认远端仓库 = 你的 fork。

**出口**：`gh repo set-default --view` 打印的是 `<你的用户名>/<repo>`。`gh repo set-default` 成功时不回显，别把"没输出"当成没生效。这一步没过就往下走，后面每一条不带 `-R` 的写命令都可能落到上游仓库上。

## 4 日常跟上游

**输入**：默认分支名（第 2 步出口里读到的那个，本次样本是 `master`）。

```bash
# 让服务端那份 fork 跟上上游
gh repo sync <你的>/<repo>
gh repo sync <你的>/<repo> --branch <分支>
gh repo sync <你的>/<repo> --source <owner>/<repo> --branch <分支>

# 让本地跟上服务端（gh repo sync 只改远端，不动工作区）
git -C <本地目录> fetch origin
git -C <本地目录> checkout <默认分支>
git -C <本地目录> pull --ff-only origin <默认分支>
```

**动作**：`gh repo sync --help` 原文说明它做的事是"用源的默认分支把目标仓库上的同名分支更新为与之相等，非 `--force` 时走 fast-forward"，无参数时目的地是当前本地仓库对应的远端仓库。所以两条通道要分开看：`gh repo sync` 对齐的是 GitHub 服务端那两份仓库，本地目录里的工作区文件它不碰。

本次实测在两侧已经相等时跑 `gh repo sync <你的>/<repo>`：退出码 0、无任何输出，本地 `git rev-parse HEAD` 前后都还是 `1dea425`。这印证了"本地不会自己跟上"，也说明这条命令幂等、可以按周期重复跑。

由此得出一条约束，它决定你怎么放提交：**要长期带自己的改动，就别把改动提交到与上游同名的那个默认分支上**。默认分支一旦有自有提交，服务端对齐不再是 fast-forward，`gh repo sync` 就不能正常完成（此句由 help 的 fast-forward 语义导出，本文件未做实测），此时只剩两条路——把你的分支 rebase 到新的上游提交上，或者用 `--force` 硬重置。

```bash
gh repo sync <你的>/<repo> --force        # 硬重置到上游：fork 默认分支上你自己的提交会丢，属不可恢复动作
```

**产出**：一个与上游相等的默认分支，加上若干条承载你改动的分支。

**出口**：三项都过。`gh api repos/<你的>/<repo>/commits/<默认分支> --jq '.sha[:7]'` 与上游同式结果一致；`git -C <目录> rev-parse HEAD` 与远端 fork 的 SHA 一致；`git -C <目录> log --oneline origin/<默认分支> ^upstream/<默认分支>` 无输出（默认分支上没有你的自有提交，这条命令要先 `git -C <目录> fetch upstream`）。

## 5 在分支上改与推

**输入**：第 1 步判出的用途，和要做的改动。

```bash
git -C <目录> checkout -b <分支名> origin/<默认分支>       # 从跟上游一致的默认分支切出来
gh issue develop <上游的 issue 编号> --repo <owner>/<repo> --name fix/<编号>   # 上游开 issue 时用它建分支，见 github-ops 第 2 步
git -C <目录> push -u origin <分支名>
```

**动作**：分支名要能说明意图，因为你可能有十几条不打算提回上游的分支。推送、核对远端收到、失败分诊的完整主线在 github-push（其第 3 步用 `git -C <目录> push -u origin <分支>` 的写法，第 5 步用 `gh api repos/<owner>/<repo>/commits/<分支> --jq .sha` 核对，两条都适用这里）。要点重复一次：`-u` 只在首次建立追踪关系时需要。

**产出**：fork 上有一条含你改动的分支，本地 SHA 与远端一致。

**出口**：`gh api repos/<你的>/<repo>/commits/<分支名> --jq '.sha[:7]'` 打印的短 SHA 与本地 `git -C <目录> rev-parse --short <分支名>` 相同。

## 6 要提回上游时

**输入**：第 5 步那条分支，且这次你确实想把改动交回上游。

```bash
gh pr create --repo <owner>/<repo> --head <你的用户名>:<分支名> --base <上游的默认分支> --title "..." --body-file pr.md
```

**动作**：`--repo` 指上游、`--head` 写成 `<用户>:<分支>` 表示分支在你的 fork 上。`--head` 的 `<user>` 只能是个人用户名，填组织名 gh 不支持；本地分支还没推时不要写 `--head`，让 gh 自己问你要不要 fork。之后这条 PR 的评审、合并、卡点处理全部在 github-ops 第 3 步，本技能不再延伸。

**产出**：一条挂在上游仓库下的 PR URL。

**出口**：`gh pr view <编号> --repo <owner>/<repo> --json headRepositoryOwner,headRefName --jq '"\(.headRepositoryOwner.login) \(.headRefName)"'` 回显的 owner 是你、分支是第 5 步那条。`headRepositoryOwner` 是个对象，取登录名要走到 `.login`（实测该字段的值是 `{"id": "...", "login": "cli"}` 这种形态）。

## 7 收口

**自检清单**，四条不过不要宣布本轮跟进结束：

1. `gh repo set-default --view` 指向你的 fork。不满足的后果：后续写命令打到上游。
2. fork 的默认分支与上游同 SHA。不满足的后果：你的分支基于旧代码，之后冲突范围越拖越大。
3. 默认分支上没有自有提交。不满足的后果：`gh repo sync` 不再能快进，只能 rebase 或硬重置。
4. 每条带自有改动的分支都能说出用途（会提回上游 / 只自用）。不满足的后果：半年后没人敢删。

**要清理时**：`gh repo list <你的用户名> --fork` 列出你名下的分支库，逐个对照上面四条判断。删仓库是不可恢复动作（`gh repo delete <你的>/<repo> --yes`），删除前先按 github-ops 的红线列出受影响对象交用户确认；只是不想再跟进，用 `gh repo archive <你的>/<repo>` 保留内容停止维护。

## 红线

- `gh repo sync --force` 是硬重置：fork 上目标分支的自有提交会直接丢失，只在"这条分支不打算留任何东西"时用，执行前说明会丢哪些提交并交用户确认。
- `gh repo delete` 删的是整个仓库，不是删本地目录；已 fork 且带自有改动的库删掉后无从恢复。
- 名字与方向不匹配这件事要靠 `git remote -v` 判：实测克隆 fork 后 `upstream` 的 fetch 与 push 两条地址都指向上游仓库，也就是说 `git push upstream <分支>` 会试着往别人的仓库推（没有权限时报错，但有权限时就直接改到上游了）。要往自己 fork 推一律写 `origin`。
- 不 fork 只为绕过登录：私有上游你本来就能推时，fork 反而多一层同步成本。

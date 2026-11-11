---
name: github-skill
description: "GitHub Agent 技能管理子技能——用 gh skill 从 GitHub 仓库安装/管理/发布 agent skills。覆盖 gh skill install/list/preview/publish/search/update。触发关键词：gh skill、技能管理、安装技能、发布技能、gh skills、管理 GitHub 技能、更新技能、技能上传、技能发布、更新技能仓库、发技能 release、技能仓库内容更新。"
---

# GitHub Agent 技能管理（skill）

用 `gh skill` 从 GitHub 仓库**安装、管理、发布 agent 技能**（SKILL.md 技能）。官方定位：*"Install and manage agent skills from GitHub repositories"*。

> **重要**：`gh skill` 处于 **preview** 阶段，行为可能变化；且**仅在较新版本 gh CLI 提供**。旧版本（如 2.78.0）执行 `gh skill` 会返回 `unknown command`——此时先升级 gh CLI 或用下方「版本说明」。

## 何时使用

- 用户要「从 GitHub 安装/搜索/发布 agent 技能」
- 用户说「gh skill」「技能管理」「装个技能」「把技能发到 GitHub」
- 管理 SKILL.md 技能的发布（publish）与获取（search/install/update）

### 技能仓库发布决策（先定方向，避免走错路）

**判断任务方向**：当任务是把**技能仓库**（含 `skills/<name>/SKILL.md` 结构，或 hermes-desktop 这类 agent 技能仓库）的内容推上 GitHub，这是「技能发布」场景，**必须走 `gh skill publish`**，不要用裸 `git push` 手动同步**替代发布**。**这不等于不需要 push**：publish 只打 tag + 建 release、不推代码，正确流程是「push 送代码 → publish 建 release」，见下方端到端流程第 ③⑤ 步。

| 任务 | 正确命令 | 归属 |
|---|---|---|
| 把技能仓库内容更新 / 发布到 GitHub（建 release） | `gh skill publish`（见下方端到端流程） | 本子技能 |
| 普通代码 / 任意仓库的代码推送 | `git push` | github-push |
| 从 GitHub 安装技能 | `gh skill install owner/repo` | 本子技能 |
| 搜索技能 | `gh skill search <kw>` | 本子技能 |

> 反模式：`gh skill publish` 会做 agentskills.io 规范校验、建立 `skills/<name>/` 虚拟文件树并创建 release；**只用** `git push` 手动同步技能文件、不跑 publish，会缺失这些（缺校验、缺 release、不遵循强制规则），是错误做法。**识别到「技能仓库」就路由到 gh skill publish，不落 github-push 作为发布动作。** 反过来只跑 publish、不 push 也是错的（见端到端流程第 ③ 步）：publish 不推代码。

## 可用命令

```
gh skill install    # 安装技能
gh skill list       # 列出已安装技能
gh skill preview    # 安装前预览
gh skill publish    # 发布技能（--dry-run 校验）
gh skill search     # 搜索技能
gh skill update     # 更新已安装技能（--all 全部）
```

别名：`gh skills`。

## 用法示例

```bash
# 搜索技能
gh skill search terraform

# 安装技能（来自 GitHub 仓库）
gh skill install github/awesome-copilot documentation-writer

# 列出已安装技能
gh skill list

# 安装前预览
gh skill preview github/awesome-copilot documentation-writer

# 更新所有已安装技能
gh skill update --all

# 校验技能能否发布（dry-run）
gh skill publish --dry-run
```

## 发布实战要点（gh skill publish）

> 以下要点在 2.97.0 上实测得出（2026-08 验证），2026-09-25 升到 2.101.0 后复验仍成立，是发布 agent 技能的关键坑。

### 1. 必须用 `skills/<name>/SKILL.md` 结构（root-level 校验不过）

`gh skill publish` 要求**技能 name 与其所在目录名一致**。若把 `SKILL.md` 放在**仓库根**（root-level），会报错：

```
error  <skill>  name "<name>" does not match directory name "."
validation failed with 1 error(s)
```

即使 `name` 与仓库名一致也过不了（gh 把 root 目录解析为 `.`）。**解法**：技能必须组织为 `skills/<name>/SKILL.md`（及其资源），这是 gh skill 官方推荐的可发现结构：

```
skills/<name>/SKILL.md   # 技能本体 + 资源（references/examples/templates 等）
README.md / LICENSE 等    # 仓库元文件留在根
```

技能发现约定（会递归匹配）：
- `skills/*/SKILL.md`
- `skills/{scope}/*/SKILL.md`
- `*/SKILL.md` (root-level，但校验会失败，勿用)
- `plugins/{scope}/skills/*/SKILL.md`

### 2. 子技能名必须符合 agentskills.io 规范

嵌套/聚合技能（一个技能下多个子技能）时，**每个子技能的目录名与 `name` 都必须**：
- 全小写字母数字 + 连字符（禁止大写、下划线）
- `name` 与目录名**完全一致**（含大小写）

否则报错，例：
```
error  x/scrapling-official  name "scrapling-official" does not match directory name "Scrapling"
error  x/Scrapling  name "Scrapling" does not follow agentskills.io naming convention (lowercase alphanumeric + hyphens)
error  x/core  name "core" does not match directory name "agent-browser"
```

> **Windows 大小写坑（实测踩过）**：在 Windows 上把目录从 `Scrapling` 改名为 `scrapling`（仅大小写差异）时，`mv`/`mvdir` 不会触发 git 重命名（文件系统大小写不敏感），本地 `gh skill publish --dry-run` 看似通过，但 **push 后远程仍是旧大小写**，Linux CI 跑 `gh skill publish --dry-run` 才暴露。修复必须用**两阶段 `git mv`** 强制改名：
> ```bash
> git mv Scrapling _tmp && git mv _tmp scrapling
> ```
> 发布前若加了 CI 校验，务必以 **Linux 上的 CI 结果为准**验证大小写。

### 3. publish 会发布**所有**被发现的技能

`gh skill publish` 没有「只发布指定技能」选项——它会校验并发布仓库里**所有**匹配发现约定的 SKILL.md（含聚合技能的子技能、示例项目内嵌的 SKILL.md）。发布前用 `--dry-run` 看清楚会发布哪些、有无 error：

```bash
gh skill publish --dry-run .
# 全部是 warning（license/body 长度）且无 error 才可发布
```

### 4. 本地保持 root 结构、用 git worktree 虚拟发布

灵犀/本地技能目录常用 root-level（`<技能>/SKILL.md`），但 gh skill 要求 `skills/<name>/`。**不要改本地技能结构**（会破坏灵犀加载），改用 `git worktree` 建独立发布工作树：

```bash
# 复用本地 git 仓库（不 clone、不碰主工作树）建独立发布工作树
cd <本地技能git仓库>
git worktree add --detach <发布目录> origin/main
# 在发布目录里把技能内容重组为 skills/<name>/ 结构（元文件留根）
# 同步本地最新技能内容，commit，push
```

**用 `origin/main` 而不是 `main`**：本地工作分支可能是 `master`（2026-11-11 实测本机技能仓库就没有名为 `main` 的本地分支，写 `main` 会直接报 `invalid reference`）。远端默认分支也要当场确认：`gh api repos/<owner>/<repo> --jq .default_branch`。

发布后清理 worktree：`git worktree remove --force <发布目录>`。

### 端到端发布流程（本次验证可复现版）

把本地技能仓库内容发布到 GitHub（含最新技能内容）的完整流程：

```bash
# ⓪ 先问出远端默认分支，下面统一用 $BRANCH，不要假定叫 main
#    （github-push 第 5 步实测过：cli/cli 的默认分支是 trunk，写 main 会 422）
BRANCH=$(gh api repos/<owner>/<repo> --jq .default_branch)

# ① 用 worktree 检出含 skills/<name>/ 结构的远端（本地安装目录不改）
git worktree add --detach <发布目录> "origin/$BRANCH"

# ② 把本地最新技能内容同步到 <发布目录>/skills/<name>/（本地保持 root 结构不动）
#    按「本地文件 -> 远端 skills/<name>/ 对应路径」复制/更新/删除；
#    只保留真实内容差异，剔除 CRLF/LF 行尾噪声（对 git diff 为空的文件还原为远端版）

# ③ 【不可跳过】在发布树提交，并把提交推到远端默认分支
#    gh skill publish 只打 tag + 建 release，不会把本地提交推到远端（2026-11-11 实测）。
#    漏掉这步会得到「release 已建、命令返回 0，但 tag 指向旧 commit、远端分支没动、
#    新文件 Not Found」的假绿。按 github-push 第 2/3 步当场探到的通路加前缀。
git -C <发布目录> add -A
git -C <发布目录> commit -m "<技能名> vX.Y.Z — <本次改动摘要>"
git -C <发布目录> push origin "HEAD:$BRANCH"

# ④ 校验（warning 可接受、error 必改）
gh skill publish --dry-run <发布目录>

# ⑤ 发布 + 创建 release（--tag 指定 semver 版本即非交互）
gh skill publish --tag vX.Y.Z <发布目录>
#    发布前查最新 release：gh release view --json tagName 或 gh release list；版本号顺延（v1.8.3 -> v1.8.4）
#    仓库需已带 agent-skills topic：gh repo view --json repositoryTopics 确认（已带则 publish 不交互询问）

# ⑥ 验证：不能只看 release 存在，要确认远端内容与本地一致
gh release view vX.Y.Z --repo <owner>/<repo>
#    内容指纹判据：远端默认分支的 tree sha 必须等于发布树本地 HEAD 的 tree sha
gh api "repos/<owner>/<repo>/commits/$BRANCH" --jq .commit.tree.sha
git -C <发布目录> rev-parse HEAD^{tree}
#    再抽查本次新增的文件在远端确实可见（严格校验返回的是 sha 而非错误 JSON）

# ⑦ 清理
git worktree remove <发布目录>
```

发布后用户可安装：`gh skill install <owner>/<repo>`；锁版本：`gh skill install <owner>/<repo> <skill> --pin vX.Y.Z`。

> 实测（2026-08，hermes-desktop-skill）：`gh skill publish` 不改任何文件（非 `--fix`），校验仅报 license 缺失为 recommended warning（不阻塞）；本地技能安装目录全程不动。`gh skill publish` 会发布仓库里**所有**被发现的技能，发布前 `--dry-run` 看清。

### 反模式红线

- **用 `git push` 手动同步技能文件替代 `gh skill publish`** —— 缺 agentskills.io 校验、缺 release、不遵循 `skills/<name>/` 强制规则。技能仓库发布必须走 `gh skill publish`。
- **只跑 `gh skill publish` 而不先把提交 push 到远端**（2026-11-11 实测踩过）：publish 只打 tag + 建 release，不推代码。跳过 push 会得到 release 已建、返回 0、但 tag 指向旧 commit 且远端默认分支（当次该仓库为 `main`）完全没动的假绿，新文件在远端查不到。**push 与 publish 是两步，不能互相替代，见端到端流程第 ③⑤ 步。**
- **直接修改本地技能安装目录结构**（把 root 下的技能文件挪进 `skills/<name>/`）会破坏宿主（灵犀等）加载，必须用 worktree 建独立发布工作树。
- **把 CRLF/LF 行尾噪声当成内容差异提交** —— 同步后对 `git diff` 为空的文件（仅行尾差异）应还原为远端版，避免污染提交。
- **publish 前不 dry-run** —— 会发布所有被发现技能，先 `--dry-run` 确认无 error 再发布。

### 5. 发布后检查结构调整引入的断链

把目录结构从 root 调整为 `skills/<name>/` 会让**仓库根元文件**（README 等）里指向技能内容的相对链接失效。发布后要扫描并修正：
- 检查 root 级 `.md` 的相对链接是否指向 `skills/<name>/...` 新路径
- 子树（`skills/<name>/` 内部）相对链接平移后通常仍有效
- **CHANGELOG 历史条目**对已删除/合并文档的旧编号链接是历史实况记录（原作者常有说明），**勿篡改**
- 过滤误报：`@/...`（FastHTML 文档特殊语法）、`/xxx`（站点绝对路径）不是仓库内文件

扫描范围为什么只限仓库根元文件：被移动子树**内部**的相对链接跟着目录一起平移，仍然有效；断掉的是根那一层指向被移走路径的链接。扩大范围只会撞上子树内的误报。

### 6. 缺失 release 用 gh release 补

push 了新代码但没打 release 时，用 `gh release create` 补（`--generate-notes` 自动生成）：
```bash
# <代理端口>：当场扫端口，不要照抄任何固定值；<默认分支>：gh api repos/<owner>/<repo> --jq .default_branch
HTTPS_PROXY=http://127.0.0.1:<代理端口> HTTP_PROXY=http://127.0.0.1:<代理端口> \
  gh release create vX.Y.Z --repo <owner>/<repo> --target <默认分支> --generate-notes --title "..."
```

### 7. 常见阻塞与处理（2026-09 实测）

**① `gh` 可能不在当前 shell 的 PATH**：2026-11-10 复测用户 PATH 已含 gh 目录，但当日 07:04 之前启动的终端仍拿不到，裸敲 `gh` 报 `command not found`。判不出当前窗口属于哪一类，所以一律用全路径调用：

```bash
"$USERPROFILE/AppData/Local/Programs/gh/bin/gh.exe" skill publish --tag v0.3.0 .
```

**② `--tag` 仍会交互**：即使指定了 `--tag`，publish 在最后仍会问
`? Enable immutable releases? (Y/n)`。无人值守会一直挂住。用管道喂答案：

```bash
printf 'n\n' | gh skill publish --tag v0.3.0 .
```

**③ 推送保护（GH013）拦截**：示例/构建产物里常硬编码第三方凭据，push 会被
`push declined due to repository rule violations` 拦下，并给出具体文件与行号。
处理顺序是：先 `git reset --soft HEAD~1`，撤下该文件，再在 `.gitignore` 加排除规则，最后重新提交推送。
**不要 force push、不要点 unblock-secret 放行**。发布前先扫一遍：

```bash
grep -rlE "apps\.googleusercontent\.com|GOCSPX-|sk-[A-Za-z0-9]{20,}" skills/
```

**④ 通用 `.gitignore` 误伤内嵌第三方库**：`build/`、`dist/` 这类规则会吞掉形如
`examples/*/webroot/pdfjs-dist/build/pdf.worker.min.mjs` 的运行时必需资源。
用窄例外放行，注意 **父目录被排除时子文件无法 re-include，必须否定目录本身**：

```
!**/pdfjs-dist/build/
```

**⑤ 静默假绿：publish 返回 0 却没建 release（2026-11-10 实测）**：本机用 `env VAR=... gh ...`、`timeout ... gh ...` 包装，或把输出重定向到文件时，`gh skill publish --tag vX.Y.Z .` 会**零输出、退出码 0、但不创建任何 release**。这不是凭证权限问题（scopes 含 `repo`），而是包装方式让这条 preview 命令在非交互终端里提前静默退出。正确写法是 shell **直接变量赋值前缀**，输出走终端或 `tee`：

```bash
cd <发布目录>
printf 'n\n' | HTTPS_PROXY=http://127.0.0.1:<代理端口> HTTP_PROXY=http://127.0.0.1:<代理端口> \
  "$USERPROFILE/AppData/Local/Programs/gh/bin/gh.exe" skill publish --tag v1.33.1 .
```

发布后**必须回查远端**才算成功，不能只看退出码：

```bash
HTTPS_PROXY=http://127.0.0.1:<代理端口> HTTP_PROXY=http://127.0.0.1:<代理端口> \
  "$USERPROFILE/AppData/Local/Programs/gh/bin/gh.exe" release view v1.33.1 --repo <owner>/<repo>
```

**⑥ 另一种假绿：release 建了但内容是旧的（2026-11-11 实测）**：与第 ⑤ 条相反，这次 `publish` 打印 `✓ Published v5.18.0`、退出码 0、release 与 tag 都真实存在，但 tag 指向的是**远端已有的旧 commit**，远端默认分支（当次为 `main`）没动，本次新增文件在远端全部 `Not Found`。成因是漏了端到端流程第 ③ 步的 push。判据不能是「release 在不在」，而必须是「远端默认分支的内容指纹（tree sha）等于本地发布树的 tree sha」，并抽查新文件确实可见。回查命令见端到端流程第 ⑥ 步。

**发布说明里的对比链接要核对**：`publish` 自动生成的 `**Full Changelog**: .../compare/<基线>...<新tag>` 基线可能指错（2026-11-11 实测指向上上版 `v5.16.3`，而真正的上一版是 `v5.17.0`）。先用 compare 端点确认基线有效（`status=ahead` 且 `total_commits` 合理），再按需修正说明文字，不要动 tag 与资产：

```bash
# 读当前说明，确认基线版本
gh api repos/<owner>/<repo>/releases/tags/vX.Y.Z --jq .body
# 验证候选基线（应返回 status=ahead）
gh api repos/<owner>/<repo>/compare/vPREV...vX.Y.Z --jq '.status + " " + (.total_commits|tostring)'
# 基线指错时只改说明文字：先取 release id，再 PATCH body
RID=$(gh api repos/<owner>/<repo>/releases/tags/vX.Y.Z --jq .id)
printf '%s' '{"body":"**Full Changelog**: https://github.com/<owner>/<repo>/compare/vPREV...vX.Y.Z"}' |
  gh api -X PATCH "repos/<owner>/<repo>/releases/$RID" --input -
```

### 8. 认证与网络

- **通路按当场探测结果选，没有「国内环境一律走代理」这回事**：2026-11-11 实测同一台机器上 git 直连被 reset、顶 IP 全断、只有本机代理可用，但 `gh` 直连 `api.github.com` 却是通的；另一天则直连可用、代理全关。按 `SKILL.md` 第 4 步的三行自检和 `github-push` 第 2 步选路，端口不要照抄任何固定值。
- 需要挂代理时：`git -c http.proxy=http://127.0.0.1:<当场探到的端口> ... push`；`gh` 与 REST 走 `HTTPS_PROXY`/`HTTP_PROXY` 环境变量。挂代理时**不要**再叠加 `--resolve` / `curloptResolve`，否则流量绕过代理。
- push 卡住（疑似认证等待）时先 `gh auth setup-git` 配置 credential helper。

## 版本说明

`gh skill` 是 preview 功能，需要较新的 gh CLI。**本机现为 gh 2.101.0，`gh skill` 及其全部子命令（install/list/preview/publish/search/update）均可用**；`ruleset`/`attestation`/`agent-task`/`licenses`/`preview` 等新命令也已就位。若其他环境 `gh skill` 报 `unknown command`：

```bash
# 检查本地版本
gh --version
# 升级 gh CLI（Windows 用 winget / 官网安装包）
winget upgrade GitHub.cli
# 升级后重新验证
gh skill --help
```

## 与其它子技能的关系

- 从 GitHub **发布/分享技能** 时，底层仍是 push 与 Release，走 `github-push`、`github-ops` 两条主线。
- 本子技能聚焦 `gh skill` 这一**技能管理专属命令**（安装/搜索/发布/更新 SKILL 技能）。

## 相关

- 访问与克隆：`github-access`；推送与认证：`github-push`；仓库运维：`github-ops`；搜索：`github-search`

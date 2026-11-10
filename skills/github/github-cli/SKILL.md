---
name: github-cli
description: "GitHub CLI 自身运维子技能——装在哪、登录谁、权限够不够、配置对不对、扩展与别名、内置帮助主题，以及账号级对象（gist 与 SSH/GPG 公钥，不挂在任何仓库上那类）。覆盖 gh auth（login/logout/refresh/setup-git/status/switch/token）、gh config（get/set/list/clear-cache）、gh alias（set/list/delete/import）、gh extension（browse/create/exec/install/list/remove/search/upgrade）、gh completion、gh licenses、gh preview、gh copilot、gh co 别名、gh help 的 8 个帮助主题、gh gist（clone/create/delete/edit/list/rename/view）、gh ssh-key 与 gh gpg-key（list/add/delete），共 43 条。触发关键词：gh 装在哪、gh 版本、gh 登录、gh auth、token 权限、scopes、切账号、gh 配置、gh 别名、gh 扩展、shell 补全、gh help、退出登录、gist、SSH 公钥、GPG 公钥、上传公钥。"
---

# GitHub CLI 自身运维（cli）

其它子技能都假定 gh 已经能用。这条线负责把"能用"确认到：哪个 gh、登录的是谁、权限够不够、配置对不对。主线依次是定位可执行文件、登录、校验账号与权限、交给 git、配置与别名、扩展，最后以帮助主题收口。

参数形态取自本机 gh 2.101.0 的 `gh <命令> --help`。

## 前置准备（只列材料）

- 一个 GitHub 账号；企业版还要实例域名（`gh` 默认打 `github.com`，靠 `-h/--hostname` 换）
- 若走 token 登录：已建好的 PAT，以及它该含的权限清单（`repo`、`read:org`、`workflow`、`project`、`admin:public_key` 按需）
- 本机 git 可用（`gh auth setup-git` 要改 git 的凭证helper 配置）

## 1 定位可执行文件与版本

**输入**：一个能跑 `gh` 的终端。

```bash
where gh 2>nul || which gh         # 本机实测：两条都无输出，即 gh 不在 PATH
ls "$USERPROFILE/AppData/Local/Programs/gh/bin/gh.exe"   # 直接按已知安装位找
gh --version                       # 若上一步无输出而这条却成功，说明 PATH 里有第三份，以它为准
```

**动作**：本机有两份 gh 安装（`C:\Users\贺新\AppData\Local\Programs\gh\bin\gh.exe` 与 `D:\WPS灵犀过程文件\gh\bin\gh.exe`，实测同为 2.101.0 (2026-09-15)、同为 42755384 字节；两份是**彼此独立的拷贝**（实测文件记录与所在卷都不同，不是链接），换版本要两份一起换，只换一份就会出现两个版本并存），2026-09-25 实测**两个目录都不在 PATH 里**（`where gh` 无输出）；**2026-11-10 复测用户 PATH 的最后一项已含 gh 的 bin 目录（写于当日 07:04）**，新进程 `where gh` 能解析到，但 07:04 之前启动的终端继承旧环境、裸敲 `gh` 仍报「无法识别」。两天的结论都是「不要赌 PATH」，只是原因不同。跨技能统一用变量指向一份：

```bash
export GH="$USERPROFILE/AppData/Local/Programs/gh/bin/gh.exe"    # 之后本文件里的 gh 都指它
"$GH" --version && "$GH" auth status
```

两处版本不一致时，先用带绝对路径的那份继续，别互相"更新"对方。

换版本时两份拷贝要一起换，换完用哈希确认一致（2026-09-25 升级后实测两份同为 2.101.0、同 42755384 字节、SHA-256 同为 `df050891…`）：

```bash
python -c "import hashlib,glob,os;f=[os.path.expanduser(r'~\AppData\Local\Programs\gh\bin\gh.exe')]+glob.glob(r'D:\WPS*\gh\bin\gh.exe');[print(hashlib.sha256(open(x,'rb').read()).hexdigest()[:16],x) for x in f]"
```

只换一份就会出现两个版本并存，而文档里的参数与 `--json` 字段是按某一份的 `--help` 写的，分叉之后校验会给出假绿。

**产出**：确定要用的 gh 绝对路径 + 版本号。

**出口**：`gh --version` 与绝对路径跑出的版本一致。若 `gh` 根本不识别，先用绝对路径跑通，再把该目录加进 PATH——不要靠重装解决 PATH 问题。

## 2 登录

**输入**：账号或 PAT。

```bash
gh auth login                      # 交互式：依次问主机、协议、浏览器还是 token
gh auth login --web                # 走浏览器 OAuth：终端给一次性代码，浏览器里确认
gh auth login --with-token         # 从 STDIN 读 PAT，无交互，适合脚本
echo "$PAT" | gh auth login --with-token    # 只在这条命令内展开，不要 echo 到日志
gh auth login -h <实例域名> -p ssh --scopes repo,workflow,project
```

**动作**：可选项一共这些——`-h/--hostname` 换实例；`-p/--git-protocol {ssh|https}` 定 git 用哪种协议；`-s/--scopes` 追加 OAuth 权限；`-w/--web` 开浏览器；`--with-token` 读 STDIN；`--skip-ssh-key` 跳过"生成并上传 SSH key"这一步；`--insecure-storage` 把凭证明文存文件而不是系统凭证库；`-c/--clipboard` 把一次性代码复制到剪贴板。

**产出**：凭证写入系统凭证库（或 `--insecure-storage` 时的明文文件）。

**出口**：进第 3 步用 `auth status` 验。`--insecure-storage` 只在系统凭证库不可用时用，用了就要接受本机任何进程都能读到明文这一后果。

## 3 校验登录状态与账号

```bash
gh auth status                        # 每个已知主机列出账号、协议、token 前缀与 scopes
gh auth status --json                 # 机器可读；先原样打一次看键名再套 --jq
gh auth status -a                     # 只看当前活跃账号
gh auth status -h <实例域名>           # 只查某个主机
gh auth switch --user <用户名>        # 同主机多账号时切活跃账号
gh auth switch -h <实例域名> --user <用户名>
```

**动作**：把 `auth status` 报出的 scopes 与任务要求对一遍。缺什么记下来，第 4 步补。

**产出**：活跃账号登录名、主机、协议、scopes 清单。

**出口**：任务需要的权限全在里面。`gh auth token` 会把 token 明文打到 stdout——**智能体会原样带回对话，因此本技能内不使用它**；要把 token 交给别的进程，让那个进程自己调 `gh auth token`，不要复制粘贴其输出。同理 `gh auth status -t/--show-token` 不要在会话里加。

## 4 补齐与收缩权限

```bash
gh auth refresh -s project                 # 追加 scope（浏览器确认一次）
gh auth refresh -s repo,read:org,workflow  # 一次补多个
gh auth refresh                            # 不带参数：只保证默认最小集
gh auth refresh --remove-scopes delete_repo     # 收缩；scope 移除是幂等的
gh auth refresh --reset-scopes                  # 回到该认证流的默认最小集
```

**动作**：`gh` 建 OAuth 凭证时的最小集是 `repo`、`read:org`、`gist`，这三个移不掉（help 明确写了）。若本机有多个账号，`refresh` 只作用于**活跃**账号：先 `auth switch` 过去、补完再切回来。

**产出**：`gh auth status` 里的 scopes 含目标权限。

**出口**：报 `403` 且提示 `Resource protected by organization SAML enforcement` 时，不是 scope 不够，是 SAML 授权过期——去网页侧重新授权，`refresh` 重试多少次都一样。

## 5 账号级对象：gist 与登录公钥

**输入**：账号已登录（第 2 到第 4 步），并且已经判清对象挂不挂在某个仓库上。挂在仓库上的（仓库级 secret/variable、deploy key、ruleset、autolink）走 github-ops；不挂的在本步。

```bash
gh gist list --limit 20 / gh gist view <id> --files
gh gist create repro.py --public            # 不带 --public 即 secret gist
gh gist clone <id-or-url> ./repro           # 拉到本地复现
gh gist rename <id> old.py new.py           # 改文件名
gh gist edit <id> / gh gist delete <id> --yes

gh ssh-key list / gh ssh-key add ~/.ssh/id_ed25519.pub --title "笔记本"
gh ssh-key add ~/.ssh/id_ed25519.pub --type signing      # 默认为 authentication
gh ssh-key delete <id> -y
gh gpg-key list / gh gpg-key add pub.asc --title "发布签名" / gh gpg-key delete <key-id> -y
```

**动作**：`gh ssh-key add` 的 help 首行原文是 "Add an SSH key to your GitHub account"，参数只有 `-t/--title` 与 `--type {authentication|signing}`，没有任何选仓库的参数——仓库级公钥是 `gh repo deploy-key`，两类对象不要混。gist 分 public 与 secret 两态，secret gist 只是不出现在列表页，拿到 URL 仍能读，别拿它当私密存储；`gh gist` 需要的 `gist` scope 在 gh 建凭证时的最小集里，通常不用补。

**产出**：`gh gist list`、`gh ssh-key list`、`gh gpg-key list` 里出现目标条目。

**出口**：公钥条目在 `list` 里能看到标题与指纹。撤销就 `delete`，但账号级公钥一删，所有靠它认证的机器和 CI 同时断，删前先确认没有别处在用；`gh gist delete` 不可恢复，贴进 issue 的 gist 链接会全部失效。

## 6 交给 git 用

**输入**：第 2、3 步已确认的账号。

```bash
gh auth setup-git                    # 把 gh 注册成 git 的 credential helper
gh auth setup-git -h <实例域名>       # 只配某个主机
gh auth setup-git -f -h <实例域名>    # 该主机从没登录过 gh 时，需与 --hostname 同时给
git config --global --get-regexp credential    # 核对写入结果
```

**动作**：`-f/--force` 必须与 `-h/--hostname` 一起用，单独 `gh auth setup-git -f` 不成——help 里对这条写明了。

**产出**：`git push`/`git clone` 走 HTTPS 时不再单独要凭证。

**出口**：`git config --global credential.https://github.com.helper` 输出含 `!...gh git-credential`。仍然提示输密码时，多半是 remote 用了 SSH 地址或另有 helper 覆盖，属 github-push 的网络与凭证主线。

## 7 登出与撤销

```bash
gh auth logout                          # 交互选主机与账号
gh auth logout -h <实例域名> -u <用户名>  # 指名登出
```

**动作**：`logout` 只删本机存的凭证，**不撤销 token**。要真正让 token 失效：网页上依次打开 Settings、Applications、GitHub CLI，点 Revoke Access（这一步会撤销你在所有设备上用 gh 生成的凭证，不可逆，先跟用户确认）。共享机器上还本机要清掉 `--insecure-storage` 落下的明文文件。

**产出**：`gh auth status` 不再列出该账号。

**出口**：明确区分两件事——"这台机器不再用这个账号"用 `logout`；"这个 token 不再有效"必须走网页撤销。只 `logout` 就以为凭证失效是错的。

## 8 配置 gh 自身行为

```bash
gh config list                     # 全部键值；--host <主机> 看单主机配置
gh config get <key> / gh config set <key> <value>
gh config set git_protocol ssh --host github.com     # 按主机设置
gh config set editor "code --wait"
gh config set prompt disabled      # 关掉交互提示，脚本环境用
gh config clear-cache              # 清 gh 的响应缓存
```

**动作**：`config set` 能认的键就四个（help 原文列出）：`git_protocol`（`ssh|https`）、`editor`（命令，可带参数）、`prompt`（`enabled|disabled`）、`pager`。`-h/--host` 三个子命令都支持，用于给不同实例配不同值。

不改配置、只在单次调用里覆盖，用环境变量（`gh help environment` 列出的这些）：

```bash
GH_TOKEN=<token> gh api user            # GH_TOKEN 优先于 GITHUB_TOKEN；GH_ENTERPRISE_TOKEN 配企业实例
GH_HOST=<实例域名> gh repo view         # 未指定主机时用它
GH_REPO=<owner>/<repo> gh pr list       # 等价于每条都带 -R
GH_DEBUG=api gh api user                # 把请求与响应打到 stderr，排 401/403/限速最好用（api 只看接口）
GH_FORCE_TTY=1 gh release list          # 管道里也要彩色表格；配 | cat 时可读
GH_PROMPT_DISABLED=1 gh pr merge 1 --squash   # 等价于 prompt disabled，脚本里防卡住
GH_CONFIG_DIR=<目录> gh auth status     # 换一套配置目录，做多账号隔离
GH_NO_UPDATE_NOTIFIER=1 gh --version    # 关掉升级提示；GH_PATH 用于 gh 找不到自身路径时
```

**产出**：`gh config list` 与预期一致。

**出口**：改完 `gh config get <key>` 回显新值。注意 `prompt disabled` 会让缺参数的命令直接报错而不是问——批量脚本里方便，手工排错时会掩盖问题。

## 9 别名

```bash
gh alias list                                   # 现有别名（别名存储文件由 gh 自己管理）
gh alias set pc 'pr checkout'                   # 之后可 gh pc 321
gh alias set bugs 'issue list --label=bugs'
gh alias set epicsBy 'issue list --author="$1" --label="epic"'    # $1 承接后续参数
gh alias set --shell igrep 'gh issue list --label="$1" | grep "$2"'   # 走 sh 解释器
gh alias set pc 'pr view' --clobber              # 覆盖同名别名
gh alias import aliases.yml / gh alias import -   # 从 YAML 文件或 STDIN 批量导入
gh alias delete pc / gh alias delete --all
```

**动作**：展开里含 `$1` 这类占位符时，后续参数按位插入；没有占位符则原样追加到末尾。以 `!` 开头即视为 shell 表达式。Windows 的 `cmd` 下参数要双引号；含引号的展开建议用 `gh alias set <名字> -`（STDIN）来定义，省掉转义坑。

**产出**：`gh alias list` 里有该条目。

**出口**：`gh <别名>` 行为与展开一致。导入的 YAML 顶层是 `别名: 展开` 的映射；`gh alias list` 的输出本身就是这个格式，可以在两台机器之间直接倒手。

## 10 扩展

```bash
gh extension list                                  # 已装（别名 gh ext ls）
gh extension search 关键词 --limit 50 --sort stars # 找现成的（默认按 star 取前 30）
gh extension search --owner github --license MIT   # 过滤；-w 在浏览器看
gh extension install <owner>/gh-<name>             # 装；也接受完整 URL（GHES 用）
gh extension install <owner>/gh-<name> --pin v1.2.0   # 锁到某个 release tag 或 commit
gh extension install <owner>/gh-<name> --force          # 已装则强制升级
gh extension upgrade <name> / upgrade --all --dry-run
gh extension exec <name> [args]                    # 显式调用扩展，跳过 PATH 查找
gh extension browse                                # 全屏交互界面增删扩展（按 ? 看键位，q 退出）
gh extension create <name>                          # 脚手架一个脚本型扩展
gh extension create <name> --precompiled=go         # 或预编译型：go / other
gh extension remove <name>                          # 卸载（别名 gh ext uninstall）
```

**动作**：装远程扩展时 gh 先看该仓库的 release 取预编译二进制，没有 release 才克隆仓库并找根目录同名可执行文件——`--pin` 对这两种情况分别是 tag 和 commit ref。装本地开发中的扩展用 `gh extension install .`，它会建符号链接，改了源码要自己重新构建可执行文件。

**产出**：`gh <扩展名>` 可直接调用。

**出口**：扩展是第三方代码，装之前确认仓库来源，锁版本（`--pin`）比追最新可控。`gh copilot` 不算扩展：它在本机没有 Copilot CLI 时下载到 `AppData\Local\GitHub CLI\copilot`，`gh copilot -- --help` 把参数交给 Copilot，`gh copilot --remove` 删掉下载的那份；给 Copilot 的参数一律放在 `--` 之后，否则被 gh 吃掉。

## 11 补全与内置帮助（遇到不确定的用法先查这里）

```bash
gh completion -s bash              # 输出补全脚本：{bash|zsh|fish|powershell}
# PowerShell 接入方式（help 原文）：把下面这行放进 $profile
#   Invoke-Expression -Command $(gh completion -s powershell | Out-String)
gh help reference                  # 本机 gh 的全量命令参考
gh help exit-codes                 # 退出码含义（脚本里判错要看）
gh help formatting                 # --json/--jq/--template 的用法
gh help environment                # 可用的环境变量（GH_TOKEN、GH_HOST、GH_BROWSER、EDITOR…）
gh help actions                    # 工作流、run、cache 的背景说明
gh help telemetry                  # 遥测开关与含义
gh help mintty                     # 在 MinTTY（Git Bash 常用终端）里的已知问题
gh help accessibility              # 无障碍行为
gh licenses                        # 本版 gh 依赖的第三方库许可证
```

**动作**：`gh help` 的帮助主题固定这 8 个（accessibility、actions、environment、exit-codes、formatting、mintty、reference、telemetry）。这 8 条是**说明文档而不是命令**：`gh help <主题>` 后面没有子命令、没有位置参数，只有 `--help` 一个参数可用；其中 accessibility、actions、telemetry 三条在本机连 `gh <主题>` 裸写也能跑出同一份文本（实测退出码 0），但为与其它命令区分，本技能一律按 `gh help <主题>` 写。任何一条命令看不明白，用 `gh help <命令> <子命令>` 取权威说明，输出与 `gh <命令> <子命令> --help` 同源。

gh 自带的简写不属于用户别名，`gh alias list` 查不到，权威来源有两处：命令自身 help 的 `Aliases` 段，以及 `gh help reference` 里该命令条目下的 `Aliases` 行。实测存在的简写：`gh co` = `gh pr checkout`（reference 里单列一条 `## gh co`，正文只写 "Alias for \"pr checkout\""；该命令自己的 Aliases 段只列 `gh pr co`，参数 `-b` 指定本地分支名、`--detach`、`-f` 重置已有同名本地分支、`--recurse-submodules`）、`gh ext` / `gh extensions` = `gh extension`、`gh cs` = `gh codespace`、`gh rs` = `gh ruleset`、`gh at` = `gh attestation`；各 `list` 子命令普遍带 `ls`（`gh codespace ls` 与 `gh cs ls`、`gh ruleset ls` 与 `gh rs ls`、`gh config ls`、`gh repo ls`、`gh cache ls`）。

**产出**：拿到权威解释，写回对应子技能的步骤里。

预览通道单独说明：`gh preview` 在 2.101.0 下仍然只有 `prompter` 一条子命令，`gh preview prompter` 依次跑全部交互提示器的测试程序，`gh preview prompter <类型>` 只跑一种，类型取 `select`、`multi-select`、`multi-select-with-search`、`input`、`password`、`confirm`、`auth-token`、`confirm-deletion`、`input-hostname`、`markdown-editor`。改交互相关的东西（例如 `--web`、编辑器、删除确认）之前先跑一次对应类型，确认终端能正常渲染，比在真实命令上试错便宜。该命令组是 preview 状态，参数与存在性都可能随版本变。

**出口**：`gh help reference` 与本机各子命令 help 同源，版本随 gh 走。gh 升级后要把受影响的子技能文档段落重跑一次 help 对照，不要假设升级后的参数集与文档一致。本机升级途径是官方 release 的 `gh_<版本>_windows_amd64.zip`（对照同版本 `checksums.txt` 校验后换 exe），`gh` 自己没有 `upgrade` 子命令，本机也没有 winget；两份拷贝要一起换，换法与哈希核对见第 1 步。

## 红线

- `gh auth token` 与 `gh auth status -t` 会把 token 打进 stdout，会话里不要执行；诊断凭证问题用 `gh auth status`（不带 `-t`）的 scopes 与用户名信息就够。
- `gh auth logout`、`gh alias delete --all`、`gh extension remove`、`gh config clear-cache` 改的都是本机状态，影响同一台机器上的其它工作流，执行前告知用户。
- `gh gist delete`、`gh ssh-key delete`、`gh gpg-key delete` 删的是账号在服务端的对象，删掉后贴出去的 gist 链接失效、靠该公钥认证的机器与 CI 立即断，执行前列出受影响对象交用户确认。
- 网页侧的 Revoke Access 会撤销 gh 在**所有设备**上生成的凭证，属最后手段，必须用户确认。
- 扩展与 `gh copilot` 会引入第三方或额外下载的可执行代码；来源、版本（`--pin`）与下载时机先讲清楚再装。

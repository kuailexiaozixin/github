---
name: github-codespace
description: "GitHub Codespaces 云端开发环境子技能——用 gh codespace 建环境、进环境干活、搬文件、看端口、查日志、重建、回收。覆盖 create/list/view/code/jupyter/ssh/cp/logs/rebuild/edit/stop/delete 与 ports 及其 forward、visibility 子命令，共 15 条。触发关键词：codespace、codespaces、云端开发环境、远程开发、开个云环境跑、VS Code Web、JupyterLab、codespace 计费、端口转发、ports visibility、gh codespace cp、清理 codespace。"
---

# GitHub Codespaces 云端环境（codespace）

Codespace 是一台按使用时长计费的云端开发机。主线依次是建环境、查状态、进环境干活、搬文件、看端口、查日志、重建、回收。

参数形态逐条取自本机 gh 2.101.0 的 `gh codespace <子命令> --help`。两条贯穿全部子命令的定位规则，先记住：

- **选哪个环境**用 `-c, --codespace <名称>`；只有 `create` 没有这个参数（它负责产出名称）
- **按仓库筛**用大写 `-R, --repo <owner>/<repo>`；小写 `-r` 在 `cp` 里另有含义（`--recursive`）
- 组织名下的环境要配 `-o, --org <组织登录名>` 加 `-u, --user <用户名>`，单用 `-c` 找不到（`-o/-u` 只有 `list`、`stop`、`delete` 支持）
- `codespace` 有别名 `cs`，`list` 有别名 `ls`，help 示例本身就用 `gh cs view`

## 前置准备（只列材料）

- 目标仓库与分支名，以及自己在该仓库的写权限
- 仓库内的 `.devcontainer/devcontainer.json`；没有时创建会走默认镜像，需要先定用什么镜像
- 账号已开通 Codespaces 且预算未超（余额与用量 gh 查不到，在网页 Settings 的 Codespaces 页看）

## 1 建环境，拿到环境名

```bash
gh codespace create -R <owner>/<repo> -b <branch> -m <机器名> -l SouthEastAsia \
  --idle-timeout 30m --retention-period 1d --default-permissions
```

- `-m, --machine` 决定核数内存；help 不列可选机型，不确定时用 `-w, --web` 在浏览器里挑。`-w` 与 `--display-name`、`--idle-timeout`、`--retention-period` 四个参数互斥（help 原文：cannot be used with --display-name, --idle-timeout, or --retention-period）
- `-l, --location` 只有 `EastUs|SouthEastAsia|WestEurope|WestUs2` 四个值，不填则自动选；国内连 `SouthEastAsia` 延迟最低
- `--idle-timeout` 空闲多久自动停机（例 `10m`、`1h`），`--retention-period` 停机后保留多久再自动删除（时长写法同上，help 标注上限 30 天）
- `-d, --display-name` 最长 48 字符，用于给自己区分多个环境；`-s, --status` 会打印 postCreateCommand 和 dotfiles 的执行状态，首次建环境时加上它能看到构建卡在哪
- `--default-permissions` 直接接受 devcontainer 申请的权限，省掉交互确认；需要最小权限时不要加它，逐条看提示
- `--devcontainer-path` 用于一个仓库里有多套 devcontainer 配置的情况

产出：回显环境名，形如 `silly-cat-1a2b3c`。后面每一步都靠它定位，先记下来。
出口：跑第 2 步的 `list`，能看到这个名字。若状态是 `Failed`，先用第 6 步的 `logs` 定位是镜像构建还是生命周期脚本失败，再决定 `rebuild` 还是 `delete` 重建——重复 `create` 只会多出若干个占配额的环境。

## 2 查环境

```bash
gh codespace list
gh codespace list --json name,state,machineName,repository,lastUsedAt --jq '.[] | select(.state=="Available")'
gh codespace list -R <owner>/<repo>          # 只看某仓库
gh codespace list -L 100                     # 默认只列 30 个，清理前放大
gh codespace list -w                          # 在浏览器里看；help 注明不能与 -o/-u 同用
gh codespace view -c <名称>
gh codespace view -c <名称> --json displayName,state,idleTimeoutMinutes,retentionPeriodDays,machineName,prebuild
```

`list`/`view`/`ports` 的可用 JSON 字段各不相同，写错会报 `Unknown JSON field` 并把候选列出来，照列的改即可。本机 gh 2.101.0 的实际清单：

- `list`：`createdAt displayName gitStatus lastUsedAt machineName name owner repository state vscsTarget`
- `view`：`billableOwner createdAt devcontainerPath displayName environmentId gitStatus idleTimeoutMinutes lastUsedAt location machineDisplayName machineName name owner prebuild recentFolders repository retentionExpiresAt retentionPeriodDays state vscsTarget`

注意保留期在 `view` 里是 `retentionPeriodDays`（天）与 `retentionExpiresAt`（到期时刻），创建时用的 `--retention-period` 是时长；没有 `retentionTimeoutMinutes` 这个字段。
出口：拿到后续要用的 `-c <名称>`。一个仓库只有一个环境时可以用 `-R <owner>/<repo>` 免记名字；同仓库有多个环境时 `-R` 会要求消歧，此时必须用 `-c`。

## 3 进环境干活

```bash
gh codespace ssh -c <名称>                            # 进交互 shell
gh codespace ssh -c <名称> -- -i ~/.ssh/my_key        # ssh 参数放 -- 之后（-i 指定密钥）
gh codespace ssh -c <名称> --profile <profile名>       # 多环境共用 SSH 配置时区分
gh codespace ssh -c <名称> --config > ~/.ssh/codespaces  # 导出 OpenSSH 配置
gh codespace code -c <名称>                            # 本机 VS Code 连上去
gh codespace code -c <名称> --insiders                 # Insiders 版
gh codespace code -c <名称> -w                         # 浏览器里的 VS Code，本机不用装
gh codespace jupyter -c <名称>                         # 打开该环境的 JupyterLab
```

- 用法是 `ssh [<flags>...] [-- <ssh-flags>...] [<command>]`：`--` 之后的参数交给 OpenSSH，最后的裸参数才是要在远端执行的命令
- `--config` 输出的是每台 codespace 一段的 OpenSSH 配置；help 给的接法是 `printf 'Match all\nInclude ~/.ssh/codespaces\n' >> ~/.ssh/config`，配好后可以直接用 `ssh` 而不必经 `gh`
- 密钥选取顺序（help 原文列出）：先看 `--` 之后用 `-i` 指定的，其次已存在的自动密钥，再次 `ssh -G` 配置里的第一对有效密钥，最后才新建自动密钥
- `--server-port` 指定 SSH 端口（`0` 表示自动选空闲端口）；连不上时用 `-d --debug-file <路径>` 落一份日志
- 前提：镜像里预装了 SSH server。自定义镜像没有时要装 openssh-server，或在 `devcontainer.json` 里加 `"features": { "ghcr.io/devcontainers/features/sshd:1": { "version": "latest" } }`；基于 Debian 系默认镜像的环境一般已具备
- `code` 的三个入口（本机 / `--insiders` / `-w` 浏览器）与 `jupyter` 都只唤起客户端：`code` 的参数是 `-c/-R/--repo-owner/--insiders/-w`，`jupyter` 只有 `-c/-R/--repo-owner`，没有别的可选项

出口：`ssh` 后 `pwd` 落在 `/workspaces/<repo>`；`code -w` 与 `jupyter` 会在浏览器打开。这三条都只在远端生效，本地不落文件（`--config` 除外，它输出到 stdout）。

## 4 本地与远端之间搬文件

远端路径用字面量前缀 `remote:` 标识，它按远端用户的**主目录**解析（不是 `/`）。第一个参数是源、最后一个是目标，与 `cp` 一致。

```bash
gh codespace cp -c <名称> ./data.csv 'remote:/workspaces/<repo>/'       # 上传，目标以 / 结尾即目录
gh codespace cp -c <名称> 'remote:/workspaces/<repo>/out/' ./out/       # 下载
gh codespace cp -c <名称> -r 'remote:/workspaces/<repo>/src' ./src/     # 目录必须加 -r/--recursive
gh codespace cp -c <名称> -e 'remote:~/*.go' ./gofiles/                 # 远端通配：加 -e 才会展开
gh codespace cp -c <名称> -e -- -F ~/.ssh/codespaces_config 'remote:~/*.go' ./gofiles/   # -- 后接 scp 参数
```

- `-r, --recursive`：任一源是目录就必须带，漏了直接报错，不会静默漏文件
- `-e, --expand`：默认远端路径按字面处理；只有要在远端展开 `~`、花括号、glob、环境变量、反引号时才加。help 明确警告：不要对不受信任用户提供的参数使用它（会在远端执行展开）
- `-p, --profile`：指定 SSH profile
- 首次运行 `cp` 会往本地 `~/.ssh` 里生成一对密钥用于连该 codespace，这是它的默认行为

出口：`gh codespace ssh -c <名称> -- ls -l remote路径` 能看到刚传的文件，或本地目标目录出现文件且大小不为 0。

## 5 起服务与对外访问

`ports` 本身列出已转发端口，它还带两条子命令：`forward` 开转发、`visibility` 改可见性。

```bash
gh codespace ports -c <名称>
gh codespace ports -c <名称> --json label,sourcePort,visibility,browseUrl --jq '.[] | "\(.sourcePort) \(.visibility) \(.browseUrl)"'
gh codespace ports forward -c <名称> 8000:8000 3000:5173   # 远端端口:本地端口，可一次给多组
gh codespace ports visibility -c <名称> 80:org 3000:private 8000:public   # help 原样示例
```

- `forward` 的取值形态是 `<remote-port>:<local-port>...`，`visibility` 是 `<port>:{public|private|org}...`，端口号取的是远端端口
- 产出：`ports` 回显已转发端口、可见性（`private`/`org`/`public`）和可直接打开的 `browseUrl`
- 出口：`ports` 里新端口的 `browseUrl` 能打开；把 `browseUrl` 发给要看效果的人，比自己开隧道省事

改可见性影响的是暴露面：`org` 让组织成员可访问、`public` 让任何拿到链接的人可访问，等于把未发布代码跑给外部看，改之前先经用户确认。某个端口当前的实际值以 `ports` 回显的 `visibility` 字段为准，不要凭默认值假设。

## 6 查日志（创建失败、连不上时用）

```bash
gh codespace logs -c <名称>
gh codespace logs -c <名称> -f          # 持续跟踪，边创建边看
```

出口：能判断失败发生在哪一段——拉镜像、`.devcontainer` 生命周期脚本、还是网络。生命周期脚本报错要回仓库改 `devcontainer.json`，然后走第 7 步重建才生效。

## 7 改配置与重建

```bash
gh codespace edit -c <名称> -d "跑评测"            # 改显示名
gh codespace edit -c <名称> -m <机器名>            # 改规格
gh codespace rebuild -c <名称>                     # 按工作目录的 dev container 重建
gh codespace rebuild -c <名称> --full              # 全量重建，额外清掉缓存的 Docker 镜像
```

`edit` 的可选项只有 `-d/--display-name` 与 `-m/--machine`（help 的 FLAGS 段就这两条业务参数）；空闲停机时长（`--idle-timeout`）和保留期（`--retention-period`）创建后改不了——建的时候就要把这两个值设小。改机型是否受环境当前状态限制，help 没有写明，实测报错时先 `stop` 再 `edit -m`。
`rebuild` 的 help 说明：代码与当前改动会保留，环境按 dev container 重新创建；`--full` 在此基础上再清掉缓存镜像，也就是连镜像构建重来。
出口：`gh codespace view -c <名称>` 显示新值。改 `.devcontainer` 后必须重建才生效；`--full` 前确认改动已提交或已用第 4 步备份到本地。

## 8 回收

```bash
gh codespace stop -c <名称>                        # 停机：磁盘内容保留，不再计费但占配额
gh codespace stop -R <owner>/<repo>                 # 该仓库只有一个环境时可按仓库停
gh codespace delete -c <名称>                       # 删除：不可恢复
gh codespace delete -R <owner>/<repo> --all         # 删该仓库全部环境
gh codespace delete --all --days 7                  # 清理 7 天没用过的，日常收口用这条
gh codespace delete -c <名称> -f                    # 跳过"有未保存改动"的确认
```

`-f, --force` 会连带丢弃环境里未提交的改动，只在确认无可用内容时用。组织名下批量清理要加 `-o <org> -u <user>`。
出口：`gh codespace list` 里不再有该名字。`--all` 和 `--days` 属批量删除，执行前先跑 `gh codespace list -L 100` 把将被删的列出来交用户确认，再执行。

## 红线

- 存活即计费。任务收尾必须 `stop` 或 `delete`；防疏漏靠建时的 `--idle-timeout`，事后改不了。
- `rebuild --full`、`delete`、`stop`、`--all`、`--days` 都会丢工作或影响别的环境，逐条确认，不用通配一把梭。
- 端口 `public` 可见性、`--default-permissions` 会扩大仓库密钥与代码的暴露面，改前先问。

## 出口：取权威参数

```bash
gh codespace --help
gh codespace create --help
```

命令在本机不在 PATH 时，用绝对路径调用（路径见 github-push 的「gh 可执行文件在哪」）。

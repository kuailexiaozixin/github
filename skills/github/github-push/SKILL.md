---
name: github-push
description: "GitHub 推送与认证子技能——把本地提交可靠地交到远端仓库并核对收到。覆盖 gh 可执行文件位置、凭证与 scope 核对、直连/本地代理/多 IP 重试三条通路的取舍、push_repo.sh 用法与退出码、推送结果的双通道核对、失败分诊。触发关键词：push/推送、git push 失败、多IP推送、GitHub 认证、gh auth、push_repo.sh、上传到 GitHub、提交代码、推送后远程没变化。"
---

# GitHub 推送与认证（push）

本地已 commit，要把提交交到 `github.com` 上并确认远端真的收到了。难点不在 git 命令，而在两件事：一是本机 `gh` 与本地代理是否真的可用（2026-09-25 实测：`gh` 不在 PATH，代理端口无一在监听），二是推送通道与核对通道是两个独立域名，一条不通不代表另一条不通。

认证动作本身（登录、补 scope、配 git 凭证助手、别名）归 `github-cli`，本技能只写推送主线。

## 前置准备（只列材料）

- 一份可用的 `gh` 可执行文件，路径见第 0 步（实测两处安装都不在 PATH）
- `GITHUB_TOKEN` 用户环境变量：`github-push/scripts/push_repo.sh` 只认环境变量与注册表 `HKCU\Environment`，不读任何文件。2026-09-25 实测本机该变量长度 40、前缀 `gho_`
- 目标仓库全名 `owner/repo`，且当前凭证对它有所写权限
- 待推送的本地仓库目录，提交已落在某个分支上

## 0 确认 gh 在哪

**输入**：一台按本技能装过 gh 的 Windows 机器。

**动作**：`gh` 在这台机器上不能直接敲。实测 `command -v gh`（Git Bash）与 `where gh`（cmd）都返回空，两份安装都不在 PATH：

- `C:\Users\<用户名>\AppData\Local\Programs\gh\bin\gh.exe`，gh version 2.101.0 (2026-09-15)——常规调用用这份
- `D:\WPS灵犀过程文件\gh\bin\gh.exe`，与上一份同版本、同字节数 42755384（2026-09-25 两份同为 2.101.0，SHA-256 前缀同为 `df050891`），是解压副本；上一级目录 `D:\WPS灵犀过程文件\gh\gh.zip`（14938517 字节，2026-09-06）仍是升级前 2.97.0 的原始包，与现在的 exe 已不对应，不要拿它回滚。

先固定一个变量再执行本技能所有命令，避免每条命令重复路径：

```bash
export GH="$USERPROFILE/AppData/Local/Programs/gh/bin/gh.exe"   # 含中文用户名路径也能解析
"$GH" --version                                                  # 打印 gh version 2.101.0
```

**产出**：`$GH` 指向一份确认可执行的 gh。

**出口**：`"$GH" --version` 打印版本即通过。两份安装版本不一致时，用绝对路径那份继续，不要拿一份去覆盖另一份。跨技能文档里提到的「gh 可执行文件在哪」都指本节。

## 1 核对凭证与 scope

**输入**：第 0 步的 `$GH`。

**动作**：先看账号与权限，再看 git 是否能复用这份凭证。用 JSON 形态读，输出里天然不含 token 值：

```bash
"$GH" auth status --json hosts
```

2026-09-25 实测输出为 `github.com` 下两条记录、同一账号，字段含 `state`、`active`、`login`、`tokenSource`、`scopes`、`gitProtocol`：环境变量 `GITHUB_TOKEN` 那条 `active: true`，钥匙串那条 `active: false`，`scopes` 为 `gist, read:org, repo, workflow`。

要推的是受保护分支或私有仓库，`repo` 已在；要动看板（`github-project`）需要 `project`，当前不在——补法见 `github-cli` 的 `gh auth refresh -s project`。

**产出**：活跃账号名、凭证来源（`GITHUB_TOKEN` 还是 keyring）、scope 清单。

**出口**：`state` 为 `success` 且 scope 覆盖本次动作。缺 scope 就回 `github-cli` 补，不要改用网页上传绕过。

禁止在本技能任何步骤里执行 `gh auth token` 或 `gh auth status -t`：两者都会把 token 明文写进终端输出与后续日志。上面这条 `--json hosts` 是等价的替代读法。

## 2 选通路

三条通路按下面的判据取一条，**任一命中即触发，不并行尝试**：

- `git ls-remote <仓库地址> HEAD` 能打印 SHA：直连可用，走第 3 步。
- 直连不通且本地代理在监听：走第 3 步的代理前缀写法。代理是否在监听要探，不要照抄端口：

  ```bash
  python -c "import socket;print('OPEN' if socket.socket().connect_ex(('127.0.0.1',7897))==0 else 'CLOSED')"
  ```

  2026-09-25 实测本机 7897、7890、10808、10809、1080 五个端口全部 CLOSED。旧文档里"走 7897 最可靠"的写法在有代理客户端的机器上成立，在这台机器上不成立，所以本步把它降为"探测通过才用"。
- 直连与代理都不通：走第 4 步的多 IP 脚本。

**产出**：一个确定的通路。

**出口**：进入对应步骤。连续两次同一通路失败就换下一条，不要重复重试同一通路碰运气。代理为何从"默认最可靠"降级为"探测通过才用"，见 `references/push.md`。

## 3 直连或代理推送

**输入**：仓库目录、分支名。

**动作**：分支名先问出来，不要假定叫 `main`——2026-09-25 实测本机 `git init` 出来的新仓库默认分支是 `master`，此时 `push -u origin main` 报 `src refspec main does not match any`。

```bash
git -C <repo> branch --show-current                 # 空仓库（无提交）时此行为空
git -C <repo> push -u origin <分支>
git -C <repo> push origin :<要删除的远端分支>        # 删远端分支属破坏性动作，先确认
```

代理在监听时，同一条命令加前缀：

```bash
HTTPS_PROXY=http://127.0.0.1:7897 git -C <repo> push -u origin <分支>
```

推送标签：

```bash
git -C <repo> tag -a v1.0.0 -m "v1.0.0" && git -C <repo> push origin v1.0.0
```

**产出**：git 回显的 `<旧SHA>..<新SHA> <分支> -> <分支>`。

**出口**：进入第 5 步核对。回显里的 SHA 只是本地计算结果，未经远程确认。

## 4 多 IP 重试推送

**输入**：仓库目录、`owner/repo`、分支（默认 `main`）。

**动作**：

```bash
bash "<技能根目录>/github-push/scripts/push_repo.sh" <repo本地目录> <owner/repo> [分支]
# 技能根目录 = 本仓库里 github/ 那一层，例：C:\Users\贺新\AppData\Roaming\WPS 灵犀\serverdir\user_skills\github
```

脚本内部按四步走：从环境变量或注册表取 token（取不到打印 `NO_TOKEN`）；用 `--resolve github.com:443:<ip>` 逐个探 IP 池；对每个可达 IP 以 `git -c url.https://<ip>/.insteadOf=https://github.com/ -c http.sslVerify=false -c http.version=HTTP/1.1 -c "http.https://<ip>/.extraheader=AUTHORIZATION: basic <base64>" push` 推送；任一成功即停。

IP 池就是这一份数据，随 `references/access.md` 的按 host IP 表一起复核，不在两处各自维护。

退出码即脚本的产出：

| 退出码 | 含义 | 下一步 |
|---|---|---|
| 0 | `PUSH_OK via <ip>`，已推送 | 进第 5 步核对 |
| 2 | `NO_DIR`，目录不存在或不是仓库 | 校正第一个参数 |
| 3 | `NO_REACHABLE_IP`，IP 池全不可达 | 回 `references/access.md` 重测 IP 或改走代理 |
| 4 | `NO_TOKEN` | 回第 1 步确认 token 来源 |
| 5 | `ALL_IP_FAILED`，连上了但每个 IP 都推失败 | 多为权限或保护分支，进第 6 步 |

**产出**：上述退出码之一。

**出口**：脚本用 `-c` 传配置，不写入仓库配置文件，无需清理；代价是这条路径关闭了 TLS 证书校验（IP 与域名不匹配），只在直连不通时使用。为什么必须关校验、为什么凭证走 extraheader 而不拼进 URL，见 `references/push.md`。

## 5 核对远程真的收到

**输入**：本地分支与 `owner/repo`。

**动作为什么是两条通道**：git 走 `github.com`，核对走 `api.github.com`，两个域名解析与故障互相独立。推送那条不通时读取这条通常还能用，所以核对不依赖 `git fetch`。

```bash
git -C <repo> rev-parse HEAD
"$GH" api repos/<owner>/<repo>/commits/<分支> --jq .sha
```

2026-09-25 实测：`git ls-remote https://github.com/cli/cli HEAD` 与 `gh api repos/cli/cli/commits/trunk --jq .sha` 返回同一个 SHA `b6770c8bc54c72e74e785c307850446b8e10be9d`，两条通道读到的是一致的。核对时分支名要用目标仓库真实存在的分支——同一次实测里 `commits/main` 对 `cli/cli` 返回 422 `No commit found for SHA: main`，因为该仓库默认分支是 `trunk`（用 `gh api repos/<owner>/<repo> --jq .default_branch` 先问出来）。

**产出**：两个 40 位 SHA。

**出口**：相等即本轮推送完成。`gh api` 本身连不上时，按 github-access 第 6 步的升级顺序判定，确认是 IP 问题后用顶 IP 的 curl 取同一端点（写法与 IP 表在 `references/access.md` 第四节）。

## 6 失败分诊

按报错形态定位，以下判据任一命中即触发对应动作：

- `src refspec <分支> does not match any`：本地没有这个分支。空仓库先 `git commit`，分支名不同则用 `git branch --show-current` 的真实值或 `git branch -m <旧> main` 改名。
- `Permission denied (publickey)`：remote 是 SSH 地址而密钥没配。改用 HTTPS 地址（`git remote set-url origin https://github.com/<owner>/<repo>.git`）或按 `github-cli` 配 SSH。
- 403/401 或 `Write access to repository not granted`：凭证或权限问题，网络是通的。回第 1 步核对 `login` 与 `scopes`；确认是协作者而非只读。
- `remote: error: GH006: Protected branch update failed`：目标分支有保护规则。先看 `gh ruleset check <分支> --repo <owner>/<repo>`（见 `github-ops` 第 6 步），不要改用 force push 绕。
- `Connection reset` / `Recv failure` / `RPC failed` / 超时：网络层，回第 2 步换通路。
- `fatal: unable to access ... Could not resolve host`：DNS。按 `references/access.md` 的重测脚本换 IP。
- 后台执行时找不到仓库：后台 shell 的工作目录会被重置，`gh repo create`、`gh release create` 一律显式带 `-R <owner>/<repo>`。

## 红线

- 不使用 `--no-verify` 跳过本地钩子，不使用 `git push --force` / `--force-with-lease` 覆盖远端，除非用户明确点名要，且执行前说明会丢哪些提交。
- token 值不打印、不写入任何文件、不在智能体之间传阅。需要它时用环境变量，不回显。
- 删除远端分支、删除已发布 tag、覆盖已发布 release 资产，都在执行前向用户确认。

## 相关

`github-cli` 管认证与 gh 自身配置；`github-access` 管读取方向与 IP 数据（`references/access.md`）；`github-ops` 管推送之后的 release、分支保护与仓库设置。

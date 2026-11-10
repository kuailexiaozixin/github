---
name: github-push
description: "GitHub 推送与认证子技能——把本地提交可靠地交到远端仓库并核对收到。覆盖 gh 可执行文件位置、凭证与 scope 核对、直连/本地代理/多 IP 重试三条通路的取舍、push_repo.sh 用法与退出码、推送结果的双通道核对、失败分诊。触发关键词：push/推送、git push 失败、多IP推送、GitHub 认证、gh auth、push_repo.sh、上传到 GitHub、提交代码、推送后远程没变化。"
---

# GitHub 推送与认证（push）

本地已 commit，要把提交交到 `github.com` 上并确认远端真的收到了。难点不在 git 命令，而在两件事：一是本机 `gh` 与本地代理是否真的可用（**2026-11-10 复测**：`gh` 目录已在用户 PATH 里但旧终端拿不到、7897 在监听、git 全局配置写死了走该代理；2026-09-25 那天则是都不在 PATH、五个端口全关），二是推送通道与核对通道是两个独立域名，一条不通不代表另一条不通。

认证动作本身（登录、补 scope、配 git 凭证助手、别名）归 `github-cli`，本技能只写推送主线。

## 前置准备（只列材料）

- 一份可用的 `gh` 可执行文件，路径见第 0 步（2026-11-10 复测：目录已进 PATH，但旧终端仍取不到，故一律按绝对路径绑定）
- `GITHUB_TOKEN` 用户环境变量：`github-push/scripts/push_repo.sh` 只认环境变量与注册表 `HKCU\Environment`，不读任何文件。2026-09-25 实测本机该变量长度 40、前缀 `gho_`，2026-11-10 复测同形。**技能根目录 `github/.env` 里那枚是另一个 token（前缀 `ghp_`、只读 classic PAT），脚本不读它**，别拿它当推送凭证
- 目标仓库全名 `owner/repo`，且当前凭证对它有所写权限
- 待推送的本地仓库目录，提交已落在某个分支上

## 0 确认 gh 在哪

**输入**：一台按本技能装过 gh 的 Windows 机器。

**动作**：**先按绝对路径绑变量，别赌 PATH。** 2026-11-10 复测：用户 PATH 的最后一项已是 `C:\Users\贺新\AppData\Local\Programs\gh\bin`（写于当日 07:04），新进程 `where gh` 解析得到；但 07:04 之前启动的终端（PowerShell 会话、IDE 内置终端）继承的是旧环境，裸敲 `gh` 仍报「无法将 gh 项识别为 cmdlet」。**「PATH 里有了」与「当前窗口能用」是两件事**，而当前窗口属于哪一类无法自证，所以一律绑绝对路径，两条分支都成立。2026-09-25 那天两条命令都是空输出，结论相同、原因不同。两份安装：

- `C:\Users\<用户名>\AppData\Local\Programs\gh\bin\gh.exe`，gh version 2.101.0 (2026-09-15)——常规调用用这份
- `D:\WPS灵犀过程文件\gh\bin\gh.exe`，与上一份同版本、同字节数 42755384（SHA-256 前缀同为 `df050891`，2026-11-10 复核仍一致），是解压副本。同目录的 `gh.zip` 是升级前的旧包，与现在的 exe 不对应，别拿它回滚。

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

2026-09-25 实测输出为 `github.com` 下两条记录、同一账号，字段含 `state`、`active`、`login`、`tokenSource`、`scopes`、`gitProtocol`：环境变量 `GITHUB_TOKEN` 那条 `active: true`，钥匙串那条 `active: false`，`scopes` 为 `gist, read:org, repo, workflow`。2026-11-10 复测同形（两条都 `active` 各一、scope 未变）。

**`state` 是 `error` 时不要直接判成「token 失效」。** 2026-11-10 实测：直连状态下两条都是 `state: "error"`、`login` 为空串、`error` 字段写着 `dial tcp 140.82.121.5:443 ... timeout`，人读的输出却只印一句「The token in GITHUB_TOKEN is invalid」——**同一份凭证挂上 `HTTPS_PROXY` 后立刻变 `state: "success"`、`login: kuailexiaozixin`**。所以读 `--json hosts` 时要看 `error` 字段里的原因，而不是只看 `state`：

| `error` 里是什么 | 含义 | 处置 |
|---|---|---|
| 含 `dial tcp` / `timeout` / `connection refused` | 网络没通，凭证未验证 | 回第 2 步选通路，**不要**重新登录或 refresh |
| 空，`login` 有值 | 正常 | 继续核 scope |
| 含 `401` / `Bad credentials` | 凭证真的失效 | 走 `github-cli` 第 2 步重新登录 |

要推的是受保护分支或私有仓库，`repo` 已在；要动看板（`github-project`）需要 `project`，当前不在——补法见 `github-cli` 的 `gh auth refresh -s project`。

**产出**：活跃账号名、凭证来源（`GITHUB_TOKEN` 还是 keyring）、scope 清单。

**出口**：`state` 为 `success` 且 scope 覆盖本次动作。缺 scope 就回 `github-cli` 补，不要改用网页上传绕过。

禁止在本技能任何步骤里执行 `gh auth token` 或 `gh auth status -t`：两者都会把 token 明文写进终端输出与后续日志。上面这条 `--json hosts` 是等价的替代读法。

**写操作前的凭证类型核对（2026-11-10 补，避免拿错 token 白跑一遍）**：`X-OAuth-Scopes` 为空**不等于**细粒度 PAT——零 scope 的 classic PAT 同样返回空。判别只看前缀：`ghp_` classic PAT、`github_pat_` 细粒度 PAT、`gho_` OAuth token。技能根目录 `github/.env` 那枚是零 scope 的 `ghp_`，**只用于读公开仓库与提升额度，禁止 export 成 `GITHUB_TOKEN` 去做建仓 / 推送 / 发 release**；拿它发请求时 `GET /user` 返回 200，写端点却一律 404。只读核对写法（不打印 token 值；IP 用 `references/access.md` 第一节当日可用的 api 前端，或改挂 `HTTPS_PROXY`）：

```bash
curl -s -D - -o /dev/null --connect-timeout 5 --max-time 15 \
  --resolve api.github.com:443:140.82.112.5 \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/user | grep -iE "^(HTTP/|x-oauth-scopes)"
```

`x-oauth-scopes` 含 `repo` 才具备建仓与推送能力；为空时回 SKILL.md 第 3 节换凭证，不要跑去改细粒度 token 的权限。

## 2 选通路

三条通路按下面的判据取一条，**任一命中即触发，不并行尝试**：

- `git ls-remote <仓库地址> HEAD` 能打印 SHA：直连可用，走第 3 步。**注意 git 可能正在偷偷走代理**：先 `git config --global --get http.proxy` 看一眼，有值说明这条「直连」其实是经代理的，此时 `gh` 与 `curl` 仍可能不通（它们不读 git 配置）。要判"真直连"，加 `-c http.proxy=` 清掉再试一次。
- 直连不通且本地代理在监听：走第 3 步的代理前缀写法。代理是否在监听要探，不要照抄端口：

  ```bash
  python -c "import socket;print('OPEN' if socket.socket().connect_ex(('127.0.0.1',7897))==0 else 'CLOSED')"
  ```

  **2026-11-10 复测：7897 OPEN**（同日 7890／1080／1081／10808／10809 全 CLOSED，且经 7897 之后 `gh api user` 立即正常）。2026-09-25 那天五个端口全 CLOSED。两天读数相反，判据只能是「当场探」。
- 直连与代理都不通：走第 4 步的多 IP 脚本。

**TLS 层例外（跨三条通路的最后一级兜底）**：若 git 在任一条通路上都因 **TLS 握手失败**而报错（`schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`——沙箱/受限运行环境把系统证书存储对该进程隔离了，直连与挂代理的 TLS 层都会挂，但 CONNECT 隧道其实已建立），则不再切通路，而是把 git 的 TLS 后端从默认 schannel 换成 openssl 并显式喂 CA bundle，再带原通路前缀重试：

```bash
CA="C:/Users/<你>/AppData/Roaming/WPS 灵犀/portable-git/PortableGit/mingw64/etc/ssl/certs/ca-bundle.crt"   # PortableGit 自带，按本机实际位置
git -c http.sslBackend=openssl -c http.sslCAInfo="$CA" -c http.proxy=http://127.0.0.1:<代理端口> push ...
```

数据与边界见 `references/access.md` 第五节末；`gh` 是 Go 二进制自带 TLS + 系统根证书，**不受此隔离影响**，仍按第 3 步挂代理走通，不必换 openssl。

**产出**：一个确定的通路。

**出口**：进入对应步骤。连续两次同一通路失败就换下一条，不要重复重试同一通路碰运气。代理为何改成"探测通过才用"、以及 2026-11-10 复测到的 7897 在监听这一读数，见 `references/push.md` 与 `references/access.md` 第三节。

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

脚本里的 `IPS` 与 `references/access.md` 第一节 github.com 那一行是**同一份数据的两处存放，改一处必须同步另一处**。两处不一致时以 access.md 的当日实测为准。

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

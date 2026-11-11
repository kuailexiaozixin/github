---
name: github-access
description: "GitHub 访问与克隆子技能——国内网络下把代码取到本地：整仓克隆、浅/稀疏/单分支克隆、免克隆读目录与文件、release 与 workflow 产物下载、REST 端点手搓、下载结果校验。覆盖 gh repo clone/read-file/read-dir、gh release download、gh run download、gh attestation download、gh api。触发关键词：访问 GitHub、克隆仓库、git clone 慢/失败、Connection reset、下载 GitHub 文件、不克隆只看代码、取 release 产物、下载 artifact、GitHub 网络不通、raw 打不开。"
---

# GitHub 访问与克隆（access）

把 GitHub 上的东西取到本地。主线依次是判需求、选通道、取回本地、校验，取不到就升级通道再来一遍。国内网络下 `github.com` 直连不稳，所以"选通道"这一步不能跳。

按 host 分列的可用 IP、镜像/代理实测、REST 端点清单、git 传输参数与 Windows 落盘坑，都在 `../references/access.md`；本文件只写流程，数据改动只在那份文件里做。

## 前置准备（只列材料）

- 目标对象的定位：`owner/repo`，以及分支/标签/提交 SHA；release 产物要版本号；workflow 产物要 run ID
- 是否需要凭证：公开仓库与公开 release 不登录也能取；私有仓库、或想吃满 5000 次/小时配额要有 token（见 github-cli 的登录主线）
- 本机是否挂了代理、监听端口是多少（决定第 2 步能不能升级）

## 1 判需求：要整仓，还是只要内容

**输入**：用户的一句话需求，翻译成下面四类之一。

| 要什么 | 取法 | 别用 |
|---|---|---|
| 要在本地跑、改、提交 | 第 3 步克隆 | 打 tar 包（没有 git 历史，之后推不上去） |
| 只要读几个文件/看目录结构 | 第 4 步免克隆读 | 整仓克隆（大仓库几十秒到几分钟） |
| 要发布产物（exe/zip/deb） | `gh release download` | 浏览器手点、curl 猜直链 |
| 要某次 CI 构建的输出 | `gh run download <run-id>` | 从 release 里找（可能没上传） |

**出口**：确定了一类，进第 2 步。判不出来就问用户"要本地跑还是只看"，这是两条不同的通道成本。

## 2 选通道：三条都当场探，按结果挑一条（没有固定优先次序）

**输入**：目标 host（`github.com` / `api.github.com` / `raw.githubusercontent.com` / `codeload.github.com` / `objects.githubusercontent.com`）。

```bash
# 一条命令判定该类 host 今天是否直连可用
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" --connect-timeout 5 https://github.com/
git ls-remote https://github.com/<owner>/<repo>.git        # 克隆类请求的最终判据
```

**动作**：三条通路各自独立探测，**用哪个客户端就先用哪个客户端探**——要 `git clone/fetch/push` 就用 `git ls-remote` 探，不要用 `curl` 的 200 代替（2026-11-10 实测过 `curl` 通而 `git` 不通的同一秒）。探的顺序按成本排：直连 → 代理（先扫常见端口）→ 顶 IP。顶 IP 时 git 要用 `-c http.curloptResolve=github.com:443:<IP>`，**不要用 `url.<ip>/.insteadOf`**（后者在当前网络下六个 IP 全失败，机制见 `references/access.md` 第四节末）。IP 由 `probe_github_net.py` 当场发现（DoH → 同段邻居 → meta 采样），不要抄 access.md 表里固定地址；该表仅作历史参考，超过两周即失效。

**产出**：一个可用通道（直连 / 顶 IP / 代理），以及它的适用范围——`--resolve` 只对显式写了该 host 的命令生效。

**出口**：`git ls-remote` 有输出即通道打通。**gh 与 git 是两条路**：`gh` 打 `api.github.com` 且用自己的解析结果，`--resolve` 和 hosts 文件对它无效，所以顶 IP 只影响 `git`/`curl`。gh 那条不通时按需要什么选替代：只要 REST 那份 JSON，就用顶 IP 的 curl 直接取端点（写法见 `../references/access.md` 第四节末段）；需要 gh 子命令自己的产出（`gh pr checks`、`gh run view --log` 这类没有对应 REST 字段的），只能挂代理让 gh 本身走通。

## 3 克隆整仓

```bash
# 首选：gh 版克隆——协议按 gh config，fork 会自动把上游加成 upstream 远端
gh repo clone <owner>/<repo>                       # 省略 OWNER 时用当前登录账号
gh repo clone <owner>/<repo> 本地目录              # 指定落地目录
gh repo clone <owner>/<repo> -- --depth=1          # git clone 的参数放 -- 之后
gh repo clone https://github.com/<owner>/<repo>    # 写了协议就按写的来，忽略 git_protocol
gh repo clone <owner>/<repo> --no-upstream         # 克隆自己的 fork 时不挂 upstream
gh repo clone <owner>/<repo> -u origin2            # 改 upstream 远端名（值可为 @owner）

# 传输量大时
git clone --depth 1 https://github.com/<owner>/<repo>.git                  # 只要最新提交
git clone --single-branch --branch <分支> <url>                            # 只要一条分支
git clone --filter=blob:none --sparse <url> && git -C <repo> sparse-checkout set <目录>
git fetch --unshallow                                                       # 浅克隆补回完整历史
```

**动作**：慢/中断时先加传输参数而不是重来：`git -c http.version=HTTP/1.1 -c http.postBuffer=524288000 -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=120 clone ...`（写成 `-c` 前缀做单次试验，确认有效再 `--global`）。顶 IP 克隆要 `git -c url.https://<IP>/.insteadOf=https://github.com/`，这条路在 github-push 里有已验证的脚本。

克隆 **fork 出来的仓库**时 `gh repo clone` 会自动加一条名为 `upstream` 的远端，并把**默认远端仓库设成上游**（帮助原文），之后不带 `-R` 的 `gh issue`/`gh pr` 命令会打到原仓库而不是你的分支库。三种处置：克隆前知道不要就加 `--no-upstream`；想留但换个名字用 `-u/--upstream-remote-name <名>`（值可为 `@owner` 形式）；已经克隆完的用 `gh repo set-default <你的>/<repo>` 纠正回来。另外两条默认行为：`OWNER/` 省略时按当前登录账号补全，仓库地址没写协议时按 `gh config get git_protocol` 决定走 HTTPS 还是 SSH。克隆之后要长期在这份 fork 上改动，接着走 github-fork 的第 3 步（把 gh 的默认远端仓库纠正回你自己的 fork）。

**产出**：本地仓库目录 + `git log -1` 有目标提交。

**出口**：`git -C <repo> rev-parse HEAD` 与远端 `git ls-remote` 的 SHA 一致。克隆的是 fork 时还要多看一眼 `git remote -v`：`upstream` 是否存在、指向哪个仓库，以及默认仓库是否已按上段纠正到你的分支库——否则下一条 `gh issue comment` 会写到别人的仓库上。只要部分目录时先 `sparse-checkout set` 再看文件是否存在，别在没 checkout 的目录里 grep 到空结果就断定"代码里没有"。

## 4 不克隆取内容

**输入**：仓库定位 + 路径/tag/run ID。

```bash
# 看目录结构（免克隆；--ref 支持分支/标签/SHA）
gh repo read-dir --repo <owner>/<repo> --ref <ref>
gh repo read-dir docs --repo <owner>/<repo> --json name,path,type,size

# 读单个文件
gh repo read-file README.md --repo <owner>/<repo>                 # 终端里走分页器，管道里输出原文
gh repo read-file src/main.py --repo <owner>/<repo> --ref v1.2.0
gh repo read-file config/app.yaml --repo <owner>/<repo> --output ./app.yaml --clobber

# release 产物
gh release download v1.2.3 --repo <owner>/<repo>                  # 该 tag 全部资产
gh release download -p '*.deb' -p '*.rpm'                          # 不带 tag 取 latest，必须配 -p 或 -A
gh release download v1.2.3 --archive=zip -D ./src/                 # 取源码包到指定目录
gh release download v1.2.3 -O -                                    # 单个资产写到 stdout

# 某次 CI 构建的产物
gh run download <run-id>                       # 不带 run ID 取的是"最近一次"，跨 run 必须显式给
gh run download <run-id> -n app-build -D ./out/
```

**动作**：`read-file`/`read-dir` 的 help 标注为 preview，参数形态可能随 gh 版本变；脚本里长期用要先 `gh help repo read-file` 对一遍。默认拒绝输出含终端转义序列的文件，确认来源可信才加 `--allow-escape-sequences`；用 `--output` 落盘时写的是原始字节。私有仓库或需要更高配额时带 token（gh 自动用已登录凭证，curl 手搓要 `-H "Authorization: Bearer $GITHUB_TOKEN"`）。

**产出**：本地文件，或读到的内容。

**出口**：`gh repo read-dir` 能列到目标路径、`read-file` 的 `--json size` 与落地文件字节数一致。整仓打包不要克隆时用 `https://github.com/<owner>/<repo>/archive/refs/heads/<分支>.tar.gz`（走 `codeload.github.com`，顶 IP 时要用 codeload 那组 IP）。

## 5 校验取到的东西

**输入**：落地文件。

```bash
ls -l 目标文件                       # 只看大小不足以判定完整
./目标程序 --version                  # 二进制必须跑一次；中转站可能返回截断但大小正常的文件
gh release view <tag> --json assets --jq '.assets[] | "\(.name) \(.size)"'   # 与本地大小对照（需 gh 2.x 支持该字段）
sha256sum 目标文件                    # 官方给了哈希就对照哈希
gh attestation download 目标文件 --repo <owner>/<repo>       # 官方签名产物：先取证明（离线可用）
gh attestation verify 目标文件 --repo <owner>/<repo>         # 再验证明链，见 github-ops 第 5 步
```

**动作**：经第三方前缀站下载的，一律做运行验证或哈希对照后再使用；前缀站存在篡改风险，只用于取公开产物。

**出口**：三项任一成立即可宣布取到——版本号回显正确、哈希与官方一致、attestation 验证通过。

## 6 不通时的升级顺序

按顺序试，每步失败记录现象再进下一步，不要跳级也不要回退重试同一招：

1. `curl -sI https://github.com/` 与 `git ls-remote`：判是网络层还是仓库权限层。仓库 404 而站点 200，是仓库不存在或私有未登录，换 IP 无用。
2. `nslookup github.com`：解析失败/超时是 DNS 层，临时 hosts 可应急但 IP 会变（数据见 `references/access.md` 第一节）。
3. 体积问题：`--depth 1`、`--filter=blob:none`、`--sparse`、或改走第 4 步免克隆。
4. 要的是 REST 端点能返回的数据：用顶 IP 的 curl 直接取，不依赖 gh 连得上（写法与 IP 分组见 `../references/access.md` 第四节末段）。
5. 挂代理：`HTTPS_PROXY=http://127.0.0.1:<探到的端口> git -c http.proxy= clone ...`。端口要当场扫（常见候选见 `references/access.md` 第三节），不要照抄 7897。挂上代理后**去掉**所有 `--resolve` / `curloptResolve` / `insteadOf` 设置，否则流量绕过代理，两头不讨好。
6. 前缀站兜底：`https://ghfast.top/<完整 GitHub URL>`，取回必做第 5 步校验。
7. 都不行：把 `curl -v` 的报错原文与日期交给用户，说明是本机网络环境限制，不要连续重试。

**TLS 后端替换（受限/沙箱环境专用）**：若报错是 `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`（安全包中没有可用的凭证）——典型于沙箱/受限运行环境把系统证书存储对该进程隔离了，直连与挂代理（CONNECT 隧道其实已建立）都会失败。这时把 git 的 TLS 后端从默认 schannel 换成 openssl 并显式喂 CA bundle，命令与边界见 `references/access.md` 第五节末。此招只救 `git`；`gh` 是 Go 二进制自带 TLS + 系统根证书，通常不受此隔离影响，仍按第 5 步挂代理走通。

**红线**：`http.sslVerify=false` 会去掉中间人防护，只在自签证书的企业代理环境里针对单条命令用（`git -c`），绝不写进 `--global`；不要为了拉一个仓库把全局 git 配置改掉，会影响其它仓库的推送。

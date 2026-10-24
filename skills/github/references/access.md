# 访问通道参考（access 深度资料）

本文件放**实测数据与判读规则**，主线流程在 `github-access/SKILL.md`。两边不重复：改通道数据只改这里。

## 一、按 host 分列的可用 IP（实测 2026-09-25，本机直连，无代理）

`--resolve <host>:443:<ip>` 逐 IP 取一次真实资源，记录 HTTP 状态码与总耗时。判读规则写在表格后面，先看完表格再看规则。

| host | 候选 IP | 实测状态 | 用途判定 |
|---|---|---|---|
| `github.com` | `140.82.112.3` `140.82.113.3` `140.82.113.4` `140.82.114.3` `140.82.116.3` `20.205.243.166` | 200，1.9–2.2s | 可用：网页与 `git clone`/`git fetch` |
| `github.com` | `140.82.112.5` | 404 | 不是 github.com 前端，别顶给它（详见规则 2） |
| `github.com` | `20.205.243.168` | 400 | 不是 github.com 前端（api 前端） |
| `api.github.com` | `140.82.112.5` `20.205.243.168` | 200 | 可用：REST API |
| `api.github.com` | `140.82.112.3` `140.82.113.3` `140.82.113.4` `140.82.114.3` `140.82.116.3` `20.205.243.166` | 301 | 会把请求重定向到 github.com，不能当 api 用 |
| `raw.githubusercontent.com` | `185.199.108.133` `185.199.109.133` `185.199.110.133` `185.199.111.133` | 200，1.1–1.3s | 可用：raw 文件 |
| `objects.githubusercontent.com` | 同上四个 `185.199.1xx.133` | 404（请求根路径，属正常） | 与 raw 同一组 anycast IP，可用；404 只说明没有该对象键 |
| `codeload.github.com` | `140.82.116.10` | 200 | 可用：`/archive/...tar.gz` 整仓打包 |
| `codeload.github.com` | `140.82.112.3` `140.82.113.4` `20.205.243.166` | 301 | 不能当 codeload 用 |

当日系统 DNS 解析结果（说明"直连是否本来就通"）：`github.com` 解析到 140.82.116.3、`api.github.com` 解析到 140.82.116.5、`raw.githubusercontent.com` 解析到 185.199.108.133 至 185.199.111.133、`codeload.github.com` 解析到 140.82.116.9 与 140.82.116.10。四条直连均返回 200。

### 判读规则

1. **每个 host 有自己的一组前端 IP，不能混用。** 140.82.112/113/114/116 段里既有 web 前端也有 api 前端，用错的表现是 301（被踢到别的 host）或 400/404，**不是网络故障**——这时换 IP 没用，要换 host 对应的那一组。
2. **`404` 与 `000` 是两件事。** `404` 说明 TCP+TLS+HTTP 全程走通、只是这个前端上没有该资源，属"可用但要换 host"；`000`（curl 无状态码）才是连不上。
3. **`--resolve` 只对显式指定该 host 的命令生效。** `git clone` 会同时打 `github.com`（智能协议）与 `objects.githubusercontent.com`（大对象），只顶一个会中途失败；`gh` 走 `api.github.com` 且用自己的 DNS，`--resolve` 与 hosts 文件对 gh 均无效，这时用 curl 顶 IP 取同一份数据，写法见本文件第四节末段。
4. **IP 会变，日期就是有效期。** 本表超过两周、或换网络环境（换城市/换运营商/挂上代理）后视为失效，按下面第二节重测。挂上代理时**不要**再用 `--resolve`：代理会自己选路，顶 IP 只会绕过代理。

## 二、重测步骤（约 30 秒，只读请求，不落凭证）

```bash
# 1) 先看直连是否本来就通（通的话不用管 IP 池）
for h in github.com api.github.com raw.githubusercontent.com codeload.github.com; do
  printf '%-28s ' "$h"; curl -s -o /dev/null -w "%{http_code}\n" --connect-timeout 5 "https://$h/"
done

# 2) 不通或很慢时，逐 IP 顶住真实资源再测（换 host 就换 URL 与 IP 段）
for ip in 140.82.112.3 140.82.113.3 140.82.113.4 140.82.114.3 140.82.116.3 20.205.243.166; do
  printf '%-16s ' "$ip"
  curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" --connect-timeout 4 --max-time 10 \
    --resolve github.com:443:$ip https://github.com/cli/cli
done
# api.github.com 用这个 URL，且只测 140.82.112.5 / 20.205.243.168：
#   https://api.github.com/repos/cli/cli
# raw 用 https://raw.githubusercontent.com/cli/cli/trunk/README.md 顶 185.199.108–111.133

# 3) 记下"host + IP + 状态码 + 日期"，回填第一节表格，替换旧行而不是追加
nslookup github.com     # 一并记录当日 DNS 结果，判断是不是解析层问题
```

**出口**：每个 host 至少有一个 IP 返回该类资源应得的状态（web/api/raw 200；objects 允许 404）。全部候选都拿不到时不是 IP 池的问题，按第五节走代理。

## 三、镜像与代理前缀（实测 2026-08，需要重测）

| 方案 | 上次实测 | 用法与风险 |
|---|---|---|
| 本地代理 `127.0.0.1:7897` | 可用，最可靠 | `HTTPS_PROXY=http://127.0.0.1:7897 git clone ...`；端口以本机代理客户端实际监听为准，换端口要先 `curl -x http://127.0.0.1:<端口> -sI https://github.com` 验证 |
| `ghfast.top` 前缀 | 可用 | `https://ghfast.top/<完整 GitHub URL>`，用于 release 直链与 raw 文件 |
| `gh-proxy.com` 前缀 | 不稳定 | 实测返回过"大小正常但无法运行"的截断文件；用它必须做运行验证 |
| `ghproxy.com`、`hub.fastgit.xyz`、`gh.api.99988866.xyz` | 全部失效 | 不要再试，浪费时间 |
| 代理端口 `1080/1081/7890/10808/10809` | 本机不可用 | 本机只有 7897 在监听 |

第三方前缀站是中转服务，存在篡改与投毒风险：只用于取**公开**产物，取回后要验（运行 `--version`/`--help`，或对照 release 的 attestation）；不要经它取需要凭证的接口，也不要用它下载源码后直接执行。

## 四、免克隆取内容的 REST 端点清单

`gh` 能直接做到的事优先用 `gh`（`gh repo read-file`、`gh repo read-dir`、`gh release download`、`gh run download`、`gh attestation download`）。gh 不可用或要脚本化时才手搓 API：

```
GET /repos/{owner}/{repo}/git/trees/{ref}?recursive=1   # 整棵文件树（含 sha 与 path）
GET /repos/{owner}/{repo}/git/blobs/{sha}               # 单个 blob，content 为 base64
GET /repos/{owner}/{repo}/contents/{path}?ref={ref}     # 单文件（含 download_url）
GET /repos/{owner}/{repo}/compare/{base}...{head}       # 只取变更文件
GET /repos/{owner}/{repo}/releases/latest               # 注意：这是 JSON 元数据，不是二进制
```

未登录 60 次/小时、带 token 5000 次/小时；批量遍历 blob 很容易吃满配额，先用 `X-RateLimit-Remaining` 响应头看余量（`gh api -i <端点>` 就能看到）。

### gh 本身打不通时用 curl 顶 IP 取同一份数据

`gh` 走 `api.github.com`，用的是它自己那次解析得到的 IP，本机 hosts 与 `--resolve` 都改不动它（规则 3）。所以 `gh api` 失败而 `curl` 直连成功时，不要重复重试 gh，改用顶 IP 的 curl 取同一个端点：

```bash
# 候选 IP 只取第一节表里 api.github.com 那一组（140.82.112.5 / 20.205.243.168）
for ip in 140.82.112.5 20.205.243.168; do
  printf '%-16s ' "$ip"
  curl -s -o /dev/null -w "%{http_code}\n" --connect-timeout 4 \
    --resolve api.github.com:443:$ip -H "Authorization: Bearer $GITHUB_TOKEN" \
    https://api.github.com/repos/<owner>/<repo>
done
# 探到 200 的那个 IP 上取数据，Accept 头决定返回的媒体类型
curl -s --resolve api.github.com:443:<可用IP> -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" https://api.github.com/repos/<owner>/<repo>
```

顶 IP 时只看状态码判成败不够：那组 web 前端 IP（140.82.112.3、140.82.113.3、140.82.113.4、140.82.114.3、140.82.116.3、20.205.243.166）对 api 返回 301，看着"有响应"其实拿不到 JSON。出口判据是响应体能解出目标字段，而不只是 2xx/3xx。

写操作（POST/PATCH）同样能用这条通道，但负载编码要另外注意，见下面第五节的 Windows 侧坑。


## 五、git 传输参数与 Windows 落盘坑

```bash
git -c http.version=HTTP/1.1 ...        # 部分网络对 HTTP/2 支持差
git -c http.postBuffer=524288000 ...    # 500MB 缓冲，大仓库推送/拉取
git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=120 ...   # 慢但不误判为断
git -c http.sslVerify=false ...         # 仅限自签/中间人代理环境，公网仓库不要关
```

写成 `-c` 前缀做单次试验，确认有效再 `git config --global`，避免全局设置影响其它仓库。

Windows 侧三个高频坑：

- **MSYS `/tmp` 不跨调用**：Git Bash 里 `curl -o /tmp/x` 写的临时目录可能在下一次调用就不在了。下载目标用 `$USERPROFILE/文件名` 或绝对 Windows 路径。
- **zip 里有一层子目录**：多数 release 包内是 `app-v1.0.0-windows-x86_64/`。解压后要把二进制从子目录移到目标 bin 根（`mv <子目录>/*.exe . && rmdir <子目录>`），否则调用方找不到。
- **含中文的 JSON 负载不要写在命令行上**：直接在命令行 `-d '{"description":"中文"}'` 会被 Windows 本地编码破坏，返回 400 `Problems parsing JSON`。把负载写成 UTF-8 文件后用 `--data-binary @payload.json` 发送；`gh api` 那条对应写法是 `--input payload.json`。

### TLS 后端替换：schannel 证书存储被隔离时改用 openssl

**现象**：`curl`/`git` 报 `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`（“安全包中没有可用的凭证”）。多见于沙箱/受限运行环境把系统证书存储对该进程隔离了——此时直连、挂代理（CONNECT 隧道其实已建立）都会失败，但 `gh`（Go 二进制，自带 TLS 与系统根证书）通常不受影响。

**做法**：把 git 的 TLS 后端从默认 schannel 换成 openssl，并显式喂 CA bundle（Windows git / PortableGit 自带一份）：

```bash
# CA bundle 路径（PortableGit 自带，按本机实际位置；本机示例见文末）
CA="C:/Users/<你>/AppData/Roaming/WPS 灵犀/portable-git/PortableGit/mingw64/etc/ssl/certs/ca-bundle.crt"
# 单条命令带 -c 前缀，不写进 --global；受限且需代理时叠加 http.proxy
git -c http.sslBackend=openssl \
    -c http.sslCAInfo="$CA" \
    -c http.proxy=http://127.0.0.1:<本机代理端口> \
    ls-remote https://github.com/<owner>/<repo>.git
# 等价：GIT_SSL_CAINFO="$CA" git -c http.sslBackend=openssl ...
```

**出口判据**：`git ls-remote` 能打印远端 HEAD/分支即 TLS 通道打通；`clone`/`push` 同法带上前缀（`-c http.sslBackend=openssl -c http.sslCAInfo="$CA"`）。

**边界**：此招只解决 `git`（它可选 openssl 后端）。`curl` 后端仍是 schannel、受限环境未必有独立 CA 可用，直接取文件不可靠——REST 数据优先用 `gh`（挂 `HTTPS_PROXY`/`HTTP_PROXY` 代理走通）或顶 IP 取端点（本文件第四节）。本机实测可用的 CA bundle：`C:/Users/贺新/AppData/Roaming/WPS 灵犀/portable-git/PortableGit/mingw64/etc/ssl/certs/ca-bundle.crt`。

## 相关

- 主线流程：`../github-access/SKILL.md`
- 推送侧的多 IP 脚本（`push_repo.sh` 的退出码与为什么关 TLS 校验）：`push.md`
- 运维命令：`ops.md`

#!/usr/bin/env python3
"""probe_github_net.py — 判断「此刻这台机器怎么连 GitHub」，并给出可直接复制的命令前缀。

为什么需要它：GitHub 的可达性不是机器属性，是当场状态。同一个用户在一天之内可能遇到
直连通、只有代理通、DNS 被污染但顶 IP 通、以及全都不通。把这个判断写死成「固定端口 +
固定 IP 列表」在别人机器上必然失效，所以这里全部改成运行时探测。

探测的四层，按成本从低到高，任一命中即停：

    1. 直连          —— 系统 DNS 能不能解析、能不能连上
    2. 本机代理      —— 读系统配置（不是猜端口）；探到就试
    3. 公共 DNS      —— 系统 DNS 被污染时，用 DoH 换一个真地址
    4. GitHub 官方段 —— 从 api.github.com/meta 取当前有效的地址段再采样

判据一律用「要用的那个客户端去探」：推代码就用 git ls-remote，取 API 就用 curl 打真端点。
curl 通不代表 git 通（两者的 DNS 与连接栈不同），这一条是本脚本存在的核心原因。

输出三种，机器可读：
    probe_github_net.py --json      # 完整结果
    probe_github_net.py             # 人读
退出码：0 至少一条通路可用；1 四层全不通。
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile

# ── 常量 ──────────────────────────────────────────────────────────────────

# 代理端口的候选值。这些只是「常见客户端的默认值」，不是通用标准：
#   7890 Clash / Clash for Windows      7897 Clash Verge / Mihomo
#   1080 v2rayN(socks)                  1081 v2rayN(http = socks+1)
#   10808 v2rayNG / 早期 v2rayN          10809 对应 http
#   8080 8081 通用代理惯例
# 用户可以在客户端里改，所以扫端口只是兜底；主力是下面 read_system_proxy()。
PROXY_PORT_CANDIDATES = (7897, 7890, 7896, 1081, 1080, 10809, 10808, 8080, 8888)

# 公共 DoH 端点。用于「系统 DNS 被污染」这一层。
DOH_ENDPOINTS = ("https://223.5.5.5/resolve", "https://1.12.12.12/resolve", "https://dns.alidns.com/resolve")

# api.github.com/meta 拿不到时用的兜底样本。**这些是样本不是全集**，
# 写在文件里只为「meta 也取不到」的最后一级；不要当成可用性保证。
FALLBACK_API = ("140.82.112.5", "140.82.112.6", "20.205.243.168")
FALLBACK_WEB = ("140.82.112.3", "140.82.113.3", "140.82.113.4", "140.82.114.3",
                "140.82.116.3", "20.205.243.166")

PROBE_TIMEOUT = 6      # 单枚地址的 curl 超时
GIT_TIMEOUT = 25       # git ls-remote 超时


# ── 基础工具 ──────────────────────────────────────────────────────────────

def _run(cmd, timeout):
    """跑一条命令，返回 (ok, stdout, stderr)。ok 只看退出码。"""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode == 0, (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired:
        return False, "", "timeout after %ss" % timeout
    except FileNotFoundError as e:
        return False, "", "not found: %s" % e


def which(name):
    return shutil.which(name) or ""


def curl_base():
    """curl 的公共前缀。--insecure 不在这里加，按需由调用方决定。"""
    c = which("curl")
    return [c or "curl"]


# ── 第一层：直连 ──────────────────────────────────────────────────────────

def resolve_system(host):
    """系统 DNS 解析。返回 (ips, err)。"""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        ips = sorted({i[4][0] for i in infos})
        return ips, ""
    except Exception as e:
        return [], "%s: %s" % (type(e).__name__, e)


def probe_git_direct(repo_url, proxy=None, resolve=None):
    """用 git 本身探。返回 (ok, detail)。

    proxy: 显式代理 URL 或空串。传空串表示**清掉** git 配置里的代理，
           这样才能量到「真直连」——本机 .gitconfig 里可能留着一条失效代理。
    resolve: "host:443:ip" 时用 http.curloptResolve 顶地址。
    """
    cmd = ["git", "-c", "http.proxy=%s" % (proxy or "")]
    if resolve:
        cmd += ["-c", "http.curloptResolve=%s" % resolve, "-c", "http.sslVerify=false"]
    cmd += ["ls-remote", repo_url, "HEAD"]
    ok, out, err = _run(cmd, GIT_TIMEOUT)
    detail = (out.strip().splitlines() or [""])[0][:12] if ok else (err.strip().splitlines() or [""])[0][:120]
    return ok, detail


def probe_https(host, ip=None, path="/", headers=None, timeout=PROBE_TIMEOUT):
    """curl 打一个真端点。返回 (status, seconds, body_head)。

    status 是字符串：三位码，或 "000"（连不上/超时）。
    400 的含义很重要：TCP+TLS 通了，但这台机器不服务该 Host —— 属「不可用」，
    与 000（连不上）是两件事，但都不算成功。
    """
    cmd = curl_base() + ["-s", "-o", "/dev/null", "-w", "%{http_code} %{time_total}",
                         "--connect-timeout", str(min(4, timeout)), "--max-time", str(timeout)]
    if ip:
        cmd += ["--resolve", "%s:443:%s" % (host, ip)]
    for h in (headers or []):
        cmd += ["-H", h]
    cmd.append("https://%s%s" % (host, path))
    ok, out, _ = _run(cmd, timeout + 3)
    parts = (out or "000 0").split()
    return parts[0] if parts else "000", (parts[1] if len(parts) > 1 else "0")


# ── 第二层：本机代理（读配置优先，扫端口兜底）────────────────────────────

def read_system_proxy():
    """读系统里登记的代理配置。返回 dict，各键可能为空。

    Windows 上三个层次要分开看，混起来会误判：
      - WinHTTP（netsh winhttp）：服务/计划任务走这条
      - WinINET（注册表 Internet Settings）：浏览器与多数图形客户端
        注意 ProxyEnable=0 时 ProxyServer 仍可能留着旧值，**必须两个一起看**
      - 环境变量：命令行工具（git/gh/curl）走这条
    """
    out = {"winhttp": "", "wininet": "", "env": "", "gitconfig": "", "socks_ports": []}

    if sys.platform == "win32":
        ok, so, _ = _run(["netsh", "winhttp", "show", "proxy"], 8)
        if ok:
            for line in so.splitlines():
                if ":" in line and any(ch.isdigit() for ch in line) and "直接访问" not in line:
                    s = line.split(":", 1)[1].strip()
                    if s and s != "直接访问(没有代理服务器)":
                        out["winhttp"] = s
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
            try:
                enabled = int(winreg.QueryValueEx(k, "ProxyEnable")[0])
            except FileNotFoundError:
                enabled = 0
            try:
                server = str(winreg.QueryValueEx(k, "ProxyServer")[0])
            except FileNotFoundError:
                server = ""
            if enabled and server:
                out["wininet"] = server
            elif server:
                out["wininet_stale"] = server   # 有值但没启用：不可用，仅留痕
        except Exception:
            pass

    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        v = os.environ.get(name, "")
        if v:
            out["env"] = v
            break

    ok, so, _ = _run(["git", "config", "--global", "--get", "http.proxy"], 8)
    if ok and so.strip():
        out["gitconfig"] = so.strip()

    return out


def scan_ports(candidates=PROXY_PORT_CANDIDATES, timeout=0.15):
    """快探候选端口。只认「本地监听」，不代表该端口是 HTTP 代理。"""
    alive = []
    for p in candidates:
        s = socket.socket()
        s.settimeout(timeout)
        try:
            if s.connect_ex(("127.0.0.1", p)) == 0:
                alive.append(p)
        finally:
            s.close()
    return alive


def proxy_url_of(cfg):
    """从系统配置里挑一个可用的代理 URL，并探它真能不能转发 HTTPS。

    返回 [(url, note)]，只保留「TCP 通 且 能代理到 github.com」的。
    """
    cands = []
    for key in ("winhttp", "wininet", "env"):
        v = cfg.get(key) or ""
        if not v:
            continue
        if "=" in v:                      # 形如 "http=127.0.0.1:7890;https=..."
            parts = dict(x.split("=", 1) for x in v.split(";") if "=" in x)
            v = parts.get("https") or parts.get("http") or ""
        if v and "://" not in v:
            v = "http://" + v
        if v:
            cands.append((v, key))
    for p in cfg.get("socks_ports") or []:
        cands.append(("socks5://127.0.0.1:%d" % p, "scan"))

    good = []
    for url, src in cands:
        cmd = curl_base() + ["-s", "-o", "/dev/null", "-w", "%{http_code}",
                             "--connect-timeout", "4", "--max-time", "10",
                             "-x", url, "https://github.com/"]
        ok, out, _ = _run(cmd, 14)
        if ok and out.strip() in ("200", "301", "302"):
            good.append((url, src))
    return good


# ── 第三层：公共 DNS（绕开被污染的系统 DNS）────────────────────────────────

def doh_resolve(host, endpoints=DOH_ENDPOINTS, timeout=8):
    """用 DoH 解析 A 记录。返回 (ips, used_endpoint, err)。"""
    for ep in endpoints:
        cmd = curl_base() + ["-s", "--connect-timeout", "4", "--max-time", str(timeout),
                             "-H", "accept: application/dns-json",
                             "%s?name=%s&type=A" % (ep, host)]
        ok, out, _ = _run(cmd, timeout + 3)
        if not ok or not out.strip():
            continue
        try:
            d = json.loads(out)
            ips = [a["data"] for a in d.get("Answer", []) if a.get("type") == 1]
            if ips:
                return ips, ep, ""
        except Exception:
            continue
    return [], "", "all DoH endpoints failed"


# ── 第四层：GitHub 官方地址段 ─────────────────────────────────────────────

def fetch_meta(api_ip=None):
    """取 api.github.com/meta。返回 (dict, err)。"""
    cmd = curl_base() + ["-s", "--connect-timeout", "5", "--max-time", "25"]
    if api_ip:
        cmd += ["--resolve", "api.github.com:443:%s" % api_ip]
    cmd.append("https://api.github.com/meta")
    ok, out, err = _run(cmd, 30)
    if not ok or not out.strip().startswith("{"):
        return {}, err or "empty"
    try:
        return json.loads(out), ""
    except Exception as e:
        return {}, str(e)


def sample_cidrs(cidrs, per_block=3, max_total=24):
    """从 CIDR 列表里采样本地址。

    分两类取：
      - /32 单地址：这是官方特意列出的独立入口，命中率高，全部取（最多 max_total）
      - 更大的段：只取段内前几个地址。**不能整段扫**——/20 就有 4096 个地址，
        actions 段加起来上万，全扫既慢又会把对方当靶子。
    """
    singles, sampled = [], []
    for c in cidrs:
        if ":" in c:            # 跳过 IPv6：本机与多数受限网络未必有 v6 出口
            continue
        try:
            n = ipaddress.ip_network(c, strict=False)
        except ValueError:
            continue
        if n.prefixlen == 32:
            singles.append(str(n.network_address))
        elif len(sampled) < max_total:
            base = int(n.network_address)
            for off in range(1, per_block + 1):
                addr = ipaddress.ip_address(base + off)
                if addr in n:
                    sampled.append(str(addr))
    out = []
    for ip in singles + sampled:
        if ip not in out:
            out.append(ip)
    return out[:max_total]


# ── 编排 ──────────────────────────────────────────────────────────────────

def probe(repo_url="https://github.com/cli/cli", want_api=True):
    r = {"git_direct": None, "proxy": None, "doh": None, "cidr": None,
         "system_proxy": None, "ok": False, "prefix": "", "notes": []}

    cfg = read_system_proxy()
    cfg["socks_ports"] = scan_ports()
    r["system_proxy"] = cfg

    # 1) 真直连（显式清 git 配置里的代理）
    ok, detail = probe_git_direct(repo_url, proxy="")
    r["git_direct"] = {"ok": ok, "detail": detail}
    if ok:
        r.update(ok=True, prefix="git -c http.proxy=", notes=["直连可用"])
        if cfg.get("gitconfig"):
            r["notes"].append("注意：.gitconfig 里仍有 http.proxy=%s，用 -c http.proxy= 清掉才是真直连"
                              % cfg["gitconfig"])
        return r

    # 2) 本机代理
    goods = proxy_url_of(cfg)
    if goods:
        url, src = goods[0]
        ok2, detail2 = probe_git_direct(repo_url, proxy=url)
        r["proxy"] = {"url": url, "source": src, "git_ok": ok2, "detail": detail2}
        if ok2:
            r.update(ok=True, prefix="HTTPS_PROXY=%s HTTP_PROXY=%s" % (url, url),
                     notes=["经本机代理可用（来源 %s）" % src])
            return r
    else:
        r["proxy"] = {"url": "", "source": "", "git_ok": False,
                      "detail": "系统配置里没有可用代理，候选端口里也没有监听"}

    # 3) DoH：系统 DNS 可能被污染
    for host in ("github.com",):
        ips, ep, err = doh_resolve(host)
        r["doh"] = {"host": host, "ips": ips, "endpoint": ep, "err": err}
        if not ips:
            continue
        for ip in ips[:3]:
            ok3, detail3 = probe_git_direct(repo_url, proxy="",
                                            resolve="%s:443:%s" % (host, ip))
            if ok3:
                r.update(ok=True,
                         prefix="git -c http.proxy= -c http.curloptResolve=%s:443:%s -c http.sslVerify=false"
                                % (host, ip),
                         notes=["系统 DNS 给出的地址不可用，DoH(%s) 解析到 %s 后可用" % (ep, ip)])
                return r

    # 4) 官方地址段
    api_ip = None
    for cand in FALLBACK_API:
        st, _ = probe_https("api.github.com", ip=cand, path="/rate_limit", timeout=8)
        if st.isdigit() and st[0] in "23":
            api_ip = cand
            break
    meta, merr = fetch_meta(api_ip)
    if meta:
        cidrs_web = meta.get("web") or []
        cands = sample_cidrs(cidrs_web)
        r["cidr"] = {"source": "api.github.com/meta via %s" % (api_ip or "direct"),
                     "web_blocks": len([c for c in cidrs_web if ":" not in c]),
                     "sampled": cands, "err": ""}
        for ip in cands:
            ok4, detail4 = probe_git_direct(repo_url, proxy="",
                                            resolve="github.com:443:%s" % ip)
            if ok4:
                r.update(ok=True,
                         prefix="git -c http.proxy= -c http.curloptResolve=github.com:443:%s -c http.sslVerify=false" % ip,
                         notes=["官方地址段内 %s 可用（共采样 %d 枚）" % (ip, len(cands))])
                return r
    else:
        r["cidr"] = {"source": "", "web_blocks": 0, "sampled": [], "err": merr}
        for ip in FALLBACK_WEB:
            ok5, detail5 = probe_git_direct(repo_url, proxy="",
                                            resolve="github.com:443:%s" % ip)
            if ok5:
                r.update(ok=True,
                         prefix="git -c http.proxy= -c http.curloptResolve=github.com:443:%s -c http.sslVerify=false" % ip,
                         notes=["meta 取不到，用内置样本 %s 探通（样本不代表全集）" % ip])
                return r

    r["notes"].append("四层全不通：直连、本机代理、DoH 顶 IP、官方地址段都没连上")
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description="探测本机到 GitHub 的可用通路")
    ap.add_argument("--repo", default="https://github.com/cli/cli",
                    help="用哪个仓库做 git 探测（默认 GitHub 官方仓库，只读）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    r = probe(args.repo)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        sp = r["system_proxy"] or {}
        print("本机代理配置：")
        print("  WinHTTP : %s" % (sp.get("winhttp") or "(无)"))
        print("  WinINET : %s%s" % (sp.get("wininet") or "(未启用)",
                                   ("  [注册表残留 %s，ProxyEnable=0]" % sp["wininet_stale"])
                                   if sp.get("wininet_stale") else ""))
        print("  环境变量: %s" % (sp.get("env") or "(无)"))
        print("  git 配置: %s" % (sp.get("gitconfig") or "(无)"))
        print("  监听端口: %s" % (sp.get("socks_ports") or "(无)"))
        print()
        print("直连      : %s  %s" % ("可用" if r["git_direct"]["ok"] else "不通",
                                      r["git_direct"]["detail"]))
        if r["proxy"]:
            print("本机代理  : %s  %s" % ("可用" if r["proxy"]["git_ok"] else "不通",
                                          r["proxy"]["url"] or r["proxy"]["detail"]))
        if r["doh"]:
            print("公共 DNS  : %s  %s" % (r["doh"]["endpoint"] or "(未取到)",
                                          " ".join(r["doh"]["ips"]) or r["doh"]["err"]))
        if r["cidr"]:
            print("官方地址段: %s  %s" % (r["cidr"]["source"] or "(未取到)",
                                          r["cidr"]["err"] or "采样 %d 枚" % len(r["cidr"]["sampled"])))
        print()
        if r["ok"]:
            print("结论：可用。命令前缀：")
            print("  " + r["prefix"])
        else:
            print("结论：四层全不通。")
        for n in r["notes"]:
            print("  - %s" % n)
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

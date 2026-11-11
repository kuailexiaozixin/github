#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""浏览器打不开 GitHub 网页：诊断 → 修复 → 验证（默认只读）。

只管浏览器实际读取的三处系统配置：
  1. WinINET 用户代理（HKCU 注册表，Edge/Chrome 默认来源，含 PAC）
  2. 系统 DNS（含 hosts 残留钉死、DNS 缓存）
  3. WinHTTP 服务层代理（不影响浏览器，列出供参考）
默认只读：打印状态、归因与修复计划，不改任何配置。
--apply <动作> 才执行修复；每个写动作先备份到 ~/.github-repair-backups/<时间戳>/，
打印精确回滚命令，修复后自动复测（走系统默认代理+DNS 的 HTTPS 请求，与浏览器同一通路）。

端口、IP、代理状态全部运行时发现：候选端口来自注册表 ProxyServer、
环境变量与常见端口扫描清单，只作扫描候选、非优先级，任何端口只在当次探测有效。

退出码：0 通路健康；2 发现问题已出计划（未改动）；3 修复并验证通过；
4 修复后仍不通；5 用法/权限错误。
"""

import argparse
import ctypes
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    import winreg
except ImportError:  # 非 Windows 环境直接报错退出
    print("仅支持 Windows（依赖注册表与 WinINET/WinHTTP）")
    sys.exit(5)

GITHUB_HOSTS = ("github.com", "api.github.com", "raw.githubusercontent.com",
                "objects.githubusercontent.com", "codeload.github.com")
COMMON_PROXY_PORTS = (7897, 7890, 7896, 1080, 10808, 10809, 8080, 8888)  # 扫描候选，非优先级
DOH_ENDPOINTS = ("https://223.5.5.5/resolve", "https://1.12.12.12/resolve",
                 "https://dns.alidns.com/resolve")
PUBLIC_DNS = ("223.5.5.5", "119.29.29.29")
INET_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
HOSTS_PATH = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"
BACKUP_ROOT = Path.home() / ".github-repair-backups"
ENV_PROXY_VARS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
                  "ALL_PROXY", "all_proxy")
ACTIONS = ("repoint-proxy", "enable-proxy", "disable-proxy", "clear-pac",
           "flushdns", "set-dns", "clean-hosts", "reset-winhttp")
NEEDS_ADMIN = ("set-dns", "clean-hosts", "reset-winhttp")
NEEDS_PORT = ("repoint-proxy", "enable-proxy")
CURL = shutil.which("curl") or "curl"


def _run(cmd, timeout):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode == 0, (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired:
        return False, "", "timeout after %ss" % timeout
    except FileNotFoundError as e:
        return False, "", "not found: %s" % e


def ps_run(script, timeout=30):
    """跑一段 PowerShell（无 profile）。返回 (ok, stdout, stderr)。"""
    return _run(["powershell", "-NoProfile", "-Command", script], timeout)


def hr(title):
    print("\n== %s ==" % title)


# ── WinINET（HKCU，浏览器默认读取的代理配置） ─────────────────────────────

def read_wininet():
    names = ("ProxyEnable", "ProxyServer", "AutoConfigURL", "ProxyOverride")
    out = {n: None for n in names}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INET_KEY) as k:
            for n in names:
                try:
                    out[n], _ = winreg.QueryValueEx(k, n)
                except OSError:
                    pass
    except OSError as e:
        out["error"] = str(e)
    return out


def write_wininet(name, value, typ):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INET_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, typ, value)


def delete_wininet(name):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INET_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.DeleteValue(k, name)


def notify_wininet():
    """广播代理设置变更（39=SETTINGS_CHANGED 40=REFRESH），浏览器不重启即可感知。"""
    try:
        w = ctypes.WinDLL("wininet")
        w.InternetSetOptionW(None, 39, None, 0)
        w.InternetSetOptionW(None, 40, None, 0)
        return True
    except Exception:
        return False


def parse_proxy_server(v):
    """ProxyServer 两种形态：'host:port' 或 'http=..;https=..;ftp=..;socks=..'。"""
    if not isinstance(v, str) or not v.strip():
        return {}
    if "=" in v:
        out = {}
        for part in v.split(";"):
            if "=" in part:
                proto, addr = part.split("=", 1)
                if addr.strip():
                    out[proto.strip().lower()] = addr.strip()
        return out
    return {"all": v.strip()}


def addr_port(addr):
    m = re.search(r":(\d+)\s*$", addr or "")
    return int(m.group(1)) if m else None


# ── 本机代理端口扫描 + CONNECT 实测 ──────────────────────────────────────

def scan_open_ports(candidates, timeout=0.15):
    open_ports = []
    for p in dict.fromkeys(candidates):
        s = socket.socket()
        s.settimeout(timeout)
        try:
            if s.connect_ex(("127.0.0.1", p)) == 0:
                open_ports.append(p)
        finally:
            s.close()
    return open_ports


def proxy_connect_test(port, host="github.com", timeout=6):
    """对本机 port 发 CONNECT host:443，浏览器经代理走的正是这条。
    返回 (状态码或 None, 首行, 毫秒)。"""
    t0 = time.perf_counter()
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(("CONNECT %s:443 HTTP/1.1\r\nHost: %s:443\r\n\r\n" % (host, host)).encode())
        data = s.recv(512)
        s.close()
        ms = round((time.perf_counter() - t0) * 1000)
        first = data.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        m = re.search(r"\s(\d{3})\s", first)
        return (m.group(1) if m else None), first.strip(), ms
    except OSError as e:
        return None, "%s: %s" % (type(e).__name__, e), None


# ── DNS：系统解析 vs DoH ────────────────────────────────────────────────

def resolve_system(host):
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        return sorted({i[4][0] for i in infos}), ""
    except Exception as e:
        return [], "%s: %s" % (type(e).__name__, e)


def doh_resolve(host, timeout=8):
    for ep in DOH_ENDPOINTS:
        ok, out, _ = _run([CURL, "-s", "--connect-timeout", "4", "--max-time", str(timeout),
                           "-H", "accept: application/dns-json",
                           "%s?name=%s&type=A" % (ep, host)], timeout + 3)
        if not ok or not out.strip():
            continue
        try:
            d = json.loads(out)
            ips = [a["data"] for a in d.get("Answer", []) if a.get("type") == 1]
            if ips:
                return ips, ep, ""
        except Exception:
            continue
    return [], "", "所有 DoH 端点都失败"


def tcp443(ip, timeout=4):
    t0 = time.perf_counter()
    try:
        s = socket.create_connection((ip, 443), timeout=timeout)
        s.close()
        return True, round((time.perf_counter() - t0) * 1000)
    except OSError:
        return False, None


def alive_ips(ips, timeout=4):
    out = []
    for ip in ips:
        ok, ms = tcp443(ip, timeout)
        if ok:
            out.append((ip, ms))
    return out


# ── hosts 残留钉死 ──────────────────────────────────────────────────────

def hosts_pins():
    try:
        text = HOSTS_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return [], str(e)
    pins = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) >= 2 and parts[1].lower() in GITHUB_HOSTS:
            pins.append((i, parts[0], parts[1].lower()))
    return pins, ""


# ── PAC 可达性 ──────────────────────────────────────────────────────────

def pac_fetch(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read(256)
        return bool(body), "HTTP %s, %d 字节" % (getattr(r, "status", "?"), len(body))
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


# ── 浏览器等效通路验证（PowerShell 走系统默认代理+DNS） ──────────────────

def web_test(target="https://github.com", timeout_sec=20):
    """Invoke-WebRequest 读 WinINET 用户设置（含 PAC），与 Edge/Chrome 默认同一条通路。
    最终仍要以真浏览器开一次页面为准（浏览器扩展与内置 DoH 脚本看不见）。"""
    ps = ("$t=[Diagnostics.Stopwatch]::StartNew();"
          "try{$r=Invoke-WebRequest -Uri '%s' -UseBasicParsing -TimeoutSec %d;"
          "$t.Stop();Write-Output ('OK ' + $r.StatusCode + ' ' + $t.ElapsedMilliseconds + 'ms')}"
          "catch{$m=$_.Exception.Message -replace \"`r|`n\",' ';Write-Output ('FAIL ' + $m)}"
          ) % (target, timeout_sec)
    ok, out, err = ps_run(ps, timeout_sec + 15)
    line = (out or "").strip().splitlines()[0] if (out or "").strip() else ""
    if line.startswith("OK "):
        return True, line[3:]
    detail = line[5:] if line.startswith("FAIL ") else (err.strip() or "no output")
    return False, detail[:160]


# ── WinHTTP（服务层，不影响浏览器） ─────────────────────────────────────

def winhttp_show():
    ok, out, err = _run(["netsh", "winhttp", "show", "proxy"], 10)
    if not ok:
        return "", err.strip()[:120]
    return " ".join(out.split()), ""


def winhttp_addr(txt):
    if not txt:
        return ""
    if "Direct access" in txt or "直接访问" in txt:
        return ""
    m = re.search(r"(?:代理服务器|Proxy Server\(s\))\s*[:：]\s*(\S+)", txt)
    return m.group(1) if m else ""


# ── 管理员权限 ──────────────────────────────────────────────────────────

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ── 状态收集与归因 ──────────────────────────────────────────────────────

def collect_state(host):
    w = read_wininet()
    ps_map = parse_proxy_server(w.get("ProxyServer"))
    ps_ports = [p for p in (addr_port(a) for a in ps_map.values()) if p]
    env_ports = []
    for var in ENV_PROXY_VARS:
        m = re.search(r":(\d+)", os.environ.get(var, ""))
        if m:
            env_ports.append(int(m.group(1)))
    candidates = list(dict.fromkeys(ps_ports + env_ports + list(COMMON_PROXY_PORTS)))
    open_ports = scan_open_ports(candidates)
    connect = {p: proxy_connect_test(p, host) for p in open_ports}
    sys_ips, sys_err = resolve_system(host)
    doh_ips, doh_ep, doh_err = doh_resolve(host)
    pins, hosts_err = hosts_pins()
    web_ok, web_detail = web_test("https://" + host)
    wht, wht_err = winhttp_show()
    return {
        "host": host, "wininet": w, "ps_map": ps_map, "ps_ports": ps_ports,
        "env_ports": env_ports, "open_ports": open_ports, "connect": connect,
        "sys_ips": sys_ips, "sys_err": sys_err, "sys_alive": alive_ips(sys_ips),
        "doh_ips": doh_ips, "doh_ep": doh_ep, "doh_err": doh_err,
        "doh_alive": alive_ips(doh_ips), "pins": pins, "hosts_err": hosts_err,
        "web_ok": web_ok, "web_detail": web_detail, "winhttp_txt": wht,
        "winhttp_err": wht_err,
    }


def print_state(st):
    w = st["wininet"]
    hr("1 系统配置（浏览器读取的三处）")
    if w.get("ProxyEnable") == 1:
        print("WinINET : 已启用  ProxyServer=%s  ProxyOverride=%s"
              % (w.get("ProxyServer") or "(空)", w.get("ProxyOverride") or "(空)"))
    else:
        print("WinINET : 未启用（浏览器直连）  ProxyServer=%s"
              % (w.get("ProxyServer") or "(空)"))
    if w.get("AutoConfigURL"):
        print("          PAC    : %s" % w["AutoConfigURL"])
    print("WinHTTP : %s" % (st["winhttp_txt"] or "(未知: %s)" % st["winhttp_err"]))
    env = {v: os.environ.get(v) for v in ENV_PROXY_VARS if os.environ.get(v)}
    print("环境变量 : %s" % (env or "(无)"))

    hr("2 本机代理端口（注册表/环境变量/常见候选，扫描+CONNECT 实测）")
    if not st["open_ports"]:
        print("（无监听）")
    for p in st["open_ports"]:
        code, first, ms = st["connect"][p]
        if code == "200":
            print("127.0.0.1:%-5d CONNECT -> %s (%dms)" % (p, code, ms))
        else:
            print("127.0.0.1:%-5d OPEN 但 CONNECT 不通: %s" % (p, (first or "")[:80]))

    hr("3 DNS（系统解析 vs DoH，443 实测）")
    if st["sys_err"]:
        print("系统解析 %s 失败: %s" % (st["host"], st["sys_err"]))
    else:
        sys_ms = {ip: ms for ip, ms in st["sys_alive"]}
        print("系统解析 %s -> %s" % (st["host"], ", ".join(
            "%s(%s)" % (ip, ("%dms" % sys_ms[ip]) if ip in sys_ms else "443不通")
            for ip in st["sys_ips"])))
    if st["doh_err"]:
        print("DoH 失败: %s" % st["doh_err"])
    else:
        doh_ms = {ip: ms for ip, ms in st["doh_alive"]}
        print("DoH(%s) -> %s" % (st["doh_ep"], ", ".join(
            "%s(%s)" % (ip, ("%dms" % doh_ms[ip]) if ip in doh_ms else "443不通")
            for ip in st["doh_ips"])))
    if st["hosts_err"]:
        print("hosts 读取失败: %s" % st["hosts_err"])
    elif st["pins"]:
        for ln, ip, h in st["pins"]:
            ok, _ = tcp443(ip)
            print("hosts 行%d: %s -> %s (%s)" % (ln, h, ip, "443通" if ok else "443不通"))
    else:
        print("hosts 无 GitHub 钉死条目")

    hr("4 浏览器等效通路（系统默认代理+DNS 的 HTTPS）")
    print("https://%s -> %s" % (st["host"],
          ("OK " + st["web_detail"]) if st["web_ok"] else ("FAIL " + st["web_detail"])))


def diagnose(st):
    """返回 (findings, plan)。plan 元素为 dict: action/port/why。"""
    findings, plan = [], []
    w = st["wininet"]
    live = [p for p in sorted(st["connect"]) if st["connect"][p][0] == "200"]
    ps_ports = st["ps_ports"]
    ps_open = [p for p in ps_ports if p in live]
    pac_ok = None
    if w.get("AutoConfigURL"):
        pac_ok, pac_detail = pac_fetch(w["AutoConfigURL"])

    def best_live():
        for p in ps_ports:
            if p in live:
                return p
        return live[0] if live else None

    if st["web_ok"]:
        return findings, plan

    pe = w.get("ProxyEnable")
    if pe == 1:
        if not st["ps_map"]:
            findings.append("ProxyEnable=1 但 ProxyServer 为空（配置不完整），浏览器按直连走")
            if live:
                plan.append({"action": "repoint-proxy", "port": best_live(),
                             "why": "本机有实测可用的代理端口，补全 ProxyServer"})
            elif st["sys_alive"]:
                findings.append("直连可达但系统通路失败：多为 TLS/证书或浏览器扩展层，脚本不可修")
            elif st["doh_alive"]:
                plan.append({"action": "flushdns", "why": "系统 DNS 解析全死而 DoH 可通，先清缓存"})
                plan.append({"action": "set-dns", "why": "清缓存后仍死则换公共 DNS（需管理员）"})
            else:
                findings.append("直连不通且无代理端口：网络整体不可达，非本机配置问题")
        elif not ps_open:
            findings.append("ProxyEnable=1，但 ProxyServer 指向的端口 %s 都没在监听——典型残留" % ps_ports)
            if live:
                plan.append({"action": "repoint-proxy", "port": best_live(),
                             "why": "代理客户端实际监听在别的端口，把浏览器指向它"})
            elif st["sys_alive"]:
                plan.append({"action": "disable-proxy",
                             "why": "代理已不在，直连可达，恢复浏览器直连"})
            elif st["doh_alive"]:
                plan.append({"action": "flushdns", "why": "先清 DNS 缓存再评估直连"})
                plan.append({"action": "set-dns", "why": "系统 DNS 解析全死而 DoH 可通，换公共 DNS（需管理员）"})
            else:
                findings.append("无活代理且直连不通：网络整体不可达，非本机配置问题")
        else:
            findings.append("ProxyServer 指向的端口在监听且 CONNECT 实测 200，但系统通路仍失败")
            if pac_ok is False:
                findings.append("AutoConfigURL 指向的 PAC 取不到（%s），PAC 优先级高于 ProxyServer" % pac_detail)
                plan.append({"action": "clear-pac", "why": "失效的 PAC 会盖过可用的 ProxyServer"})
            elif "all" not in st["ps_map"] and "https" not in st["ps_map"]:
                plan.append({"action": "repoint-proxy", "port": ps_open[0],
                             "why": "ProxyServer 是按协议分段形式且缺 https 段，归一为全协议形式"})
            else:
                findings.append("代理与 PAC 都正常仍失败：多为 TLS/证书或浏览器扩展层，脚本不可修")
    else:
        if w.get("AutoConfigURL") and pac_ok is False:
            findings.append("AutoConfigURL 指向的 PAC 取不到（%s）" % pac_detail)
            if live:
                plan.append({"action": "clear-pac", "why": "清掉失效 PAC，让浏览器走可用代理"})
        if not st["sys_alive"]:
            if live:
                findings.append("系统代理未启用，直连 IP 全部 443 不通，但本机有活代理端口 %s" % live)
                plan.append({"action": "enable-proxy", "port": live[0],
                             "why": "代理客户端开着但浏览器没用它，启用系统代理指向该端口"})
            elif st["doh_alive"]:
                findings.append("系统 DNS 把 %s 解析到全部不通的 IP，DoH 解析的 IP 可通——污染或缓存"
                                % st["host"])
                plan.append({"action": "flushdns", "why": "先清缓存，可能只是缓存了污染结果"})
                plan.append({"action": "set-dns", "why": "清完仍死则换公共 DNS（需管理员）"})
            else:
                findings.append("直连不通、无代理端口、DoH IP 也不通：网络整体不可达，非本机配置问题")
        else:
            findings.append("直连可达但系统通路失败：多为 TLS/证书或浏览器自身配置"
                            "（扩展代理、内置 DoH），脚本不可修")

    stale_pins = [(ln, ip, h) for ln, ip, h in st["pins"] if not tcp443(ip)[0]]
    if stale_pins:
        if pe != 1 or not live:
            findings.append("hosts 把 %s 钉到已失效的 IP：%s"
                            % (st["host"], "、".join("行%d %s" % (ln, ip) for ln, ip, _ in stale_pins)))
            plan.append({"action": "clean-hosts", "why": "直连场景下 hosts 优先于 DNS，死 IP 会挡住浏览器（需管理员）"})
        else:
            findings.append("hosts 有钉死条目（%s），但走代理时由代理侧解析，暂不挡路"
                            % "、".join("行%d" % ln for ln, _, _ in stale_pins))

    wh_addr = winhttp_addr(st["winhttp_txt"])
    if wh_addr:
        wp = addr_port(wh_addr)
        if wp and wp not in st["open_ports"]:
            findings.append("WinHTTP 层残留代理 %s（不影响浏览器，影响服务类进程）" % wh_addr)
            plan.append({"action": "reset-winhttp", "why": "服务类进程同样撞死端口（需管理员）"})
    return findings, plan


def print_plan(plan):
    if not plan:
        return
    hr("修复计划（按顺序，每执行一条就重跑诊断）")
    for i, p in enumerate(plan, 1):
        cmd = "python github-access/scripts/repair_github_net.py --apply %s" % p["action"]
        if p.get("port"):
            cmd += " --port %d" % p["port"]
        print("%d. %s" % (i, cmd))
        print("   为什么: %s" % p["why"])


# ── 备份与回滚 ──────────────────────────────────────────────────────────

def make_backup():
    d = BACKUP_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    d.mkdir(parents=True, exist_ok=True)
    snap = {"created": datetime.now().isoformat(), "wininet": read_wininet(),
            "adapter_dns": adapter_dns_snapshot(), "winhttp": winhttp_show()[0]}
    (d / "backup.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    if HOSTS_PATH.exists():
        shutil.copy2(HOSTS_PATH, d / "hosts.bak")
    return d


def reg_add(name, typ, value):
    return 'reg add "HKCU\\%s" /v %s /t %s /d "%s" /f' % (INET_KEY, name, typ, value)


def adapter_dns_snapshot():
    ps = ("Get-DnsClientServerAddress -AddressFamily IPv2 | "
          "Where-Object {$_.ServerAddresses} | "
          "Select-Object InterfaceAlias,@{n='Servers';e={$_.ServerAddresses -join ','}} | "
          "ConvertTo-Json -Compress")
    ok, out, _ = ps_run(ps, 15)
    if not ok or not out.strip():
        return []
    try:
        d = json.loads(out)
        if isinstance(d, dict):
            d = [d]
        return [{"iface": x.get("InterfaceAlias", ""), "servers": x.get("Servers", "")}
                for x in d]
    except Exception:
        return []


def active_iface():
    ps = ("$r=Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | "
          "Sort-Object RouteMetric | Select-Object -First 1 -ExpandProperty InterfaceAlias; "
          "Write-Output $r")
    ok, out, _ = ps_run(ps, 15)
    return (out or "").strip()


# ── 修复动作（每个返回 (做了什么, [回滚命令])） ───────────────────────────

def apply_repoint_proxy(args, bk):
    port = args.port
    code, first, _ = proxy_connect_test(port)
    if code != "200":
        print("拒绝执行：端口 %d 没有在监听或 CONNECT 实测不是 200（%s）" % (port, (first or "")[:80]))
        sys.exit(5)
    old = read_wininet()
    rollback = []
    if old.get("ProxyEnable") == 1 and old.get("ProxyServer"):
        rollback.append(reg_add("ProxyServer", "REG_SZ", old["ProxyServer"]))
    else:
        rollback.append(reg_add("ProxyEnable", "REG_DWORD", "0"))
    write_wininet("ProxyEnable", 1, winreg.REG_DWORD)
    write_wininet("ProxyServer", "127.0.0.1:%d" % port, winreg.REG_SZ)
    if old.get("AutoConfigURL"):
        delete_wininet("AutoConfigURL")
        rollback.append(reg_add("AutoConfigURL", "REG_SZ", old["AutoConfigURL"]))
        print("已同时清掉 AutoConfigURL（PAC 优先级更高，留着会盖过新 ProxyServer）")
    notify_wininet()
    return ("ProxyEnable=1，ProxyServer=127.0.0.1:%d（原值已备份）" % port), rollback


def apply_disable_proxy(args, bk):
    old = read_wininet()
    write_wininet("ProxyEnable", 0, winreg.REG_DWORD)
    notify_wininet()
    rollback = [reg_add("ProxyEnable", "REG_DWORD", "1")]
    if old.get("ProxyServer"):
        rollback.append(reg_add("ProxyServer", "REG_SZ", old["ProxyServer"]))
    return ("ProxyEnable=0（浏览器恢复直连；原 ProxyServer=%s 已备份）" % old.get("ProxyServer")), rollback


def apply_clear_pac(args, bk):
    old = read_wininet()
    if not old.get("AutoConfigURL"):
        print("没有 AutoConfigURL，无需清理")
        sys.exit(5)
    delete_wininet("AutoConfigURL")
    notify_wininet()
    rollback = [reg_add("AutoConfigURL", "REG_SZ", old["AutoConfigURL"])]
    return ("已删除 AutoConfigURL=%s" % old["AutoConfigURL"]), rollback


def apply_flushdns(args, bk):
    ok, out, err = _run(["ipconfig", "/flushdns"], 15)
    if not ok:
        print("flushdns 失败: %s" % (err or out).strip()[:120])
        sys.exit(5)
    return ("DNS 缓存已清空（缓存自动重建，无需回滚）", [])


def apply_set_dns(args, bk):
    iface = active_iface()
    if not iface:
        print("找不到默认路由所在网卡，未改动")
        sys.exit(5)
    dns = ",".join("'%s'" % d for d in PUBLIC_DNS)
    ps = "Set-DnsClientServerAddress -InterfaceAlias '%s' -ServerAddresses %s" % (iface, dns)
    ok, out, err = ps_run(ps, 20)
    if not ok:
        print("set-dns 失败: %s" % (err or out).strip()[:160])
        sys.exit(5)
    _run(["ipconfig", "/flushdns"], 15)
    old = [x for x in adapter_dns_snapshot() if x["iface"] == iface]
    if old and old[0]["servers"]:
        rollback = ["Set-DnsClientServerAddress -InterfaceAlias '%s' -ServerAddresses %s"
                    % (iface, ",".join("'%s'" % s for s in old[0]["servers"].split(",")))]
    else:
        rollback = ["Set-DnsClientServerAddress -InterfaceAlias '%s' -ResetServerAddresses" % iface]
    return ("网卡 %s 的 DNS 改为 %s（原值已备份）" % (iface, "/".join(PUBLIC_DNS))), rollback


def apply_clean_hosts(args, bk):
    text = HOSTS_PATH.read_text(encoding="utf-8", errors="replace")
    kept, removed = [], []
    for line in text.splitlines(keepends=True):
        s = line.strip()
        parts = s.split()
        if (len(parts) >= 2 and not s.startswith("#")
                and parts[1].lower() in GITHUB_HOSTS and not tcp443(parts[0])[0]):
            removed.append(s)
        else:
            kept.append(line)
    if not removed:
        print("hosts 里没有指向已死 IP 的 GitHub 条目，未改动")
        sys.exit(5)
    HOSTS_PATH.write_text("".join(kept), encoding="utf-8")
    _run(["ipconfig", "/flushdns"], 15)
    rollback = ['copy /Y "%s" "%s"' % (bk / "hosts.bak", HOSTS_PATH),
                'cp "%s" "%s"' % (bk / "hosts.bak", HOSTS_PATH)]
    return ("从 hosts 移除 %d 行已死钉死：\n    %s"
            % (len(removed), "\n    ".join(removed[:10]))), rollback


def apply_reset_winhttp(args, bk):
    old_addr = winhttp_addr(winhttp_show()[0])
    ok, out, err = _run(["netsh", "winhttp", "reset", "proxy"], 20)
    if not ok:
        print("reset-winhttp 失败: %s" % (err or out).strip()[:120])
        sys.exit(5)
    rollback = ["netsh winhttp set proxy %s" % old_addr] if old_addr else []
    return ("WinHTTP 代理已重置为直接访问（原值=%s 已备份）" % (old_addr or "直接访问")), rollback


APPLY_FUNCS = {
    "repoint-proxy": apply_repoint_proxy,
    "enable-proxy": apply_repoint_proxy,
    "disable-proxy": apply_disable_proxy,
    "clear-pac": apply_clear_pac,
    "flushdns": apply_flushdns,
    "set-dns": apply_set_dns,
    "clean-hosts": apply_clean_hosts,
    "reset-winhttp": apply_reset_winhttp,
}


def run_apply(args, host):
    if args.apply in NEEDS_PORT and not args.port:
        print("%s 需要 --port（从诊断输出的修复计划里取）" % args.apply)
        return 5
    if args.apply in NEEDS_ADMIN and not is_admin():
        print("%s 需要管理员权限：请用管理员身份重跑" % args.apply)
        return 5
    bk = make_backup()
    hr("备份")
    print("已写入 %s（wininet 注册表值、适配器 DNS、WinHTTP、hosts 副本）" % bk)
    hr("修复")
    describe, rollback = APPLY_FUNCS[args.apply](args, bk)
    print(describe)
    hr("验证（系统默认代理+DNS 的 HTTPS）")
    ips, err = resolve_system(host)
    alive = alive_ips(ips)
    if err:
        print("系统解析 %s 失败: %s" % (host, err))
    else:
        print("系统解析 -> %s；443 实测通: %s"
              % (", ".join(ips) or "(空)", ", ".join(ip for ip, _ in alive) or "(无)"))
    ok, detail = web_test("https://" + host)
    print("https://%s -> %s" % (host, ("OK " + detail) if ok else ("FAIL " + detail)))
    hr("回滚（如需撤销本次改动）")
    for c in rollback:
        print("  " + c)
    if not rollback:
        print("  （无需回滚）")
    if ok:
        print("\n验证通过。最终仍请用真浏览器开一次 https://%s 确认。" % host)
        return 3
    print("\n修复后仍不通：按 github-access 第 6 步的升级顺序继续排查，"
          "或重跑诊断看归因是否变化。不要重复执行同一动作。")
    return 4


def run_diagnose(host):
    st = collect_state(host)
    print_state(st)
    findings, plan = diagnose(st)
    if not findings and not plan:
        hr("结论")
        print("浏览器通路健康（https://%s 经系统默认配置可达），无需修复。" % host)
        wh_addr = winhttp_addr(st["winhttp_txt"])
        if wh_addr:
            print("注意：WinHTTP 层有代理 %s，只影响服务类进程，不影响浏览器。" % wh_addr)
        return 0
    hr("归因")
    for f in findings:
        print("- " + f)
    if plan:
        print_plan(plan)
    else:
        hr("结论")
        print("问题不在本脚本可修的三层配置里，按 github-access 第 6 步继续排查。")
    return 2


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="浏览器打不开 GitHub 的诊断-修复-验证（默认只读）")
    ap.add_argument("--apply", choices=ACTIONS, metavar="动作",
                    help="执行修复动作（缺省只读诊断）：%s" % "|".join(ACTIONS))
    ap.add_argument("--port", type=int, help="repoint-proxy / enable-proxy 的目标端口")
    ap.add_argument("--host", default="github.com", help="验证目标域名（默认 github.com）")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if args.apply:
        return run_apply(args, args.host)
    return run_diagnose(args.host)


if __name__ == "__main__":
    sys.exit(main())

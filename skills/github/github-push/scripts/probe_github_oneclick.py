# -*- coding: utf-8 -*-
# 一键 GitHub 连通性自检：一条命令判定「直连 / 系统代理 / 顶 IP」哪条路能用。
# 用法：python probe_github_oneclick.py
# 输出结构化 JSON：{"direct":bool, "gh_direct":bool, "system_proxy":"host:port|null",
#                   "proxy_port":"port|null", "top_ip_candidates":[...], "verdict":"direct|proxy|topip|none"}
# 设计原则：不照抄任何历史读数；代理端口从系统设置动态发现（不写死）；顶 IP 候选当场重测。
import json, os, socket, subprocess, sys, re, urllib.request

def run(cmd, timeout=8):
    """Run a command, return (ok, output)."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, creationflags=0x08000000 if sys.platform == "win32" else 0)
        return r.returncode == 0, (r.stdout or "").strip()
    except Exception as e:
        return False, str(e)

def git_direct():
    # 明确清掉代理残留，量真直连
    ok, out = run('git -c http.proxy= ls-remote https://github.com/cli/cli HEAD', timeout=12)
    return bool(out.split()) and bool(re.match(r"^[0-9a-f]{7,}", out.split()[0]))

def gh_direct():
    gh = os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Programs", "gh", "bin", "gh.exe")
    if sys.platform != "win32":
        gh = "gh"
    ok, out = run('%s api user --jq .login' % gh, timeout=12)
    return ok and bool(out.strip())

def system_proxy():
    # 动态发现：Windows 系统代理（注册表 Internet Settings）
    if sys.platform == "win32":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings")
            val, _ = winreg.QueryValueEx(k, "ProxyServer")
            en, _ = winreg.QueryValueEx(k, "ProxyEnable")
            if en and val:
                return str(val)
        except Exception:
            pass
    # 回退：环境变量
    for v in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        e = os.environ.get(v)
        if e:
            return e.replace("http://", "").replace("https://", "")
    return None

def probe_ports(extra=()):
    """系统代理端口优先，其次常见候选，逐个 0.15s 探测。"""
    cands = []
    sp = system_proxy()
    if sp:
        m = re.search(r":(\d+)$", sp)
        if m: cands.append(int(m.group(1)))
    for p in (7897, 7890, 7896, 1080, 10808, 10809, 8080, 8888):
        if p not in cands: cands.append(p)
    cands.extend(extra)
    for p in cands:
        try:
            s = socket.socket(); s.settimeout(0.15)
            if s.connect_ex(("127.0.0.1", p)) == 0:
                s.close(); return str(p)
            s.close()
        except Exception:
            pass
    return None

def top_ip_candidates():
    """当场解析 github.com 的 IP，挑可达的前几个（用 references/access.md 的方法）。"""
    ips = set()
    try:
        for a in socket.getaddrinfo("github.com", 443, type=socket.SOCK_STREAM):
            ips.add(a[4][0])
    except Exception:
        pass
    good = []
    for ip in ips:
        try:
            s = socket.socket(); s.settimeout(0.6)
            if s.connect_ex((ip, 443)) == 0: good.append(ip); s.close()
            else: s.close()
        except Exception:
            pass
        if len(good) >= 3: break
    return good

def main():
    d = git_direct()
    g = gh_direct()
    port = probe_ports()
    ips = top_ip_candidates()
    sp = system_proxy()
    if d and g:
        verdict = "direct"
    elif d:
        verdict = "git-direct-only"  # git 通 gh 不通：gh 那条挂代理
    elif port:
        verdict = "proxy"
    elif ips:
        verdict = "topip"
    else:
        verdict = "none"
    out = {
        "direct_git": d,
        "direct_gh": g,
        "system_proxy": sp,
        "open_proxy_port": port,
        "top_ip_candidates": ips,
        "verdict": verdict,
        "hint": {
            "direct": "最省事，git 与 gh 都直连",
            "git-direct-only": "git 直连可用，gh 需挂代理",
            "proxy": "走 http://127.0.0.1:" + str(port) + "（git 加 http.proxy，gh 加 HTTPS_PROXY）",
            "topip": "git 加 http.curloptResolve 顶 IP",
            "none": "三条通路各试两轮仍不可达，把失败原文交用户",
        }[verdict],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

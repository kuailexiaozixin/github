# github

GitHub 全场景 **Agent Skill**（遵循 [Agent Skills 开放标准](https://agentskills.io)）：国内网络访问与克隆、推送与认证、仓库运维（issue/PR/CI/release）、分支库（fork）跟进、Projects 看板、Codespaces、开源项目搜索、gh skill 技能管理、gh CLI 配置，浏览器打不开 GitHub 时诊断并修复系统代理/DNS/hosts 配置。一个入口 SKILL.md 分派到 9 个子技能，命令与出口判据全部在子技能里。

## 子技能（9 个）

| 子技能 | 主线 |
|---|---|
| `github-access` | 拿代码/仓库/文件；访问慢与失败处理；浏览器打不开 GitHub 时的系统代理/DNS/hosts 修复 |
| `github-push` | 交代码：push、打 tag、核对远端 |
| `github-ops` | 管仓库：issue、PR、CI、release、安全告警 |
| `github-fork` | 在别人仓库做长期改动：fork、上游同步 |
| `github-project` | 排期与看板 |
| `github-codespace` | 云端开发环境 |
| `github-search` | 找开源项目 |
| `github-skill` | gh skill 技能安装/发布/更新 |
| `github-cli` | gh 自身：登录、scope、凭证助手、别名 |

## 安装

```bash
gh skill install kuailexiaozixin/github
```

## 前置

- `gh` CLI（本技能命令在 gh 2.101.0 上实测；`gh skill` 为 preview 功能需较新版本）
- 认证：`gh auth login`，或环境变量 `GITHUB_TOKEN`（`repo` scope 用于建仓/推送）

## 红线

- 破坏性动作（force push、删远端分支/仓库、删已发布 release）执行前须向用户确认。
- 凭证值不打印、不写入仓库或工作区文件。

## License

MIT © 2026 kuailexiaozixin

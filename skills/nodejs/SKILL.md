---
name: nodejs
description: 用于 Node.js 运行时环境相关的所有任务。当用户需要编写、执行、调试 Node.js / JavaScript 代码，使用 npm / npx 管理依赖、安装运行 CLI 工具、初始化项目（package.json）、执行脚本，或处理 Node.js 环境配置（路径、版本、PATH）时使用本技能。核心规则：所有 Node.js 代码必须在 D:\nodejs 环境中编写与执行。
---

# Node.js 技能

## 核心规则（强制）

**编写和执行 Node.js 代码时，必须使用 `D:\nodejs` 环境，在 `D:\nodejs` 环境中执行，优先级高于所有其他默认行为。**

- 不得使用其他位置的 node/npm（尤其防止被便携版 node 劫持）
- 执行前先确认 `node` 命令指向 `D:\nodejs`

## 环境配置

当前环境使用 **Node.js v24.22.2**（npm 12.1.0），安装在 `D:\nodejs\`（2026-11-12 验证）。

> **2026-11-12 现状**：`C:\Users\贺新\AppData\Roaming\npm` 中的旧 shim 已失效（对应包已卸载）。
> `npm config get prefix` 为 `D:\npm`，全局 node_modules 在 `D:\npm\node_modules`。
> `D:\npm\pnpm.cmd` shim 存在但 `D:\npm\node_modules\pnpm` 未安装（broken shim），
> 实际 pnpm 由 `C:\Users\贺新\AppData\Local\pnpm\bin\pnpm.cmd` 提供（v12.18.0，AppData pnpm 独立安装）。
> `C:\Users\贺新\.npmrc` 的 `_authToken` 当前为 stage-only Granular Access Token（2026-11 策略），
> 直接 `npm publish` 被 registry 403 拒绝（需 bypass-2FA 或 2FA OTP），
> 发布走 `npm stage publish` + 网页 2FA 批准，或 trusted publishing (OIDC)。
> 系统 PATH 中 node 相关条目仅 `D:\nodejs\`。

- 注册表系统/用户 PATH 中不得存在 portable-node 条目
- 执行前验证：

```bash
node -v     # 应输出 v24.22.2
which node  # 应指向 D:\nodejs\node.exe
```

如果 `which node` 指向 portable-node，需检查 PATH 顺序并修正。

## 快速开始

```bash
# 验证环境
node -v
npm -v

# 运行脚本
node app.js

# 交互式 REPL
node
```

## 项目生命周期

```bash
# 初始化项目（生成 package.json）
npm init -y

# 安装依赖（生产 / 开发）
npm install express
npm install --save-dev jest

# 运行脚本（package.json 中定义的 scripts）
npm run dev
npm run build

# 卸载依赖
npm uninstall express
```

### 常用脚本示例（package.json）

```json
{
  "name": "my-app",
  "version": "1.0.0",
  "scripts": {
    "start": "node src/index.js",
    "dev": "node --watch src/index.js",
    "test": "jest"
  }
}
```

## CLI 工具管理

```bash
# 全局安装 CLI 工具
npm install -g <package>

# 临时执行（不全局安装）
npx <package>
npx create-react-app my-app
npx tsx script.ts

# 列出/更新全局工具
npm list -g --depth=0
npm update -g
```

## pnpm（独立安装，非 D:\npm 全局）

pnpm **不在** `D:\npm\node_modules` 中（`D:\npm\pnpm.cmd` 是 broken shim，指向不存在的模块）。

| 组件 | 路径 |
|------|------|
| pnpm 可执行 | `C:\Users\贺新\AppData\Local\pnpm\bin\pnpm.cmd`（Windows）/ `...\pnpm`（sh） |
| pnpm 版本 | 12.18.0 |
| 全局 v11 store | `C:\Users\贺新\AppData\Local\pnpm\global\v11\...`（由 AppData pnpm 自管理） |

调用方式（在 bash 会话中）：

```bash
# 方式 1：直接调 AppData pnpm（绕过 broken D:\npm\pnpm.cmd）
"C:/Users/贺新/AppData/Local/pnpm/bin/pnpm.cmd" --version
"C:/Users/贺新/AppData/Local/pnpm/bin/pnpm.cmd" install

# 方式 2：若 D:\npm\pnpm.cmd 的 shim 已修复（pnpm 已装入 D:\npm\node_modules），
# 则 export PATH="/d/nodejs:/d/npm:$PATH" 后直接用 pnpm
```

> **注意**：会话 PATH 顺序很重要。若 `D:\npm` 在 PATH 中且其 pnpm.cmd shim 仍指向缺失模块，
> 调用 `pnpm` 会报 `Cannot find module 'D:\npm\node_modules\pnpm\bin\pnpm.mjs'`。
> 此时应直接调 AppData 路径。

## npm 发布策略（2026-11 更新）

由于 npm registry 政策变更，**直接 `npm publish` 需要 bypass-2FA Granular Access Token 或交互式 2FA**。
当前 `C:\Users\贺新\.npmrc` 中的 token 为 **stage-only** 类型。

### 方案一：Trusted Publishing（OIDC）——已验证成功（2026-11-13）

**dsh-skill-mcp-market 0.5.23 已通过此方式直发 npm，无需 2FA、无需网页批准、无需 token。**

工作流程：
1. 仓库 `.github/workflows/publish.yml` 配置 `id-token: write` 权限 + `registry-url: https://registry.npmjs.org`
2. 触发器为 `push: tags: [v*]` 和 `workflow_dispatch`（dry_run 布尔输入）
3. 在 npmjs.com 包设置页（Settings → Access → Trusted Publishers）配置：
   - Provider: `github`
   - Owner: 仓库所属用户/组织
   - Repository: 仓库名
   - Workflow: `publish.yml`（必须与文件名精确匹配）
4. 推 v* tag → GitHub Action 自动运行 → `npm publish` 走 OIDC 签名直发
5. 首次配置有 48h 验证窗口，需在此期间完成一次 publish 验证

关键约束：
- Trusted Publishing 只认 `npm publish`（直发），**不认** `npm stage publish`（进 staging 队列）
- 所有 token 类型（classic / granular / bypass-2FA）均兼容 OIDC trusted publishers
- 2027-01 起 bypass-2FA granular token 不能再直接 publish，统一走 trusted publishing
- 发布证据：`_npmUser.name="GitHub Actions"`、`_npmUser.email="npm-oidc-no-reply@github.com"`、
  `_npmUser.trustedPublisher.oidcConfigId`（UUID）、SLSA provenance attestation

### 方案二：stage-only token（备用，需网页批准）

```bash
# 1. 暂存版本（stage-only token 可执行）
npm stage publish .
# → 输出：+ <pkg>@<ver> (staged with id <stage-id>)

# 2. 批准（二选一）
# (a) 网页批准：https://www.npmjs.com/package/<pkg> → Staged → Approve → 输入 6 位 2FA 码
# (b) 命令行：npm stage approve <stage-id> --otp <6位码>
```

> **不要**把 stage-only token 当作直接发布 token 使用；`npm publish` 会 403。
> 若要直接发布，需在 npm 网页新建 token：权限选 **Read and write**（直接发布，非 stage only）+ **勾选 Bypass 2FA**。
> 该能力 2027 年 1 月起将被移除，届时统一走 trusted publishing。

## 参考资料

- **Node.js 官方文档索引**：[references/llms.txt](references/llms.txt) —— Node.js 官方 `llms.txt`，**原封不动**保存，包含全部官方 API 章节（Debugger、Crypto、Buffer、FS、HTTP、Stream 等）的标题与描述链接。
- 需要编写或理解某个内置模块时，按 llms.txt 中的章节名定位对应 API 文档。

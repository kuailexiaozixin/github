---
name: github-project
description: "GitHub Projects 看板子技能——用 gh project 建看板、设计字段、把工作项推进到收口。覆盖 create/list/view、field-create/field-list/field-delete、item-add/item-create/item-list/item-edit/item-archive/item-delete、link/unlink、copy/mark-template/close/delete 全部 19 条子命令。触发关键词：看板、projects、GitHub Project、立项、排期、卡片、建字段、把工作项挂到看板、看板统计、项目收口。"
---

# GitHub Projects 看板（project）

看板上的每一行是一个**工作项**（issue、PR 或只有标题的草稿项），每一列是一个**字段**（状态、优先级、日期等）。本子技能的主线依次是立项、设计字段、灌入工作项、按字段推进、关联仓库，最后收口。

## 前置准备（只列材料）

- 已登录且 token 含 `project` 权限的 gh（取值与补权限见 github-push 的认证主线）
- 归属方：个人看板写 `@me`，组织看板写组织登录名；组织看板还需模板字段 ID
- 要挂上来的 issue/PR 链接，形式 `https://github.com/<owner>/<repo>/issues/<n>`

全流程都用**项目编号**（下面第 1 步的产出）定位看板，不用看板标题。

## 1 立项，拿到项目编号

```bash
gh project create --owner @me --title "季度交付"
```

产出：回显里带新看板的**编号**（形如 `(#12)`）。把 12 记下来，后续每步的 `<number>` 都是它。
出口：`gh project list --owner @me` 列表里有该编号。若这里就报权限错误，先回认证主线补 `project` 权限，不要改用网页建完再来。

## 2 看清默认结构，拿到字段 ID

```bash
gh project view 12 --owner @me
gh project field-list 12 --owner @me --format json
```

产出：字段清单，含每个字段的名称与 ID。默认表格里不显示字段 ID，所以要加 `--format json`；第一次用先原样打印一次看清结构，再决定是否套 `--jq`。
出口：拿到状态列的字段 ID（第 5 步 `item-edit` 的脚本路线要用）。用 `--format json` 而不是默认表格，因为表格里不输出字段 ID；`field-list` 默认只取 30 个字段，字段多时加 `-L <条数>`。

## 3 设计字段

```bash
# 单选列：--single-select-options 是列表型参数，重复传或逗号分隔一次给完都行
gh project field-create 12 --owner @me --name "风险" --data-type SINGLE_SELECT \
  --single-select-options 高 --single-select-options 中 --single-select-options 低
gh project field-create 12 --owner @me --name "优先级" --data-type SINGLE_SELECT \
  --single-select-options "P0,P1,P2"          # help 示例的逗号写法
gh project field-create 12 --owner @me --name "截止" --data-type DATE
gh project field-create 12 --owner @me --name "说明" --data-type text     # 大小写均可
gh project field-delete --id <字段ID>        # 删错了，用字段 ID，不用字段名
```

`--data-type` 只接受 `TEXT`、`SINGLE_SELECT`、`DATE`、`NUMBER` 四种（2.101.0 实测 help 原文，与 2.97.0 一致）。迭代列建不了，只能给已有迭代列赋值，用第 5 步的 `--iteration-id`。

产出：新字段出现在第 2 步的 `field-list` 里。单选列的**选项 ID** 也在这一步拿到（`field-list --format json` 里查）。
出口：`field-list` 能查到目标字段即为完成。字段建完就固定，改名不影响已存的值，但删字段会清掉所有卡片上该列的值——删前先确认没有数据要留。

## 4 灌入工作项

```bash
# 把已有的 issue / PR 挂上来：只能用 --url
gh project item-add 12 --owner @me --url https://github.com/<owner>/<repo>/issues/34
# 没有对应 issue 的临时待办，建草稿项
gh project item-create 12 --owner @me --title "整理发布清单" --body "含回滚步骤"
# 拿每项的 item ID
gh project item-list 12 --owner @me --format json
# 按看板筛选语法过滤，比拉全量 JSON 再自己筛省事
gh project item-list 12 --owner @me --query "assignee:@me is:issue is:open"
gh project item-list 12 --owner @me --query "label:bug -status:Done" --field "Status"
```

产出：`item-list` 里出现该项，记下 `id`（即 `<item-ID>`）。
`item-list` 默认只取 30 项，看板大了要加 `-L <条数>`；`--field`/`--field-id` 可重复，把指定字段的值作为额外列显示，`--query` 的过滤语法与网页看板一致（`-status:Done` 前的减号表示"不等于"）。
出口：`item-list` 能查到。注意 `item-add` 不支持 `--repo`、`--title`（2.101.0 实测它只有 `--url/--owner/--format`），要按仓库批量入板只能在 shell 里循环 issue URL。

## 5 按字段推进

`item-edit` 有两条定位路线，help 把第一条称作"usual way"，日常手工用它；第二条是给脚本用的 node ID 路线：

```bash
# 常规：项目编号 + --owner + issue/PR 链接 + 字段名；单选列填选项文字
gh project item-edit 12 --owner @me --url https://github.com/<owner>/<repo>/issues/34 \
  --field "Status" --value "Done"
# 脚本：全用 node ID，取值参数按字段类型选一个
gh project item-edit --id <item-ID> --field-id <字段ID> --project-id <项目ID> --text "新说明"
gh project item-edit --id <item-ID> --field-id <字段ID> --project-id <项目ID> --clear   # 清空这一列
```

脚本路线的取值参数按字段类型对应：

| 字段类型 | 取值参数 |
|---|---|
| TEXT | `--text` |
| NUMBER | `--number`（float 类型） |
| DATE | `--date 2026-10-15`（help 标注格式 YYYY-MM-DD） |
| SINGLE_SELECT | `--single-select-option-id`（选项 ID 来自第 3 步的 `field-list --format json`） |
| ITERATION 列 | `--iteration-id` |
| 草稿项改标题/正文 | `--title` / `--body` |

三条容易踩的点，都是 help 原文写明的：
- `--project-id` 是项目 node ID，从 `gh project view 12 --owner @me --format json` 取，与项目编号 12 不是一个值
- `--url` 是 issue/PR 的链接而不是看板链接，所以它的 owner 可以不同于看板 owner——`--owner` 选的是看板归属方
- 非草稿项一次调用只能改一个字段的值；要改两列就分两次执行

出口：`item-list 12 --owner @me --query "..."` 或 `--format json` 里该项该列的值已变。报错会指名是 `--field-id`、`--project-id` 还是选项 ID 不对，按提示回到第 2、3 步重新取值。

## 6 与仓库、团队挂钩

```bash
gh project link 12 --owner @me --repo <仓库名>        # 关联本看板 owner 名下的仓库
gh project link 12                                     # --repo/--team 都不给时，关联当前目录所在仓库
gh project link 12 --owner <org> --team <team-slug>    # 团队关联只在组织看板下用
gh project unlink 12 --owner @me --repo <仓库名>       # 解除，看板本身保留
# 看板自身的名字、描述、说明与可见性
gh project edit 12 --owner @me --title "季度交付" --visibility PRIVATE
gh project edit 12 --owner @me --description "一句话说明"
gh project edit 12 --owner @me --readme "使用说明：状态列只有三档，超期看截止列"
```

`--repo` 取的是仓库名（help 示例为 `--repo my_repo`），不是 `owner/repo` 全名；owner 由 `--owner` 决定。`--visibility` 只有 `PUBLIC|PRIVATE` 两个值。`link` 与 `unlink` 参数集相同（`--owner` / `-R, --repo` / `-T, --team`）。
出口：`gh project view 12 --owner @me`（加 `-w` 直接在浏览器打开看板）的关联列表里出现该仓库或团队，标题/描述/说明/可见性与设定一致。

## 7 收口

```bash
gh project item-archive 12 --owner @me --id <item-ID>    # 完成的项归档，不占活跃视图
gh project item-archive 12 --owner @me --id <item-ID> --undo   # 归档错了撤回
gh project item-delete 12 --owner @me --id <item-ID>     # 只删草稿项；删掉即无，归档优于删除
gh project close 12 --owner @me                          # 整个看板收口，可读不可写
gh project close 12 --owner @me --undo                   # 重新开工
gh project copy 12 --source-owner <org> --target-owner @me --title "我的副本" --drafts
gh project mark-template 12 --owner <org>                # 设为组织模板，供别人复制；--owner 要组织登录名
gh project mark-template 12 --owner <org> --undo        # 取消模板
gh project delete 12 --owner @me                         # 不可恢复
```

出口：`gh project list --owner @me` 只剩该留的看板。`list` 默认不含已关闭的，加 `--closed` 才显示。

## 红线

- `project delete` 与 `item-delete` 不可恢复，与 `close`、`item-archive` 是两件事：收口保留数据，删除清空数据。删除前需用户明确确认。
- 归档、模板化、复制只对组织或本人有写权限的看板生效，遇到 403 先查权限再查命令。

## 出口：取权威参数

```bash
gh project --help
gh project item-edit --help
```

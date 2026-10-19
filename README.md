# branchs

多分支管理工具，支持 CLI 和 GUI 两种模式。

## 安装

```bash
pip install -e .
```

## 快速开始

```bash
# CLI 模式
branchs --help

# GUI 模式
branchs-gui
```

## 分支管理

### 查看分支列表

```bash
branchs branch list
branchs branch list --remote  # 查看远程分支
```

### 设置分支类型和上下游关系

分支类型: `main` | `project` | `feature` | `release` | `hotfix`

```bash
branchs branch set-type main main --description "主分支"
branchs branch set-type develop project --upstream main
branchs branch set-type feat-login feature --upstream develop
branchs branch set-type release-1.0 release
```

### 设置默认分支

不指定 source 时，默认将默认分支合并到目标分支。

```bash
branchs branch set-default main
```

### 查看同级分支

同级分支 = 从同一个 commit 切出的分支。

```bash
branchs branch siblings
branchs branch siblings feat-login
```

### 查看分支差异

```bash
# 摘要
branchs branch diff feature project
# 完整 diff
branchs branch diff feature project --full
```

### 删除分支配置

```bash
branchs branch remove feat-login
```

## 合并操作

### 合并两个分支

```bash
branchs merge do -s feature -t develop
branchs merge do -s feature -t develop --mode keep   # 冲突时保留现状
branchs merge do -s feature -t develop --mode abort  # 冲突时回退 (默认)
branchs merge do -s feature -t develop --no-ff       # 禁用快进合并
```

设置了默认分支后，可不指定 source：

```bash
branchs merge do -t develop  # 将默认分支合并到 develop
```

### 一对多合并

```bash
branchs merge multi -s feature -t develop -t release-1.0 -t main
```

### 默认分支合并

```bash
branchs merge default -t develop
```

## Rebase 操作

在当前分支（或指定分支 a）下将分支变基到目标分支 b：

```bash
# 在当前分支下 rebase 到 target/upstream 分支 (如 b 分支)
branchs rebase do -u <b_branch>

# 指定将 a 分支 rebase 到 b 分支
branchs rebase do -b <a_branch> -u <b_branch>

# 指定冲突处理模式
branchs rebase do -u <b_branch> --mode abort  # 冲突时自动回退 (默认)
branchs rebase do -u <b_branch> --mode keep   # 冲突时保留现状供手动处理

# 冲突解决后的辅助命令
branchs rebase continue  # 解决冲突后继续变基
branchs rebase skip      # 跳过当前冲突提交
branchs rebase abort     # 中止变基操作

# 也可以通过 branch 子命令执行
branchs branch rebase -u <b_branch>
```

## Commit 管理

### 自动提交

```bash
# IDEA 当前 changelist（默认）
branchs commit auto

# 自定义 message
branchs commit auto -m "feat: 添加登录功能"

# 显式提交所有已暂存改动或指定的已暂存文件
branchs commit auto --mode all
branchs commit auto --mode all -f src/login.py -f tests/test_login.py
```

### 同步父分支后提交并推送

先给当前分支配置父分支。例如，`a` 从 `b` 切出：

```bash
branchs branch set-type a feature --upstream b
branchs commit publish -m "feat: 更新 a"
branchs commit publish --preview  # 只查看新提交将包含的文件，不访问远端或修改仓库
branchs commit publish --mode all -m "feat: 更新 a"  # 显式提交所有已暂存改动
```

`publish` 会抓取 `origin/a` 和 `origin/b`，先将本地 `a` 的提交接在最新的 `origin/a` 后面，再将 `a` 变基到 `origin/b`。工作区的未提交改动会临时保存，变基完成后恢复、提交并推送。若变基改写了已推送的提交，使用带明确期望值的 `--force-with-lease`；若远端有新的并发提交，推送会失败，保留本地提交。可用 `-r` 指定其他 remote。

所有提交模式都只使用 Git 暂存区中已有的改动。branchs 不运行 `git add`，未暂存的文件或同一文件的未暂存代码片段不会进入新提交。默认 `idea` 模式还要求暂存文件都属于 IntelliJ IDEA 当前 changelist；如果暂存区含有其他 changelist 的文件，就停止并提示先自行取消暂存。程序从 `.idea/workspace.xml` 读取当前 changelist；找不到项目或列表时会停止，不会扩大提交范围。**Unversioned Files** 不属于当前 changelist。同一文件跨多个 changelist 时也会停止，请在 IDEA 内完成这类分块提交。CLI 在执行前列出实际暂存文件；GUI 的 **Commit** 页可切换模式、预览并确认。已经存在的本地提交也可能随推送一起上传，不属于这个“新提交文件”列表。

branchs 发起的 Git 网络命令始终直连，不使用环境变量或 Git 配置中的 HTTP 代理，也不会修改 Windows 或 Git 的持久代理配置。

### 建议 commit message

```bash
branchs commit suggest
```

### 查看提交历史

```bash
branchs commit log
branchs commit log -n 10                    # 最近 10 条
branchs commit log --author "张三"          # 按作者筛选
branchs commit log --since "2024-01-01"     # 按时间筛选
branchs commit log --grep "fix"             # 按 message 筛选
branchs commit log -b develop               # 查看指定分支
```

### 回退提交

```bash
branchs commit revert <commit_hash>
```

### Cherry-pick

会分析受影响文件数量，评估是否值得 cherry-pick。

```bash
branchs commit cherry-pick <commit_hash> -t develop
branchs commit cherry-pick <commit_hash> -t develop --mode keep
```

## 文件级合并

将指定文件从 source 合并到 target，会自动分析关联文件并给出建议。

```bash
branchs file merge src/login.py -s feature -t develop
branchs file merge config.yaml -s feature -t develop --mode abort
```

## 多 Remote 管理

### 查看项目下已配置的 Remote

```bash
branchs remote list
```

### 配置主副 remote

```bash
branchs remote set -p origin -s upstream
```

### 一键同步

将主 remote 的所有分支同步到副 remote。冲突时保留副 remote 现状，给出提示。结束后会生成总结报告。

```bash
branchs remote sync
branchs remote sync -p origin -s mirror
```

## 配置管理

### 查看配置

```bash
branchs config show
```

### 设置冲突处理模式

```bash
branchs config set-mode abort  # 冲突自动回退 (默认)
branchs config set-mode keep   # 冲突保留现状
```

## GUI 模式

```bash
branchs-gui
```

GUI 会记住上次打开的仓库，下次启动时自动打开。窗口顶部的 **Repository** 下拉框或 **Menu → Recent repositories** 可切换最近使用的仓库；点击 **Open** 可添加其他仓库。已不存在的路径会自动跳过。最近仓库最多保存 10 个，记录保存在 `~/.config/branchs/config.json`。

GUI 提供 **Light** 和 **Dark** 两种主题。点击窗口顶部的主题按钮即可立即切换，也可在 **Settings → Appearance** 选择；下次启动会沿用上次选择。

在 **Commit** 页，先选择提交类型（如 `fix`、`feat`、`chore`），填写摘要，可选填影响范围、详细说明和不兼容变更标记。提交信息按 [Conventional Commits 1.0.0](https://www.conventionalcommits.org/zh-hans/v1.0.0/) 生成，例如 `fix(gui): 修复内网连接`。下方表格列出当前模式将提交的已暂存文件。**Publish** 执行时会弹出进度窗口，显示正在查询远端、获取分支、变基、提交或推送的步骤。

**Cherry-pick** 的 Target 表示接收所选提交的本地目标分支。成功后 GUI 会切回原分支；目标分支不会自动推送。

包含 6 个标签页：

- **Branches**: 分支列表、类型/上下游设置、默认分支、同级分支查看
- **Merge**: 可视化合并操作，输出合并结果
- **Rebase**: 可视化变基操作，支持 Rebase / Continue / Skip / Abort
- **Commit**: 提交历史、自动提交、cherry-pick、revert
- **Remote Sync**: 配置并执行远程同步，查看同步报告
- **Config**: 设置默认分支、合并模式等

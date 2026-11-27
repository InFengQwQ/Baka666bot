# 维护约定

## 干净

- 干净 = 可维护，不是什么都不动；收尾清掉临时文件、死代码、死配置。
- 仓库不放二进制、大资源、依赖（Java、Chromium、FFmpeg、NapCat、构建产物、测试样本）；能默认就默认，不多加文件或配置；配置与数据分离，本地状态不入库。
- 不打临时补丁、不加兜底；简洁优先，但不为省字砍掉必要的健壮性检查。

## 资源

- 资源放 GitHub Release，三类 tag：`replay-renderer-<ver>`、`assets-<date>`、`napcat-<ver>`。
- `assets-manifest.json` 固定 url/size/sha256，`fetch-assets.py` 拉取；启动脚本可以代拉，但要保持简单，不堆 PATH/echo。
- Docker 构建期只拉 Linux 需要的那部分。

## 文档与注释

- README 极简、面向使用者，只写跑起来的步骤；部署事实、登录、操作、已知行为写 x30a-server。
- 注释写为什么，用短语；行内注释两个空格加 `#`；不写无信息注释和大段注释块。
- 改上游代码前写清原契约，放在 commit 或代码旁，不堆文档。

## 配置

- `.env`、`config/*.env`、`data/`、`NapCat.Shell/` 是本地状态，不入库。
- `.env.example` 列全所有键，同一层级的键同进同出；空值能触发默认就写空，或统一写默认值，不混用。
- 线上 compose 用 `env_file` 读 `.env`，不把值硬编码进 `environment`。

## 提交与分支

- 一次一个方向：适配、通用修复、清理、配置各自独立；英文 conventional；Linux 专用修复算适配；改动多了重整 commit。
- `main` 只放 fork 自有、能直接跑的内容；可上游修复从 `upstream/main` 开 `upstream/<主题>` 单提交，cherry-pick 回 `main`；子模块修复单独分支；同步用 merge，不改写历史；分支在仓库外 worktree 开。

## 依赖与来源

- 先看文件属于哪个仓库：`src/plugins/` 下四个子模块目录属于各自仓库，其余（`Malody_toolkit`、`avatar_card` 等）属于 `MCPsDE/Baka666bot`。
- 子模块里的问题先到根仓库找同一段代码，按根 → 中间 → 我们的顺序确认是谁引入的，PR 提给根；没有自己 fork 的提到 MCPsDE。
- 子模块指针上移前，确认那个提交已推到对应远端，否则 CI 的 checkout 会失败。

| 子模块 | 根 | 中间 | 我们的 fork |
|---|---|---|---|
| `nonebot-plugin-for-osumania4k` | `Nick2357111/…` | `MCPsDE/…` | `InFengQwQ/…` |
| `nonebot_plugin_osubot` | `yaowan233/…` | `MCPsDE/…` | `InFengQwQ/…` |
| `nonebot_plugin_osugreek` | `YakumoZn/…` | `MCPsDE/…` | 无 |
| `nonebot_plugin_osumania_toolkit` | `LeoBlackMT/…` | `MCPsDE/…` | 无 |

## 同步与发布

- 每周日 0 点同步一次，只开 PR（`chore/sync-fork`），不自动合 `main`；上游 NapCat 不得覆盖本地冻结的 4.18.42；`DROP_PATHS` 跟着维护，`KEEP_PATHS` 只留子模块指针；出现未登记的二进制直接失败；冲突先用三行说明再等决定。
- 镜像在 push `main` 时自动构建，tag 为构建日期加运行序号，另附 `latest`，compose 用 `latest`；线上手动 `pull`，不自动更新。

## 验证与交流

- 能读代码、配置、网络定论的不实测；不反复测同一项；必须实测用真实样本；一次报告全量缺口；测完清现场。
- 提交前跑 `uv run ruff check`：只查会导致运行错误的那部分 F 规则，规则集写在 `pyproject.toml`。
- 先说明再做，没让做的不做；不确定先问；范围一次说全；结论用事实和数字。

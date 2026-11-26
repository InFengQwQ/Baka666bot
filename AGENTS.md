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

## 同步与发布

- 每周日 0 点同步一次，只开 PR（`chore/sync-fork`），不自动合 `main`；上游 NapCat 不得覆盖本地冻结的 4.18.42；`DROP_PATHS`/`OURS_PATHS` 跟着维护；冲突先用三行说明再等决定。
- 镜像推 GHCR，`latest` 加提交 sha；线上手动 `pull`，不自动更新。

## 验证与交流

- 能读代码、配置、网络定论的不实测；不反复测同一项；必须实测用真实样本；一次报告全量缺口；测完清现场。
- 先说明再做，没让做的不做；不确定先问；范围一次说全；结论用事实和数字。

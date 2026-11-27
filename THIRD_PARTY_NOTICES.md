# Third-Party Notices

The following plugin sources are included as independent repositories or local forks. Their upstream projects retain copyright and license notices.

| Component | Upstream | Fork branch | License |
| --- | --- | --- | --- |
| nonebot-plugin-osubot | [yaowan233/nonebot-plugin-osubot](https://github.com/yaowan233/nonebot-plugin-osubot) | [MCPsDE/nonebot-plugin-osubot](https://github.com/MCPsDE/nonebot-plugin-osubot/tree/baka666bot) | AGPL-3.0, see [license text](licenses/nonebot-plugin-osubot.txt) |
| nonebot-plugin-osugreek | [YakumoZn/nonebot-plugin-osugreek](https://github.com/YakumoZn/nonebot-plugin-osugreek) | [MCPsDE/nonebot-plugin-osugreek](https://github.com/MCPsDE/nonebot-plugin-osugreek/tree/baka666bot) | MIT, see [license text](licenses/nonebot-plugin-osugreek.txt) |
| nonebot-plugin-osumania-toolkit | [LeoBlackMT/nonebot-plugin-osumania-toolkit](https://github.com/LeoBlackMT/nonebot-plugin-osumania-toolkit) | [MCPsDE/nonebot-plugin-osumania-toolkit](https://github.com/MCPsDE/nonebot-plugin-osumania-toolkit/tree/baka666bot) | MIT, see [license text](licenses/nonebot-plugin-osumania-toolkit.txt) |
| nonebot-plugin-for-osumania4k | [Nick2357111/nonebot-plugin-for-osumania4k](https://github.com/Nick2357111/nonebot-plugin-for-osumania4k) | [MCPsDE/nonebot-plugin-for-osumania4k](https://github.com/MCPsDE/nonebot-plugin-for-osumania4k) | No upstream license file or license metadata was found. This project does not assign a license to that code. |

Additional bundled components:

- `ManiaReplayMaster.jar` is downloaded from the `replay-renderer-2.4.0` release by `scripts/fetch-assets.py`; the jar includes the Apache License 2.0 and notice under `META-INF/`.
- `isnet-anime.onnx` is downloaded from the `assets-2026.11.26` release by `scripts/fetch-assets.py`. The weights are the anime character segmentation model from [SkyTNT/anime-segmentation](https://github.com/SkyTNT/anime-segmentation), licensed Apache-2.0.
- `nlohmann/json` 3.11.3 is included under MIT; its SPDX notice is retained in `src/plugins/Malody_toolkit/json.hpp`.
- The ECharts bundle in `nonebot_plugin_osubot` retains its Apache-2.0 and MIT notices in the JavaScript file header.
- FFmpeg is no longer bundled. `ffmpeg` and `ffprobe` are resolved from `PATH` and stay under the license of the installed build.
- Wine is installed from the Debian package archive when the Docker image is built and is not distributed with this repository; it stays under LGPL-2.1-or-later.
- The legacy `ma2om`, `ncm2mp3` and `prontom` executables are downloaded from the `assets-2026.11.26` release. No license notices or metadata were present in the supplied files, so this project does not assign a license to them.
- On Linux `ma2om.exe`, `ncm2mp3.exe` and `prontom.exe` are downloaded and run through wine; the old `mp32ogg`, `ncm2ogg` and `DragUnzip` wrappers are no longer used or downloaded.
- The bundled Eclipse Temurin JRE was removed; `ManiaReplayMaster.jar` now runs on a system Java 11+ runtime that is not distributed with this repository.
- Chromium is installed by Playwright and is not distributed with this repository.
- `NapCat.Shell/` is deployed locally from [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) and is not tracked by this repository. No license file or repository license metadata was present in the supplied runtime/source; this project does not assign a license to it.
- The local Malody conversion tools include `ma2om.exe`, `ncm2mp3.exe` and `prontom.exe`; `inverse.py`, `tojack.py` and `prontom.cpp` are tracked source. The source folder supplied no license metadata for these files; no license is assigned by this project.
- `MalodyVClientPlugin` documents protocol references to [Mugzone/Emiria](https://github.com/Mugzone/Emiria). The upstream repository does not declare a license, and this project does not claim a license for it.

Python dependencies installed from `pyproject.toml` remain subject to the licenses shipped with their respective package distributions.

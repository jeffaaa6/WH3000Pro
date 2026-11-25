# WH3000 Pro 固件云编译

适用于华思飞 WH3000 Pro eMMC 版（MT7981B）。默认用 [LEDE](https://github.com/coolsnowwolf/lede)，也可切换到[华思飞源码](https://github.com/huasifei-source/huasifei-source)。

默认 LEDE 配置包含 QModem v3.3.0（经典界面及短信）、风扇温控、手机 USB 共享、OpenClash、MosDNS 和 PassWall。OpenClash 的核心可在插件页面中安装。

## 编译

1. 在 [Actions](https://github.com/jeffaaa6/WH3000Pro/actions) 打开 **Build WH3000 Pro Firmware**，点击 **Run workflow**。
2. `source` 默认是 `lede`。仅检查编译准备和磁盘空间时，选择 `prepare_only`；试编译时可取消 `upload_release`。
3. 完成后从本次运行的 **Artifacts** 下载固件、SHA256 校验值和实际选包配置。启用 `upload_release` 时也会上传到 **Releases**。

## 定制

- [LEDE 选包](config/wh3000-pro-lede.config) · [华思飞选包](config/wh3000-pro-huasifei.config)
- 软件源在 [diy-part1.sh](scripts/diy-part1.sh)，自定义文件放进 [files/](files/)。

刷机前请备份。升级使用对应 WH3000 Pro **eMMC** 的 `sysupgrade.bin`；跨固件切换时请取消保留配置。

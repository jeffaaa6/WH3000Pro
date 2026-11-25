# Huasifei WH3000 Pro (eMMC) OpenWrt/LEDE 云编译配置仓库

本仓库为 **华思飞 WH3000 Pro (eMMC / MT7981B Filogic 820)** 的独立固件云编译配置骨架，通过 GitHub Actions 按需拉取上游源码并构建固件，避免直接 Fork 庞大源码仓带来的同步冲突。

- **默认编译基线**：[`coolsnowwolf/lede`](https://github.com/coolsnowwolf/lede)（`master` 分支，目标机型 `huasifei_wh3000-pro`）
- **可选切换基线**：[`huasifei-source/huasifei-source`](https://github.com/huasifei-source/huasifei-source)（`main` 分支，目标机型 `huasifei_wh3000-pro-emmc`）
- **核心预置能力**：
  - 蜂窝 / USB 3.0 / 5G 模组驱动（覆盖 MBIM / QMI / NCM / ECM / RNDIS / USB 串口，适配 Foxconn T99W368 等模组）
  - [`FUjr/QModem`](https://github.com/FUjr/QModem) 5G 模组拨号与短信管理 UI
  - [`JiaY-shi/fancontrol`](https://github.com/JiaY-shi/fancontrol) PWM 风扇温控，并内置 `uci-defaults` 首次开机自动探测 `pwmfan` 真实 `hwmon` 节点（解决 `hwmon1` / `hwmon2` 漂移问题）
  - 预留 `lua` 与 `luci-compat`，便于后续按需迁入自定义 Lua 适配脚本

---

## 目录结构

```text
WH3000Pro/
├── .github/workflows/
│   └── build.yml                     # GitHub Actions 手动触发云编译工作流（支持切换 LEDE / huasifei-source）
├── config/
│   ├── wh3000-pro-lede.config        # coolsnowwolf/lede 精简选包种子配置
│   └── wh3000-pro-huasifei.config    # huasifei-source 精简选包种子配置
├── scripts/
│   ├── diy-part1.sh                  # feeds update 前执行：注入 QModem、fancontrol 等外部 feed
│   └── diy-part2.sh                  # feeds install 后执行：自定义 IP/主机名、补丁与兼容性修复
├── files/                            # 覆写根目录：随固件一起打包进 ROM（切勿放入隐私信息）
│   ├── README.md
│   └── etc/uci-defaults/
│       └── 99-wh3000pro-custom       # 首次启动自动修正 fancontrol 的 pwmfan 路径
├── .gitignore
└── README.md
```

---

## 使用方式

### 1. 触发云编译

进入仓库的 **Actions** → 选择 **Build WH3000 Pro Firmware** → 点击 **Run workflow**，按需调整参数：

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `source` | `lede` | 上游源码选择：`lede`（`coolsnowwolf/lede`）或 `huasifei`（`huasifei-source`） |
| `lan_ip` | `192.168.1.1` | 固件默认管理口 LAN IP |
| `hostname` | `WH3000Pro` | 固件默认主机名 |
| `ssh_menuconfig` | `false` | 勾选后在 `make defconfig` 阶段暂停并开启 `tmate` 远程终端，可运行 `make menuconfig` 并用 `./scripts/diffconfig.sh` 导出精简配置 |
| `upload_release` | `true` | 编译完成后自动发布 GitHub Release（含固件与 `sha256sums.txt`） |
| `enable_dl_cache` | `true` | 缓存 `dl/` 源码包目录以加快后续构建 |

### 2. 下载产物

编译完成后，可在 **Releases** 或本次运行页面的 **Artifacts** 中下载：

- `*-squashfs-sysupgrade.bin`：正式刷入 eMMC 的升级固件
- `*-initramfs-kernel.bin`：纯内存运行版镜像（用于调试或恢复）
- `sha256sums.txt`：固件校验和
- `seed-diffconfig.config` / `full.config`：本次构建实际生效的精简与完整配置

---

## 定制与维护建议

1. **只维护精简选包配置**：日常增删软件包请编辑 `config/wh3000-pro-lede.config` 或 `config/wh3000-pro-huasifei.config`，由云端每次执行 `make defconfig` 自动解算依赖，避免完整 `.config` 随上游迭代失效。
2. **自定义脚本放进 `files/`**：例如后续需要打包自己的 T99W368 守护脚本时，按路由器根路径放入 `files/` 目录即可（详见 [files/README.md](files/README.md)）。
3. **公开仓库隐私红线**：**切勿**将 WiFi 密码、SSH 私钥、代理节点订阅、个人 APN/账号密码或 `factory`/`fip` 硬件分区备份提交到本仓库。

---

## 刷机注意事项（WH3000 Pro eMMC）

- **核对机型**：确认刷入的文件名对应 **WH3000 Pro eMMC**（不含 `nand` 字样）。
- **跨发行版切勿保留配置**：从 QWRT、官方 OpenWrt、LEDE、`huasifei-source` 之间互刷时，由于内核、WiFi 驱动（闭源 `mt798x` vs 开源 `mt7915e`）与包管理器存在差异，务必使用 `sysupgrade -n` 或在网页取消勾选「保留当前配置」。
- **先备份再尝鲜**：首次刷机前建议先在本地离线备份路由器的 `factory`、`fip` 分区及原有配置，且日常换固件切勿刷写 U-Boot / BL2 / GPT。

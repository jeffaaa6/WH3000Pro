#!/usr/bin/env bash
# ==============================================================================
# diy-part2.sh
# 执行时机：`./scripts/feeds install -a` 之后、`make defconfig` 之前
# 工作目录：上游 OpenWrt/LEDE 源码根目录
# 作用：应用定制补丁、修改默认 LAN IP 与主机名、修正 WH3000 Pro 槽位配置等
# ==============================================================================
set -euo pipefail

BUILD_SOURCE="${BUILD_SOURCE:-lede}"
LAN_IP="${LAN_IP:-192.168.1.1}"
HOSTNAME="${HOSTNAME:-WH3000Pro}"
# 针对 huasifei-source：是否保留上游 FUjr/QModem 的 modem_support.json（避免旧补丁覆盖 T99W368 等新模组）
KEEP_UPSTREAM_MODEM_JSON="${KEEP_UPSTREAM_MODEM_JSON:-true}"

echo "[diy-part2] 当前编译基线: ${BUILD_SOURCE}"
echo "[diy-part2] 默认 LAN IP: ${LAN_IP} | 主机名: ${HOSTNAME}"

# ------------------------------------------------------------------------------
# 1. huasifei-source 专属：应用仓库自带的 patches/feeds 补丁
# ------------------------------------------------------------------------------
if [ "${BUILD_SOURCE}" = "huasifei" ] && [ -d "./patches/feeds" ]; then
    echo "[diy-part2] 检测到 huasifei-source patches/feeds，正在应用补丁..."
    MODEM_JSON_REL="qmodem/application/qmodem/files/usr/share/qmodem/modem_support.json"
    MODEM_JSON_BAK=""

    if [ "${KEEP_UPSTREAM_MODEM_JSON}" = "true" ] && [ -f "./feeds/${MODEM_JSON_REL}" ]; then
        MODEM_JSON_BAK="$(mktemp)"
        cp -f "./feeds/${MODEM_JSON_REL}" "${MODEM_JSON_BAK}"
        echo "[diy-part2] 已暂存上游 QModem modem_support.json"
    fi

    cp -rpf ./patches/feeds/. ./feeds/

    if [ -n "${MODEM_JSON_BAK}" ] && [ -f "${MODEM_JSON_BAK}" ]; then
        cp -f "${MODEM_JSON_BAK}" "./feeds/${MODEM_JSON_REL}"
        rm -f "${MODEM_JSON_BAK}"
        echo "[diy-part2] 已还原上游最新版 QModem modem_support.json（保留 T99W368 等模组定义）"
    fi
fi

# ------------------------------------------------------------------------------
# 2. 修复 QModem 预设槽位脚本对 huasifei,wh3000-pro* 的兼容（兼容 eMMC 机型名）
#    同时兼容 QModem v3.x (board.d/03_qmodem) 与旧版 (uci-defaults/99-add-5g-handler)
# ------------------------------------------------------------------------------
for handler_file in \
    "feeds/qmodem/application/qmodem/files/etc/board.d/03_qmodem" \
    "feeds/qmodem/application/qmodem/files/etc/uci-defaults/99-add-5g-handler"; do
    if [ -f "${handler_file}" ] && grep -q 'huasifei,wh3000-pro)' "${handler_file}"; then
        sed -i 's/huasifei,wh3000-pro)/huasifei,wh3000-pro*)/g' "${handler_file}"
        echo "[diy-part2] 已扩展 ${handler_file} 的匹配模式为 huasifei,wh3000-pro*)"
    fi
done

# ------------------------------------------------------------------------------
# 3. 修改默认 LAN IP 与主机名（兼容 LEDE 新版 luci2 路径与传统 files 路径）
# ------------------------------------------------------------------------------
CONFIG_GEN_CANDIDATES=(
    "package/base-files/luci2/bin/config_generate"
    "package/base-files/files/bin/config_generate"
)

for cfg_gen in "${CONFIG_GEN_CANDIDATES[@]}"; do
    if [ -f "${cfg_gen}" ]; then
        if [ "${LAN_IP}" != "192.168.1.1" ]; then
            sed -i "s/192\.168\.1\.1/${LAN_IP}/g" "${cfg_gen}"
            echo "[diy-part2] 已将 ${cfg_gen} 默认 LAN IP 修改为 ${LAN_IP}"
        fi

        if [ -n "${HOSTNAME}" ]; then
            sed -i "s/set system\.@system\[-1\]\.hostname='[^']*'/set system.@system[-1].hostname='${HOSTNAME}'/g" "${cfg_gen}"
            echo "[diy-part2] 已将 ${cfg_gen} 默认主机名修改为 ${HOSTNAME}"
        fi
    fi
done

# ------------------------------------------------------------------------------
# 4. 确保复制到源码的自定义 uci-defaults / init.d 脚本具备可执行权限
# ------------------------------------------------------------------------------
for exec_dir in "files/etc/uci-defaults" "files/etc/init.d"; do
    if [ -d "${exec_dir}" ]; then
        chmod +x "${exec_dir}"/* 2>/dev/null || true
    fi
done

echo "[diy-part2] 自定义处理完成"

#!/usr/bin/env bash
# ==============================================================================
# diy-part1.sh
# 执行时机：克隆上游源码后、`./scripts/feeds update -a` 之前
# 工作目录：上游 OpenWrt/LEDE 源码根目录
# 作用：按需向 feeds.conf.default 注入第三方软件源（幂等执行，避免重复追加）
# ==============================================================================
set -euo pipefail

BUILD_SOURCE="${BUILD_SOURCE:-lede}"
FEEDS_FILE="feeds.conf.default"
if [ -f feeds.conf ]; then
    FEEDS_FILE="feeds.conf"
fi

echo "[diy-part1] 当前编译基线: ${BUILD_SOURCE}"

if [ ! -f "${FEEDS_FILE}" ]; then
    echo "[diy-part1] 错误：未找到 ${FEEDS_FILE}" >&2
    exit 1
fi

ensure_feed() {
    local feed_name="$1"
    local feed_line="$2"

    # 若已存在未注释的同名 feed，则跳过避免冲突
    if grep -Eq "^[[:space:]]*src-[a-z-]+[[:space:]]+${feed_name}[[:space:]]" "${FEEDS_FILE}"; then
        echo "[diy-part1] Feed '${feed_name}' 已存在，跳过追加"
    else
        echo "${feed_line}" >> "${FEEDS_FILE}"
        echo "[diy-part1] 已添加 Feed: ${feed_line}"
    fi
}

if [ "${BUILD_SOURCE}" = "lede" ]; then
    # QModem v3.3.0 正式版
    QMODEM_COMMIT="5cc80e5f9fc218cd50bef9749dc7d0027e8b3072"

    # 按上游说明优先选择 MosDNS、PassWall 的同名包。
    feed_config=$(mktemp)
    trap 'rm -f "$feed_config"' EXIT
    printf '%s\n' \
        "src-git mosdns https://github.com/sbwml/luci-app-mosdns.git;v5" \
        "src-git passwall_packages https://github.com/Openwrt-Passwall/openwrt-passwall-packages.git;main" \
        "src-git passwall_luci https://github.com/Openwrt-Passwall/openwrt-passwall.git;main" \
        "src-git openclash https://github.com/vernesong/OpenClash.git;master" \
        "src-git qmodem https://github.com/FUjr/QModem.git^${QMODEM_COMMIT}" |
        awk 'NR == FNR { managed[$2] = 1; print; next }
             $1 ~ /^src-/ && ($2 in managed) { next }
             { print }' - "${FEEDS_FILE}" > "${feed_config}"
    cat "${feed_config}" > "${FEEDS_FILE}"

    # v2ray-geodata 的 Makefile 在仓库根目录，按 MosDNS 上游说明放进 package/。
    geodata_dir="package/wh3000pro/v2ray-geodata"
    if [ ! -f "${geodata_dir}/Makefile" ]; then
        mkdir -p "$(dirname "${geodata_dir}")"
        git clone --depth=1 --branch master https://github.com/sbwml/v2ray-geodata.git "${geodata_dir}"
    fi

    if [ -n "${GITHUB_ENV:-}" ]; then
        printf 'WH3000_QMODEM_COMMIT=%s\n' "${QMODEM_COMMIT}" >> "${GITHUB_ENV}"
    fi
else
    ensure_feed "qmodem" "src-git qmodem https://github.com/FUjr/QModem.git;main"
fi

ensure_feed "fancontrol" "src-git fancontrol https://github.com/JiaY-shi/fancontrol.git"

echo "[diy-part1] 最终 ${FEEDS_FILE} 内容："
cat "${FEEDS_FILE}"

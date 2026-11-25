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

# 1. 注入 FUjr/QModem（5G/4G 蜂窝模组管理与拨号套件）
ensure_feed "qmodem" "src-git qmodem https://github.com/FUjr/QModem.git;main"

# 2. 注入 JiaY-shi/fancontrol（PWM 风扇温控守护与 LuCI 界面）
ensure_feed "fancontrol" "src-git fancontrol https://github.com/JiaY-shi/fancontrol.git"

# ------------------------------------------------------------------------------
# 可选：后续如需引入其他第三方源，可取消注释并按需添加，例如：
# ensure_feed "openclash" "src-git openclash https://github.com/vernesong/OpenClash.git;master"
# ------------------------------------------------------------------------------

echo "[diy-part1] 最终 ${FEEDS_FILE} 内容："
cat "${FEEDS_FILE}"

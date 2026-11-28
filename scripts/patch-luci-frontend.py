#!/usr/bin/env python3
"""
为 OpenWrt/LEDE LuCI 前端应用两项幂等加固补丁：
1. cbi.js：通过 Object.defineProperty(window, '_', { get, set }) 保护全局翻译函数 _，
   彻底免疫浏览器扩展（如注入 Lodash 4.x 的插件）覆盖 window._ 导致菜单变英文与
   TypeError: _(...).format is not a function。
2. controller/admin/index.uc + 主题 header.ut：为 /cgi-bin/luci/admin/translations/<lang>
   增加基于 i18n/*.lmo 文件指纹的 /tmp 原子缓存、ETag/304 与浏览器 Cache-Control 缓存，
   将切页翻译脚本耗时从 ~1.6s 降至毫秒级（浏览器命中 0ms）。
"""

import argparse
import glob
import json
import os
import re
import sys


CBI_MARKER = "__luci_tr"
TR_CACHE_MARKER = "luci-tr-"
ARGON_COMPAT_MARKER = "/* wh3000pro-argon-compat-v4 */"
ARGON_COMPAT_OLD_RE = re.compile(r"\n?/\* wh3000pro-argon-compat-v\d+ \*/.*\Z", re.S)

ARGON_COMPAT_CSS = """
/* wh3000pro-argon-compat-v4 */
/* 1. 修复空表格（含带 footer 的 Dockerman 列表）占位行绝对定位盖住页脚或产生白条裁切 */
.table .tr.placeholder:has(> .td[colspan]) {
  height: auto;
}
.table .tr.placeholder > .td[colspan] {
  position: static;
  width: auto;
  line-height: 1.8;
  padding: 1.25rem 1rem !important;
  text-align: center !important;
  background: var(--row-color);
  color: var(--muted-text);
}
.table:has(.tr.cbi-section-table-footer) .tr.cbi-section-table-footer > .td {
  line-height: 1.5;
  padding: 0.7rem 1rem;
  vertical-align: middle;
}

/* 2. 补齐 Docker 升为一级菜单（admin/docker）后的容器操作列换行适配 */
[data-page="admin-docker-containers"] .td:last-child:has(> div > .cbi-button + .cbi-button) {
  width: 16rem;
  min-width: 16rem;
  white-space: normal;
  text-align: end;
}
[data-page="admin-docker-containers"] .td:last-child:has(> div > .cbi-button + .cbi-button) > div {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  max-width: 16rem;
  margin-inline-start: auto;
  gap: var(--control-gap);
}
[data-page="admin-docker-containers"] .td:last-child:has(> div > .cbi-button + .cbi-button) > div > * {
  flex: 0 0 auto;
}
@media screen and (max-width: 600px) {
  [data-page="admin-docker-containers"] .td:last-child:has(> div > .cbi-button + .cbi-button) {
    flex: 1 1 100%;
    width: 100%;
    min-width: 0;
    max-width: 100%;
  }
  [data-page="admin-docker-containers"] .td:last-child:has(> div > .cbi-button + .cbi-button) > div {
    max-width: 100%;
  }
}

/* 3. 补齐 LEDE 路径下 TTYD（admin/system/ttyd）终端全屏高度适配 */
[data-page="admin-system-ttyd"] #maincontent > .container,
[data-page="admin-system-ttyd-ttyd"] #maincontent > .container {
  display: flex;
  flex-direction: column;
}
[data-page="admin-system-ttyd"] #view,
[data-page="admin-system-ttyd-ttyd"] #view {
  flex: 1;
}
[data-page="admin-system-ttyd"] #view iframe,
[data-page="admin-system-ttyd-ttyd"] #view iframe {
  height: 100%;
  min-height: calc(100vh - 11rem);
}

/* 4. 补齐 WeChatPush 日志页与在线设备页卡片内边距及暗色边框适配 */
[data-page="admin-services-wechatpush-log"] .cbi-section {
  padding: var(--field-gap) var(--section-inset);
}
[data-page="admin-services-wechatpush-log"] #log_textarea pre {
  border-color: var(--border-color);
  background: var(--surface-inset);
  color: var(--log-text);
}
[data-page="admin-services-wechatpush-log"] .cbi-section small {
  color: var(--muted-text);
}
[data-page="admin-services-wechatpush-client"] table {
  background: var(--surface-color);
  border-radius: var(--radius-card);
  box-shadow: var(--section-shadow);
  overflow: hidden;
}
[data-page="admin-services-wechatpush-client"] th,
[data-page="admin-services-wechatpush-client"] td {
  border-color: var(--border-color) !important;
}
[data-page="admin-services-wechatpush-client"] tr:nth-child(even) {
  background: var(--row-alt) !important;
}
[data-page="admin-services-wechatpush-client"] a {
  color: var(--link-color) !important;
}

/* 5. 补齐 Argon v3 全局非 Tab 表单卡片 (.cbi-section > .cbi-section-node) 上下内边距，解决末行控件/按钮贴底 */
.cbi-section > .cbi-section-node:not(.cbi-section-node-tabbed):where(:has(> .cbi-value, > [id] > .cbi-value)) {
  padding-block: var(--field-gap);
}
.cbi-section > :is(h3, h4, .cbi-section-descr:not(:empty)) ~ .cbi-section-node:not(.cbi-section-node-tabbed):where(:has(> .cbi-value, > [id] > .cbi-value)) {
  padding-block-start: 0;
}

/* 6. 优化 Docker 概述页 README 链接排版、启停按钮卡片内边距与总览统计卡片主题适配 */
[data-page="admin-docker-overview"] .cbi-map-descr > br,
[data-page="admin-services-dockerman-overview"] .cbi-map-descr > br {
  display: none;
}
[data-page="admin-docker-overview"] .cbi-map-descr > a,
[data-page="admin-services-dockerman-overview"] .cbi-map-descr > a {
  display: inline-block;
  margin-inline-start: 0.5rem;
  font-weight: 500;
  white-space: nowrap;
}
[data-page="admin-docker-overview"] .cbi-section:has(> div > button.btn),
[data-page="admin-services-dockerman-overview"] .cbi-section:has(> div > button.btn) {
  padding: var(--field-gap) var(--section-inset);
}
[data-page="admin-docker-overview"] .cbi-section:has(> div > button.btn) > div,
[data-page="admin-services-dockerman-overview"] .cbi-section:has(> div > button.btn) > div {
  margin-bottom: 0 !important;
  gap: var(--control-gap) !important;
  align-items: center;
}
[data-page="admin-docker-overview"] #view .cbi-map > div[style*="grid"] > a > div,
[data-page="admin-services-dockerman-overview"] #view .cbi-map > div[style*="grid"] > a > div {
  background: var(--surface-color);
  border-color: var(--border-color) !important;
  border-radius: var(--radius-card) !important;
  box-shadow: var(--section-shadow);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
[data-page="admin-docker-overview"] #view .cbi-map > div[style*="grid"] > a:hover > div,
[data-page="admin-services-dockerman-overview"] #view .cbi-map > div[style*="grid"] > a:hover > div {
  transform: translateY(-2px);
}
[data-page="admin-docker-overview"] #view .cbi-map > div[style*="grid"] > a div[style*="color: #333"],
[data-page="admin-services-dockerman-overview"] #view .cbi-map > div[style*="grid"] > a div[style*="color: #333"] {
  color: var(--text-strong) !important;
}
[data-page="admin-docker-overview"] #view .cbi-map > div[style*="grid"] > a span[style*="color: #666"],
[data-page="admin-services-dockerman-overview"] #view .cbi-map > div[style*="grid"] > a span[style*="color: #666"] {
  color: var(--muted-text) !important;
}

/* 7. 防止 Argon 的 :empty { display: none } 隐藏表格说明行空单元格，避免后续说明整体左移错位 */
.cbi-section-table-descr > th:empty,
.cbi-section-table-descr > td:empty,
.cbi-section-table-descr > .th:empty,
.cbi-section-table-descr > .td:empty {
  display: table-cell !important;
}
"""


def find_matching_brace(text: str, open_idx: int) -> int:
    """从 open_idx ('{') 起解析配对的 '}'，正确跳过单/双引号字符串与注释。"""
    n = len(text)
    depth = 0
    i = open_idx
    in_str = None
    in_line_comment = False
    in_block_comment = False

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def patch_cbi_js(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    if CBI_MARKER in src:
        return "already_patched"

    # 匹配顶层或压缩后的 function _(s, c) { ... }
    m = re.search(r"(?<![A-Za-z0-9_$])function\s+_\s*\(([^)]*)\)\s*\{", src)
    if not m:
        raise RuntimeError(f"未在 {path} 中找到 function _(...) 定义")

    brace_start = m.end() - 1
    brace_end = find_matching_brace(src, brace_start)
    if brace_end < 0:
        raise RuntimeError(f"无法解析 {path} 中 function _(...) 的函数体")

    params = m.group(1)
    body = src[brace_start : brace_end + 1]

    # 使用内部函数 __luci_tr + 只读 getter / 静默空 setter 保护 window._：
    # - 避免顶层 function _() 的 configurable:false 阻止 defineProperty；
    # - 无论外部扩展在 cbi.js 之前还是之后赋值 window._ = lodash，均无法覆盖 LuCI 翻译函数，
    #   且严格模式下空 setter 静默吞掉赋值不会让扩展抛异常。
    guard = (
        f"function {CBI_MARKER}({params}){body}"
        f"(function(){{var g=typeof window!=='undefined'?window:(typeof globalThis!=='undefined'?globalThis:null);"
        f"if(g){{try{{Object.defineProperty(g,'_',{{get:function(){{return {CBI_MARKER};}},"
        f"set:function(){{}},configurable:false,enumerable:true}});}}catch(e){{g._={CBI_MARKER};}}}}}})();"
    )

    patched = src[: m.start()] + guard + src[brace_end + 1 :]
    with open(path, "w", encoding="utf-8") as f:
        f.write(patched)
    return "patched"


NEW_ACTION_TRANSLATIONS = """\taction_translations: function(reqlang) {
\t\tconst lang = reqlang ?? dispatcher.lang ?? 'en';
\t\tconst safe_lang = match(lang, /^[A-Za-z0-9_-]+$/) ? lang : null;

\t\tif (!safe_lang) {
\t\t\tif (reqlang != null && reqlang != dispatcher.lang) {
\t\t\t\tload_catalog(reqlang, '/usr/lib/lua/luci/i18n');
\t\t\t\tchange_catalog(reqlang);
\t\t\t}

\t\t\thttp.prepare_content('application/javascript; charset=UTF-8');
\t\t\thttp.write('window.TR={');
\t\t\tget_translations((key, val) => http.write(sprintf('"%08x":%J,', key, val)));
\t\t\thttp.write('};');
\t\t\treturn;
\t\t}

\t\tconst i18n_dir = '/usr/lib/lua/luci/i18n';
\t\tconst suffix = `.${safe_lang}.lmo`;
\t\tlet count = 0, total_size = 0, max_mtime = 0;

\t\tfor (let name in (lsdir(i18n_dir) ?? [])) {
\t\t\tif (substr(name, -length(suffix)) == suffix) {
\t\t\t\tconst st = stat(`${i18n_dir}/${name}`);
\t\t\t\tif (st) {
\t\t\t\t\tcount++;
\t\t\t\t\ttotal_size += st.size;
\t\t\t\t\tif (st.mtime > max_mtime)
\t\t\t\t\t\tmax_mtime = st.mtime;
\t\t\t\t}
\t\t\t}
\t\t}

\t\tconst stamp = `${safe_lang}-${count}-${total_size}-${max_mtime}`;
\t\tconst etag = `"${stamp}"`;

\t\thttp.header('Cache-Control', 'public, max-age=86400');
\t\thttp.header('ETag', etag);

\t\tif (http.getenv('HTTP_IF_NONE_MATCH') == etag) {
\t\t\thttp.status(304, 'Not Modified');
\t\t\thttp.close();
\t\t\treturn;
\t\t}

\t\tconst cache_name = `luci-tr-${stamp}.js`;
\t\tconst cache_path = `/tmp/${cache_name}`;
\t\tlet body = readfile(cache_path);

\t\tif (body == null) {
\t\t\tif (reqlang != null && reqlang != dispatcher.lang) {
\t\t\t\tload_catalog(reqlang, i18n_dir);
\t\t\t\tchange_catalog(reqlang);
\t\t\t}

\t\t\tconst parts = [ 'window.TR={' ];
\t\t\tget_translations((key, val) => push(parts, sprintf('"%08x":%J,', key, val)));
\t\t\tpush(parts, '};');
\t\t\tbody = join('', parts);

\t\t\tconst prefix = `luci-tr-${safe_lang}-`;
\t\t\tfor (let entry in (lsdir('/tmp') ?? [])) {
\t\t\t\tif (index(entry, prefix) == 0 && entry != cache_name)
\t\t\t\t\tunlink(`/tmp/${entry}`);
\t\t\t}

\t\t\tconst tmp_path = `${cache_path}.${time()}.${length(body)}.tmp`;
\t\t\tif (writefile(tmp_path, body) != null) {
\t\t\t\tif (!rename(tmp_path, cache_path))
\t\t\t\t\tunlink(tmp_path);
\t\t\t}
\t\t}

\t\thttp.prepare_content('application/javascript; charset=UTF-8');
\t\thttp.write(body);
\t}"""


def patch_index_uc(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    if TR_CACHE_MARKER in src:
        return "already_patched"

    # 确保导入 fs 辅助函数
    fs_import = "import { lsdir, stat, readfile, writefile, rename, unlink } from 'fs';\n"
    if "from 'fs';" not in src:
        m_imp = re.search(r"import\s+\{[^}]*\}\s+from\s+'luci\.core';\s*\n", src)
        if not m_imp:
            raise RuntimeError(f"未在 {path} 中找到 luci.core import 语句")
        src = src[: m_imp.end()] + fs_import + src[m_imp.end() :]

    m_act = re.search(r"\taction_translations:\s*function\s*\([^)]*\)\s*\{", src)
    if not m_act:
        raise RuntimeError(f"未在 {path} 中找到 action_translations 定义")

    brace_start = m_act.end() - 1
    brace_end = find_matching_brace(src, brace_start)
    if brace_end < 0:
        raise RuntimeError(f"无法解析 {path} 中 action_translations 函数体")

    patched = src[: m_act.start()] + NEW_ACTION_TRANSLATIONS + src[brace_end + 1 :]
    with open(path, "w", encoding="utf-8") as f:
        f.write(patched)
    return "patched"


def patch_header_ut(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    changed = False

    # 1. 为 translations/<lang> 追加版本号查询参数，刷固件升级后强制刷新浏览器缓存
    old_tag = "<script src=\"{{ dispatcher.build_url('admin/translations', dispatcher.lang) }}\"></script>"
    if old_tag in src:
        if "theme_rev" in src:
            new_tag = "<script src=\"{{ dispatcher.build_url('admin/translations', dispatcher.lang) }}?v={{ theme_rev }}\"></script>"
        else:
            new_tag = "<script src=\"{{ dispatcher.build_url('admin/translations', dispatcher.lang) }}?v={{ version?.luciversion ?? 'dev' }}\"></script>"
        src = src.replace(old_tag, new_tag, 1)
        changed = True

    # 2. 为 cbi.js 资源链接追加防劫持版本后缀，确保浏览器立即拉取新版 cbi.js 无需手动清缓存
    if "-trguard1" not in src:
        new_src, n_sub = re.subn(
            r'(<script\s+src="\{\{\s*resource\s*\}\}/cbi\.js\?v=[^"]+)(")',
            r"\1-trguard1\2",
            src,
            count=1,
        )
        if n_sub > 0:
            src = new_src
            changed = True

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        return "patched"
    if "admin/translations', dispatcher.lang) }}?v=" in src or "-trguard1" in src:
        return "already_patched"
    return "skipped"


def patch_dockerman_menu(menu_path: str, common_js_path: str) -> str:
    """将新版 luci-app-dockerman 从「服务 -> Dockerman JS」提升为顶层一级菜单「Docker」（匹配 Argon docker.svg 图标）。"""
    menu_changed = False
    with open(menu_path, "r", encoding="utf-8") as f:
        menu = json.load(f)

    new_menu = {}
    for k, v in menu.items():
        nk = k.replace("admin/services/dockerman", "admin/docker") if k.startswith("admin/services/dockerman") else k
        if nk != k:
            menu_changed = True
        if isinstance(v, dict):
            v = dict(v)
            action = v.get("action")
            if isinstance(action, dict) and isinstance(action.get("path"), str) and action["path"].startswith("admin/services/dockerman"):
                action = dict(action)
                action["path"] = action["path"].replace("admin/services/dockerman", "admin/docker", 1)
                v["action"] = action
                menu_changed = True
            if nk == "admin/docker":
                if v.get("title") != "Docker":
                    v["title"] = "Docker"
                    menu_changed = True
                if v.get("order") != 28:
                    v["order"] = 28
                    menu_changed = True
        new_menu[nk] = v

    if menu_changed:
        with open(menu_path, "w", encoding="utf-8") as f:
            json.dump(new_menu, f, indent="\t", ensure_ascii=False)
            f.write("\n")

    js_changed = False
    if common_js_path and os.path.isfile(common_js_path):
        with open(common_js_path, "r", encoding="utf-8") as f:
            js = f.read()
        if "admin/services/dockerman" in js:
            js = js.replace("admin/services/dockerman", "admin/docker")
            with open(common_js_path, "w", encoding="utf-8") as f:
                f.write(js)
            js_changed = True

    return "patched" if (menu_changed or js_changed) else "already_patched"


def patch_dockerman_views(views_dir: str) -> str:
    """清理新版 Dockerman 带文字大按钮上的花哨 Emoji（如「创建 🪄➕」「截断 ✂️」），保留纯图标行内小按钮。"""
    if not views_dir or not os.path.isdir(views_dir):
        return "skipped"

    # 1) 仅移除已经带完整 .i18n 文字标签后紧跟的 .e Emoji，不碰单独使用 .e 的纯图标小按钮
    # 2) 将中文下容易引起误解的 Prune 译文「截断」替换为「清理未使用」（英文界面保持 Prune）
    patterns = [
        (
            re.compile(r"(\$\{dm2\.ActionTypes\[['\"][^'\"]+['\"]\]\.i18n\})\s+\$\{dm2\.ActionTypes\[['\"][^'\"]+['\"]\]\.e\}"),
            r"\1",
        ),
        (
            re.compile(r"(\$\{dm2\.Types\[['\"][^'\"]+['\"]\]\.sub\[['\"][^'\"]+['\"]\]\.i18n\})\s+\$\{dm2\.Types\[['\"][^'\"]+['\"]\]\.sub\[['\"][^'\"]+['\"]\]\.e\}"),
            r"\1",
        ),
        (
            re.compile(r"(_\(['\"]Labels['\"]\))\s*\+\s*['\"]\s*🏷️?['\"]"),
            r"\1",
        ),
        (
            re.compile(r"prune\.inputtitle\s*=\s*`\$\{dm2\.ActionTypes\[['\"]prune['\"]\]\.i18n\}`"),
            "prune.inputtitle=(dm2.ActionTypes['prune'].i18n==='截断'?'清理未使用':dm2.ActionTypes['prune'].i18n)",
        ),
    ]

    changed_files = 0
    for name in sorted(os.listdir(views_dir)):
        if not name.endswith(".js"):
            continue
        p = os.path.join(views_dir, name)
        if not os.path.isfile(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            src = f.read()
        new_src = src
        for pat, repl in patterns:
            new_src = pat.sub(repl, new_src)
        if new_src != src:
            with open(p, "w", encoding="utf-8") as f:
                f.write(new_src)
            changed_files += 1

    return f"patched({changed_files})" if changed_files > 0 else "already_patched"


def patch_form_js(path: str) -> str:
    """为 TableSection 空表占位单元格补充 colspan='99'，配合 CSS 彻底脱离绝对定位叠层。"""
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    if "colspan" in src and re.search(r"placeholder['\"][^;]*colspan", src):
        return "already_patched"

    pat = re.compile(
        r"(E\(\s*['\"]tr['\"]\s*,\s*\{\s*['\"]class['\"]\s*:\s*['\"]tr cbi-section-table-row placeholder['\"]\s*\}\s*,\s*E\(\s*['\"]td['\"]\s*,\s*\{\s*['\"]class['\"]\s*:\s*['\"]td['\"])(\s*\}\s*,\s*this\.renderSectionPlaceholder\(\)\s*\)\s*\))"
    )
    new_src, n = pat.subn(r"\1,'colspan':'99'\2", src, count=1)
    if n == 0:
        return "skipped"

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_src)
    return "patched"


def patch_argon_admin_css(css_path: str) -> str:
    """向 Argon v3 admin.css 追加（或升级）幂等兼容修正。"""
    with open(css_path, "r", encoding="utf-8") as f:
        src = f.read()

    if ARGON_COMPAT_MARKER in src:
        return "already_patched"

    cleaned = ARGON_COMPAT_OLD_RE.sub("", src).rstrip()
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(cleaned + "\n" + ARGON_COMPAT_CSS.lstrip())
    return "patched"


def main() -> int:
    parser = argparse.ArgumentParser(description="应用 LuCI 前端防劫持、翻译缓存与主题兼容补丁")
    parser.add_argument("--source-root", help="OpenWrt/LEDE 编译源码根目录")
    parser.add_argument("--cbi-js", help="指定单个 cbi.js 文件路径")
    parser.add_argument("--form-js", help="指定单个 form.js 文件路径")
    parser.add_argument("--index-uc", help="指定单个 controller/admin/index.uc 文件路径")
    parser.add_argument("--header-ut", action="append", default=[], help="指定单个或多个 header.ut 文件路径")
    parser.add_argument("--argon-css", action="append", default=[], help="指定单个或多个 Argon admin.css 文件路径")
    parser.add_argument("--dockerman-views", action="append", default=[], help="指定 Dockerman view JS 目录路径")
    args = parser.parse_args()

    cbi_targets = []
    form_targets = []
    index_targets = []
    header_targets = list(args.header_ut)
    argon_css_targets = list(args.argon_css)
    dockerman_view_dirs = list(args.dockerman_views)

    if args.cbi_js:
        cbi_targets.append(args.cbi_js)
    if args.form_js:
        form_targets.append(args.form_js)
    if args.index_uc:
        index_targets.append(args.index_uc)

    if args.source_root:
        root = args.source_root
        for rel in [
            "feeds/luci/modules/luci-base/htdocs/luci-static/resources/cbi.js",
            "package/feeds/luci/luci-base/htdocs/luci-static/resources/cbi.js",
        ]:
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                cbi_targets.append(os.path.realpath(p))
        for rel in [
            "feeds/luci/modules/luci-base/htdocs/luci-static/resources/form.js",
            "package/feeds/luci/luci-base/htdocs/luci-static/resources/form.js",
        ]:
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                form_targets.append(os.path.realpath(p))
        for rel in [
            "feeds/luci/modules/luci-base/ucode/controller/admin/index.uc",
            "package/feeds/luci/luci-base/ucode/controller/admin/index.uc",
            "feeds/luci/modules/luci-base/root/usr/share/ucode/luci/controller/admin/index.uc",
            "package/feeds/luci/luci-base/root/usr/share/ucode/luci/controller/admin/index.uc",
        ]:
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                index_targets.append(os.path.realpath(p))
        for pattern in [
            "feeds/luci/themes/*/ucode/template/themes/*/header.ut",
            "feeds/luci/themes/*/ucode/template/themes/*/head.ut",
            "package/feeds/luci/*/ucode/template/themes/*/header.ut",
            "package/feeds/luci/*/ucode/template/themes/*/head.ut",
            "package/*/luci-theme-*/ucode/template/themes/*/header.ut",
            "package/*/luci-theme-*/ucode/template/themes/*/head.ut",
        ]:
            for p in sorted(glob.glob(os.path.join(root, pattern))):
                if os.path.isfile(p):
                    header_targets.append(os.path.realpath(p))
        for pattern in [
            "package/*/luci-theme-argon/htdocs/luci-static/argon/css/admin.css",
            "feeds/luci/themes/luci-theme-argon/htdocs/luci-static/argon/css/admin.css",
            "package/feeds/luci/luci-theme-argon/htdocs/luci-static/argon/css/admin.css",
        ]:
            for p in sorted(glob.glob(os.path.join(root, pattern))):
                if os.path.isfile(p):
                    argon_css_targets.append(os.path.realpath(p))

    # 去重
    cbi_targets = list(dict.fromkeys(cbi_targets))
    form_targets = list(dict.fromkeys(form_targets))
    index_targets = list(dict.fromkeys(index_targets))
    header_targets = list(dict.fromkeys(header_targets))
    argon_css_targets = list(dict.fromkeys(argon_css_targets))

    if args.source_root:
        if not cbi_targets:
            raise RuntimeError("在 --source-root 下未找到 cbi.js，请检查 LuCI 源码路径")
        if not index_targets:
            raise RuntimeError("在 --source-root 下未找到 controller/admin/index.uc，请检查 LuCI 源码路径")
        if not header_targets:
            raise RuntimeError("在 --source-root 下未找到任何主题 header.ut / head.ut")

    for p in cbi_targets:
        status = patch_cbi_js(p)
        print(f"[patch-luci-frontend] cbi.js ({status}): {p}")
    for p in form_targets:
        status = patch_form_js(p)
        print(f"[patch-luci-frontend] form.js ({status}): {p}")
    for p in index_targets:
        status = patch_index_uc(p)
        print(f"[patch-luci-frontend] index.uc ({status}): {p}")
    for p in header_targets:
        status = patch_header_ut(p)
        print(f"[patch-luci-frontend] header.ut ({status}): {p}")
    for p in argon_css_targets:
        status = patch_argon_admin_css(p)
        print(f"[patch-luci-frontend] argon admin.css ({status}): {p}")

    # 可选：若存在新版 luci-app-dockerman，提升为顶层一级菜单 Docker 并清理大按钮花哨 Emoji
    if args.source_root:
        root = args.source_root
        dockerman_menus = []
        for rel in [
            "feeds/luci/applications/luci-app-dockerman/root/usr/share/luci/menu.d/luci-app-dockerman.json",
            "package/feeds/luci/luci-app-dockerman/root/usr/share/luci/menu.d/luci-app-dockerman.json",
        ]:
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                dockerman_menus.append(os.path.realpath(p))
        for mp in list(dict.fromkeys(dockerman_menus)):
            app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(mp))))))
            cjs = os.path.join(app_root, "htdocs/luci-static/resources/dockerman/common.js")
            vdir = os.path.join(app_root, "htdocs/luci-static/resources/view/dockerman")
            status = patch_dockerman_menu(mp, cjs)
            print(f"[patch-luci-frontend] dockerman menu ({status}): {mp}")
            if os.path.isdir(vdir):
                dockerman_view_dirs.append(os.path.realpath(vdir))

    for vdir in list(dict.fromkeys(dockerman_view_dirs)):
        status = patch_dockerman_views(vdir)
        print(f"[patch-luci-frontend] dockerman views ({status}): {vdir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

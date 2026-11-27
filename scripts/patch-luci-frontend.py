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
import os
import re
import sys


CBI_MARKER = "__luci_tr"
TR_CACHE_MARKER = "luci-tr-"


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


def main() -> int:
    parser = argparse.ArgumentParser(description="应用 LuCI 前端防劫持与翻译缓存补丁")
    parser.add_argument("--source-root", help="OpenWrt/LEDE 编译源码根目录")
    parser.add_argument("--cbi-js", help="指定单个 cbi.js 文件路径")
    parser.add_argument("--index-uc", help="指定单个 controller/admin/index.uc 文件路径")
    parser.add_argument("--header-ut", action="append", default=[], help="指定单个或多个 header.ut 文件路径")
    args = parser.parse_args()

    cbi_targets = []
    index_targets = []
    header_targets = list(args.header_ut)

    if args.cbi_js:
        cbi_targets.append(args.cbi_js)
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
            "feeds/luci/modules/luci-base/root/usr/share/ucode/luci/controller/admin/index.uc",
            "package/feeds/luci/luci-base/root/usr/share/ucode/luci/controller/admin/index.uc",
        ]:
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                index_targets.append(os.path.realpath(p))
        for pattern in [
            "feeds/luci/themes/*/ucode/template/themes/*/header.ut",
            "package/feeds/luci/*/ucode/template/themes/*/header.ut",
            "package/*/luci-theme-*/ucode/template/themes/*/header.ut",
        ]:
            for p in sorted(glob.glob(os.path.join(root, pattern))):
                if os.path.isfile(p):
                    header_targets.append(os.path.realpath(p))

    # 去重
    cbi_targets = list(dict.fromkeys(cbi_targets))
    index_targets = list(dict.fromkeys(index_targets))
    header_targets = list(dict.fromkeys(header_targets))

    for p in cbi_targets:
        status = patch_cbi_js(p)
        print(f"[patch-luci-frontend] cbi.js ({status}): {p}")
    for p in index_targets:
        status = patch_index_uc(p)
        print(f"[patch-luci-frontend] index.uc ({status}): {p}")
    for p in header_targets:
        status = patch_header_ut(p)
        print(f"[patch-luci-frontend] header.ut ({status}): {p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

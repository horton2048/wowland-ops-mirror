#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wowland-ops-mirror 同步脚本
从飞书知识库镜像指定 wiki 节点(及其子文档)到本地目录, 供 git push 到 GitHub。

特性:
- 文档正文转 Markdown
- 内嵌图片下载到 _assets/ 并替换为本地相对引用
- synced_reference(跨文档引用块) 解析为实际内容并内联
- 变更检测(基于 obj_edit_time 与内容比对), 生成 README 索引与 manifest

用法: python3 sync_wowland.py [--repo 镜像仓库根目录] [--json 输出机器可读结果]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

# ---------------- 文档清单: wiki 节点 -> (相对目录, 标题/文件名) ----------------
# 相对目录以 docs/ 为根; 试营业执行手册沿用远程仓库已有文件名, 保持 raw 链接兼容
DOCS = [
    # 主节点 1
    ("DpzZwwMFTiAqBOkBRUAcFiKAnbc", "docs", "月亮湖WowLand社群招新方案（总）"),
    # 主节点 1 的子文档
    ("AFfmwbJbjiJhIqksDWccGyUVncf", "docs/月亮湖WowLand社群招新方案（总）", "个人经历宣讲"),
    ("OhqbwJzSiiWzbJkTTQ1cOmsCnYe", "docs/月亮湖WowLand社群招新方案（总）", "【北京工业大学WowLand】（建筑工程学院就业专场） 宣讲会方案"),
    ("TTLMwBia1ibUOdk3vf4cKOaYnNh", "docs/月亮湖WowLand社群招新方案（总）", "校园墙线上推广方案"),
    ("HjSuwUssYiuXqbk7lMTc7ubFnqh", "docs/月亮湖WowLand社群招新方案（总）", "校园墙招新方案"),
    ("Du7awSO35iGwgWkzN8Nc1fihnfb", "docs/月亮湖WowLand社群招新方案（总）", "个人自媒体招新方案"),
    ("KgT5wStHHi5Mvek9az2coqNCnYb", "docs/月亮湖WowLand社群招新方案（总）", "月亮湖WowLand-集中招新方案"),
    # 主节点 2 (文件名沿用远程仓库已有命名)
    ("JdscwcN7ji2kCHke3V5chJJWnbe", "docs", "试营业执行手册"),
]

WIKI_URL = "https://larkcommunity.feishu.cn/wiki/{token}"
IMG_TAG_RE = re.compile(r"<img\b[^>]*?>", re.S)
SYNCED_REF_RE = re.compile(r"<synced_reference\b[^>]*?>(?:</synced_reference>)?", re.S)

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"cmd failed: {cmd}\n{r.stderr[:2000]}")
    return r.stdout

def fetch_doc_markdown(doc_url):
    out = run(f"lark-cli docs +fetch --doc '{doc_url}' --doc-format markdown --as user --format json")
    data = json.loads(out)
    if not data.get("ok"):
        raise RuntimeError(f"fetch failed: {data}")
    return data["data"]["document"].get("content", "")

def fetch_block_markdown(doc_token, block_id, depth):
    """抓取指定文档中某 block 的内容(markdown), depth 限制递归"""
    out = run(f"lark-cli docs +fetch --doc '{doc_token}' --doc-format markdown --scope range --start-block-id '{block_id}' --as user --format json")
    data = json.loads(out)
    if not data.get("ok"):
        return None
    content = data["data"]["document"].get("content", "")
    # 去掉 fragment / synced-source 包裹与 title
    content = re.sub(r"^<title>.*?</title>\s*", "", content, flags=re.S)
    content = re.sub(r"^<fragment[^>]*>|</fragment>$", "", content, flags=re.S)
    content = re.sub(r"^<synced-source[^>]*>|</synced-source>$", "", content, flags=re.S)
    if depth < 2:
        content = resolve_synced_refs(content, depth + 1)
    return content.strip()

def resolve_synced_refs(content, depth=0):
    """把 synced_reference 替换为其引用的源 block 内容"""
    def repl(m):
        tag = m.group(0)
        src_token = re.search(r'src-token="([^"]+)"', tag)
        src_block = re.search(r'src-block-id="([^"]+)"', tag)
        if not (src_token and src_block):
            return tag
        block_content = fetch_block_markdown(src_token.group(1), src_block.group(1), depth)
        if block_content is None:
            return tag
        return ("\n\n> 📎 以下为引用自[关联文档](https://larkcommunity.feishu.cn/docx/%s)的内容:\n\n%s\n\n> 📎 引用结束\n"
                % (src_token.group(1), block_content))
    return SYNCED_REF_RE.sub(repl, content)

def download_images(content, repo_root):
    """下载文档内嵌图片到 repo_root/_assets, 返回 (处理后的content, 下载的图片列表)"""
    assets_dir = os.path.join(repo_root, "_assets")
    os.makedirs(assets_dir, exist_ok=True)
    downloaded = []

    def repl(m):
        tag = m.group(0)
        src_m = re.search(r'src="([^"]+)"', tag)
        if not src_m:
            return tag
        token = src_m.group(1)
        alt_m = re.search(r'alt="([^"]*)"', tag)
        alt = alt_m.group(1) if alt_m else "image"
        # 已有映射文件则跳过下载
        existing = [f for f in os.listdir(assets_dir) if f.startswith(token + ".")]
        if existing:
            fname = existing[0]
        else:
            fname = None
            for attempt in range(3):
                try:
                    run(f"lark-cli docs +media-download --token '{token}' --output '{os.path.join(assets_dir, token)}'")
                    candidates = [f for f in os.listdir(assets_dir) if f.startswith(token + ".")]
                    if candidates:
                        fname = candidates[0]
                        break
                except Exception as e:
                    print(f"  [retry {attempt+1}/3] 图片 {token}: {str(e)[:120]}", file=sys.stderr)
                time.sleep(2 * (attempt + 1))
            if not fname:
                print(f"  [warn] 图片下载失败, 保留原标签: {token}", file=sys.stderr)
                return tag
            downloaded.append(fname)
        return f"![{alt}](_assets/{fname})"

    content = IMG_TAG_RE.sub(repl, content)
    return content, downloaded

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    repo = args.repo

    manifest_path = os.path.join(repo, ".sync_manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

    changed = []
    new_images = []
    result = {"ok": True, "docs": [], "changed": []}

    for node_token, subdir, title in DOCS:
        url = WIKI_URL.format(token=node_token)
        try:
            content = fetch_doc_markdown(url)
            content = re.sub(r"^<title>.*?</title>\s*", "", content, flags=re.S)
            content = resolve_synced_refs(content)
            content, imgs = download_images(content, repo)
            new_images.extend(imgs)
            # 清理 synced-source 包裹标签(保留内部内容)
            content = re.sub(r"</?synced-source[^>]*>", "", content)

            nout = run(f"lark-cli wiki +node-get --node-token '{url}' --as user --format json")
            node = json.loads(nout)["data"]
        except Exception as e:
            result["ok"] = False
            result["docs"].append({"title": title, "error": str(e)})
            print(f"[ERROR] {title}: {e}", file=sys.stderr)
            continue

        rel_dir = os.path.join(subdir) if subdir else ""
        rel_path = os.path.join(rel_dir, f"{title}.md")
        abs_path = os.path.join(repo, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        edit_ts = node.get("obj_edit_time")
        header = (
            "> 来源: [飞书知识库]({url})\n"
            "> 节点: `{token}` | 文档类型: `{obj_type}` | 最近编辑(unix): `{edit}`\n"
            "\n"
        ).format(url=url, token=node_token,
                  obj_type=node.get("obj_type"), edit=edit_ts or "")

        new_body = header + content.rstrip() + "\n"

        changed_flag = False
        if os.path.exists(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                old_body = f.read()
            if old_body != new_body:
                changed_flag = True
        else:
            changed_flag = True

        if changed_flag:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_body)
            changed.append(rel_path)

        prev = manifest.get(rel_path, {})
        manifest[rel_path] = {
            "node_token": node_token,
            "title": title,
            "obj_token": node.get("obj_token"),
            "obj_edit_time": edit_ts or prev.get("obj_edit_time"),
            "synced_at": int(time.time()),
        }
        result["docs"].append({"title": title, "path": rel_path,
                               "edit_time": edit_ts, "changed": changed_flag})

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # README 索引
    readme_lines = [
        "# WowLand Ops Mirror",
        "",
        "> 飞书知识库 → GitHub 自动镜像仓库。飞书为权威编辑源, 本仓库为**公开只读镜像**, 供 Grok Bot / 运营助手拉取最新口径。",
        "> 内容由定时任务自动同步, 请勿手动编辑(会被覆盖)。",
        "",
        "## 官方飞书索引(权威)",
        "",
        "1. WowLand社群｜试营业执行手册 Copy — https://larkcommunity.feishu.cn/wiki/JdscwcN7ji2kCHke3V5chJJWnbe",
        "2. 月亮湖WowLand社群招新方案（总） — https://larkcommunity.feishu.cn/wiki/DpzZwwMFTiAqBOkBRUAcFiKAnbc",
        "",
        "## 文档索引",
        "",
    ]
    for node_token, subdir, title in DOCS:
        rel_dir = os.path.join(subdir) if subdir else ""
        rel_path = os.path.join(rel_dir, f"{title}.md").replace(os.sep, "/")
        info = manifest.get(rel_path, {})
        edit = info.get("obj_edit_time") or ""
        line = f"- [{title}]({rel_path})"
        if edit:
            line += f" (最近编辑: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(edit)))})"
        readme_lines.append(line)
    readme_lines += [
        "",
        "## 机器人读取入口",
        "",
        "- 试营业手册 raw: `https://raw.githubusercontent.com/horton2048/wowland-ops-mirror/main/docs/试营业执行手册.md`",
        "- 招新方案 raw: `https://raw.githubusercontent.com/horton2048/wowland-ops-mirror/main/docs/月亮湖WowLand社群招新方案（总）.md`",
        "",
        "## 同步信息",
        "",
        "- 同步范围: 月亮湖WowLand社群招新方案（总）及其全部 6 个子文档; WowLand社群｜试营业执行手册 Copy",
        "- 存档保留: `docs/社长手册.md`(历史手动存档, 不在自动同步范围)",
        f"- 最近同步: {time.strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    with open(os.path.join(repo, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(readme_lines) + "\n")

    result["changed"] = changed
    result["new_images"] = new_images
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if changed:
            print("changed files:")
            for c in changed:
                print("  +", c)
        else:
            print("no changes")
        if new_images:
            print("downloaded images:", len(new_images))

if __name__ == "__main__":
    main()

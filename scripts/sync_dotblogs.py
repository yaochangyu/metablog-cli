#!/usr/bin/env python3
"""
同步 dotblogs 文章到本機目錄（依 postId 判斷本機沒有的新文章才下載）

用法：
  sync_dotblogs.py                 同步到預設目錄 /mnt/d/llm-wiki/wiki/raw/dotblogs
  sync_dotblogs.py --dir <path>    同步到指定目錄
  sync_dotblogs.py --dry-run       只列出將下載的文章，不實際下載

新文章依分類存到 <dir>/<分類>/<標題>.md（無分類則存到 <dir>/未分類/），
與現有備份的資料夾結構一致。

注意：只偵測「本機沒有的新文章」，不會偵測既有文章的內容是否被編輯過。
"""
import argparse
import os
import re
import sys
import xmlrpc.client

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metablog_cli as mb

DEFAULT_SYNC_DIR = "/mnt/d/llm-wiki/wiki/raw/dotblogs"

# 只抓 postId 這一行，不做完整 YAML 解析：
# 部分舊備份檔的 abstract 欄位含未跳脫的 HTML 引號，會讓 yaml.safe_load 整份炸掉。
_POST_ID_RE = re.compile(r"^postId:\s*(.+?)\s*$", re.MULTILINE)


def scan_local_post_ids(base_dir: str) -> set[str]:
    ids = set()
    if not os.path.isdir(base_dir):
        return ids
    for root, _, files in os.walk(base_dir):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            try:
                with open(os.path.join(root, fn), encoding="utf-8") as f:
                    head = f.read(4096)
            except OSError:
                continue
            m = _POST_ID_RE.search(head)
            if m:
                pid = m.group(1).strip().strip("'\"")
                if pid:
                    ids.add(pid)
    return ids


def download_to_category(proxy, post_id: str, username: str, password: str, base_dir: str) -> str:
    post = proxy.metaWeblog.getPost(post_id, username, password)
    categories = post.get("categories") or []
    folder = categories[0] if categories else "未分類"
    return mb.download_post(proxy, post_id, username, password, os.path.join(base_dir, folder))


def main():
    username = os.environ.get("BLOG_USER")
    password = mb.keyring.get_password(mb.KEYRING_SERVICE, "BLOG_PASSWORD") \
        or os.environ.get("BLOG_PASSWORD")
    if not username or not password:
        print("錯誤：缺少 BLOG_USER / BLOG_PASSWORD，設定方式請參考 metablog_cli.py", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="同步 dotblogs 文章到本機目錄")
    parser.add_argument("--dir", default=DEFAULT_SYNC_DIR, help=f"同步目標目錄（預設 {DEFAULT_SYNC_DIR}）")
    parser.add_argument("--dry-run", action="store_true", help="只列出將下載的文章，不實際下載")
    args = parser.parse_args()

    proxy = xmlrpc.client.ServerProxy(mb.API_URL)
    blogid = proxy.blogger.getUsersBlogs("", username, password)[0]["blogid"]

    print("正在取得遠端文章清單...")
    remote_posts = mb.fetch_posts(proxy, blogid, username, password, size=50, fetch_all=True)

    print(f"正在掃描本機目錄 {args.dir} ...")
    local_ids = scan_local_post_ids(args.dir)

    new_posts = [p for p in remote_posts if p["postid"] not in local_ids]

    print(f"遠端共 {len(remote_posts)} 篇，本機已有 {len(local_ids)} 篇，新文章 {len(new_posts)} 篇")

    if not new_posts:
        print("沒有新文章，已是最新。")
        return

    if args.dry_run:
        for p in new_posts:
            print(f"  待下載：{p['postid'][:8]}  {p.get('title', '')}")
        return

    for p in new_posts:
        path = download_to_category(proxy, p["postid"], username, password, args.dir)
        print(f"✅ {p['postid'][:8]} → {path}")

    print(f"\n同步完成，新增 {len(new_posts)} 篇文章。")


if __name__ == "__main__":
    main()

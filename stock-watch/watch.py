"""Costco 上架提醒：用真浏览器打开 Costco 的任天堂分类页，
发现 Switch 2 塞尔达限定机就在仓库里开 issue 通知。"""
import json
import os
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
STATE_FILE = HERE / "state.json"


def matches(name, cfg):
    low = name.lower()
    return (all(w in low for w in cfg["must_include"])
            and any(w in low for w in cfg["any_of"])
            and not any(w in low for w in cfg["exclude"]))


def page_products(page, url):
    """返回页面上所有商品 [(名称, 链接)]。"""
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("a[href*='.product.']", timeout=30000)
    except Exception:
        pass
    page.wait_for_timeout(3000)
    items = page.eval_on_selector_all(
        "a[href*='.product.'], a[href*='/p/-/']",
        "els => els.map(e => [e.innerText.trim(), e.href])",
    )
    seen, out = set(), []
    for name, link in items:
        if name and link not in seen:
            seen.add(link)
            out.append((name, link))
    return out


def notify(title, body):
    """在仓库里开一个 issue。GitHub 会自动给仓库主人发邮件和 App 推送。"""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        print("不在 GitHub Actions 里，只打印：\n" + title + "\n" + body)
        return
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=json.dumps({"title": title, "body": body}).encode(),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        print("已发通知：" + json.loads(resp.read())["html_url"])


def main():
    cfg = json.loads((HERE / "config.json").read_text())
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    notified = set(state.get("notified", []))
    alerts = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="en-US", user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"))
        for url in cfg["pages"]:
            try:
                products = page_products(page, url)
            except Exception as e:
                print(f"{url} 打开失败：{e}")
                continue
            print(f"{url}：找到 {len(products)} 个商品")
            for name, link in products[:5]:
                print(f"  例：{name.splitlines()[0][:80]}")
            for name, link in products:
                if matches(name, cfg) and link not in notified:
                    notified.add(link)
                    alerts.append(f"**{name.splitlines()[0]}**\n{link}")
        browser.close()

    STATE_FILE.write_text(json.dumps({"notified": sorted(notified)}, ensure_ascii=False, indent=2))
    if alerts:
        owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
        notify("Costco 上架了 Switch 2 塞尔达限定机！",
               "\n\n".join(alerts) + f"\n\n快去 Costco 看看 @{owner}")
    else:
        print("还没上架")


if __name__ == "__main__":
    main()

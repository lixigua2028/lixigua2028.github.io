"""Switch 2 塞尔达限定机监控：查新闻 + 查商品页，有新消息就发邮件。"""
import json
import os
import re
import smtplib
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from pathlib import Path

HERE = Path(__file__).parent
STATE_FILE = HERE / "state.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def news_items(cfg, rss_text=None):
    """从 Google News RSS 找疑似塞尔达限定机的新闻，返回 [(id, 标题, 链接)]。"""
    if rss_text is None:
        q = urllib.parse.quote(cfg["news_query"])
        rss_text = fetch(f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")
    found = []
    for item in ET.fromstring(rss_text).iter("item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        t = title.lower()
        if all(w in t for w in cfg["news_must_include"]) and any(w in t for w in cfg["news_any_of"]):
            found.append((link, title, link))
    return found


def stock_status(product, html):
    """返回 'in_stock' / 'out_of_stock' / 'not_listed' / 'unknown'。"""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    low = text.lower()
    idx = low.find(product["match_text"].lower())
    if idx < 0:
        return "not_listed"
    # 只看商品名附近的一段文字，避免误判页面上别的商品
    window = low[max(0, idx - 300): idx + 600]
    if any(w.lower() in window for w in product["out_of_stock_words"]):
        return "out_of_stock"
    if any(w.lower() in window for w in product["in_stock_words"]):
        return "in_stock"
    return "unknown"


def send_email(subject, body):
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    to = os.environ.get("MAIL_TO") or user
    if not (user and password):
        print("未配置邮箱，只打印：\n" + subject + "\n" + body)
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    with smtplib.SMTP_SSL(host, 465, timeout=30) as s:
        s.login(user, password)
        s.send_message(msg)
    print("已发邮件：" + subject)


def main():
    cfg = json.loads((HERE / "config.json").read_text())
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"seen_news": [], "stock": {}}
    alerts = []

    try:
        for nid, title, link in news_items(cfg):
            if nid not in state["seen_news"]:
                state["seen_news"].append(nid)
                alerts.append(f"[新闻] {title}\n{link}")
    except Exception as e:
        print(f"新闻检查失败：{e}", file=sys.stderr)

    for p in cfg["products"]:
        try:
            status = stock_status(p, fetch(p["url"]))
        except Exception as e:
            print(f"{p['name']} 检查失败：{e}", file=sys.stderr)
            continue
        print(f"{p['name']}: {status}")
        old = state["stock"].get(p["url"])
        if status in ("in_stock", "out_of_stock") and status != old and (old or status == "in_stock"):
            label = "有货了！快去买" if status == "in_stock" else "已经卖完"
            alerts.append(f"[{label}] {p['name']}\n{p['url']}")
        if status != "unknown":
            state["stock"][p["url"]] = status

    state["seen_news"] = state["seen_news"][-300:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    if alerts:
        send_email(f"Switch 2 塞尔达限定机：{len(alerts)} 条新消息", "\n\n".join(alerts))
    else:
        print("没有新消息")


if __name__ == "__main__":
    main()

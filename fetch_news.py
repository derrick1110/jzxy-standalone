"""抓取荆州学院官网首页“综合要闻”并写入 campus.db。"""

from __future__ import annotations

import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# 用户给出的 jznu.edu.cn 无法解析；荆州学院现官网域名是 jzun.edu.cn。
BASE_URL = "https://www.jzun.edu.cn"
HOME_URL = f"{BASE_URL}/"
CATEGORY = "综合要闻"
DB_PATH = Path(__file__).resolve().with_name("campus.db")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def fetch_html(url: str) -> str:
    """请求页面，并在每次请求结束后等待 1 秒。"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"
        return response.text
    finally:
        time.sleep(1)


def clean_text(text: str) -> str:
    """压缩多余空白，同时保留段落内的可读文本。"""
    return re.sub(r"\s+", " ", text).strip()


def extract_date(text: str) -> str:
    """从列表或详情页文字中提取 YYYY-MM-DD 格式日期。"""
    match = re.search(r"(20\d{2})[年/.-](\d{1,2})[月/.-](\d{1,2})", text)
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def find_category_section(soup: BeautifulSoup) -> Optional[BeautifulSoup]:
    """在首页定位标题为“综合要闻”的整个新闻板块。"""
    heading = next(
        (
            node
            for node in soup.find_all(["h1", "h2", "h3", "h4"])
            if CATEGORY in clean_text(node.get_text(" ", strip=True))
        ),
        None,
    )
    if not heading:
        return None
    return heading.find_parent("div", class_="news") or heading.parent


def extract_news_list(home_html: str) -> List[Dict[str, str]]:
    """解析首页综合要闻列表。"""
    soup = BeautifulSoup(home_html, "html.parser")
    section = find_category_section(soup)
    if section is None:
        raise RuntimeError("首页未找到“综合要闻”板块")

    # 只抓带发布日期的文字新闻列表，避免混入专题图片轮播。
    items = section.select(".news-item ul.flex li.wl")
    if not items:
        items = section.select("li")

    news: List[Dict[str, str]] = []
    seen_urls = set()
    for item in items:
        link = item.select_one("a[href]")
        if link is None or not link.get("href"):
            continue

        title_node = item.select_one("h1, h2, h3, h4") or link
        title = clean_text(title_node.get_text(" ", strip=True)) or clean_text(
            link.get("title", "")
        )
        if not title:
            continue

        date_text = item.get_text(" ", strip=True)
        publish_date = extract_date(date_text)
        url = urljoin(BASE_URL, link["href"])
        if url in seen_urls:
            continue
        seen_urls.add(url)

        news.append(
            {
                "category": CATEGORY,
                "title": title,
                "publish_date": publish_date,
                "url": url,
            }
        )
    return news


def extract_article(article_html: str) -> Dict[str, str]:
    """从详情页提取完整标题、日期和所有 <p> 标签内的正文。"""
    soup = BeautifulSoup(article_html, "html.parser")

    title_node = soup.select_one("h2.cont-tit2") or soup.find("h1")
    detail_title = clean_text(title_node.get_text(" ", strip=True)) if title_node else ""

    detail_date = ""
    for span in soup.select("span"):
        span_text = clean_text(span.get_text(" ", strip=True))
        if "日期" in span_text:
            detail_date = extract_date(span_text)
            if detail_date:
                break

    content_root = (
        soup.select_one("div.v_news_content")
        or soup.select_one("#vsb_content")
        or soup.select_one("#cont")
    )
    if content_root is None:
        raise RuntimeError("详情页未找到正文区域")

    paragraphs = []
    for paragraph in content_root.find_all("p"):
        text = clean_text(paragraph.get_text(" ", strip=True))
        if text:
            paragraphs.append(text)

    return {
        "title": detail_title,
        "publish_date": detail_date,
        "content": "\n\n".join(paragraphs),
    }


def init_database(db_path: Path = DB_PATH) -> None:
    """创建新闻表。"""
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS public_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                publish_date TEXT NOT NULL,
                content TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE
            )
            """
        )
        connection.commit()


def save_news(news: List[Dict[str, str]], db_path: Path = DB_PATH) -> int:
    """使用 INSERT OR IGNORE 写入新闻，返回实际新增数量。"""
    inserted = 0
    with sqlite3.connect(db_path) as connection:
        for item in news:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO public_news
                    (category, title, publish_date, content, url)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item["category"],
                    item["title"],
                    item["publish_date"],
                    item["content"],
                    item["url"],
                ),
            )
            inserted += cursor.rowcount
        connection.commit()
    return inserted


def print_first_two(db_path: Path = DB_PATH) -> None:
    """打印数据库中前两条新闻，用于验证正文已经成功入库。"""
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, category, title, publish_date, content, url
            FROM public_news
            ORDER BY publish_date DESC, id DESC
            LIMIT 2
            """
        ).fetchall()

    print(f"\n数据库验证：显示前 {len(rows)} 条新闻")
    for row in rows:
        news_id, category, title, publish_date, content, url = row
        print("\n" + "-" * 72)
        print(f"ID: {news_id}")
        print(f"分类: {category}")
        print(f"标题: {title}")
        print(f"日期: {publish_date}")
        print(f"链接: {url}")
        print(f"正文长度: {len(content)} 字")
        print(f"正文: {content}")


def main() -> None:
    print(f"正在抓取：{HOME_URL}")
    home_html = fetch_html(HOME_URL)
    news_list = extract_news_list(home_html)
    if not news_list:
        raise RuntimeError("未从首页提取到综合要闻列表")
    print(f"首页发现 {len(news_list)} 条综合要闻，开始抓取详情页。")

    complete_news: List[Dict[str, str]] = []
    for index, item in enumerate(news_list, start=1):
        print(f"[{index}/{len(news_list)}] {item['title']}")
        try:
            article_html = fetch_html(item["url"])
            detail = extract_article(article_html)
        except (requests.RequestException, RuntimeError) as exc:
            print(f"  跳过：{exc}")
            continue

        if not detail["content"]:
            print("  跳过：正文 <p> 标签中没有文本")
            continue

        complete_news.append(
            {
                "category": CATEGORY,
                "title": detail["title"] or item["title"],
                "publish_date": detail["publish_date"] or item["publish_date"],
                "content": detail["content"],
                "url": item["url"],
            }
        )

    if not complete_news:
        raise RuntimeError("没有任何一条新闻成功提取正文，数据库未写入")

    init_database()
    inserted = save_news(complete_news)
    print(f"\n抓取完成：成功解析 {len(complete_news)} 条，新增入库 {inserted} 条。")
    print(f"数据库位置：{DB_PATH}")
    print_first_two()


if __name__ == "__main__":
    main()

"""Build the public digest from the configured official sources."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import html
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import requests
import yaml

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SHANGHAI = ZoneInfo("Asia/Shanghai")
CATEGORIES = ("新闻动态", "观点评论", "政策解读")
DATE = re.compile(r"(?<!\d)(20\d\d)[./年-](0?[1-9]|1[0-2])[./月-](0?[1-9]|[12]\d|3[01])(?!\d)")
EDITION_DATE = re.compile(r"/(20\d\d)-?(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/")
DATE_META = ('meta[name="publishdate"], meta[name="PubDate"], meta[name="pubdate"], '
             'meta[name="publishDate"], meta[name="publish_time"], meta[name="PubTime"], '
             'meta[property="article:published_time"]')
MISSING = "暂未提取"


def parse_date(pattern, value):
    match = pattern.search(value)
    if match:
        try:
            return date(*(int(part) for part in match.groups()))
        except ValueError:
            pass
    return None


def trusted(url, domain):
    parts = urlsplit(url)
    host = parts.hostname or ""
    return parts.scheme in ("http", "https") and (host == domain or host.endswith("." + domain))


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def fetch(session, url, domain):
    time.sleep(0.35)
    response = session.get(url, timeout=(8, 15))
    response.raise_for_status()
    if not trusted(response.url, domain):
        raise ValueError("重定向离开官方域名")
    try:
        text = response.content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = response.content.decode("gb18030", errors="replace")
    return BeautifulSoup(text, "html.parser"), response.url


def links(soup, base, source, pattern):
    for anchor in soup.select("a[href]"):
        link = urljoin(base, anchor["href"]).split("#", 1)[0].split("?", 1)[0]
        if trusted(link, source["domain"]) and re.fullmatch(pattern, urlsplit(link).path):
            yield link, anchor


def published(soup, link, edition, listed):
    if edition:
        return parse_date(EDITION_DATE, link)
    for node in soup.select(DATE_META + ', time[datetime], .pubtime, .pubTime, .article-time, '
                            '.time, #pubtime, .publish-time, .date, .source, .info, #source'):
        value = node.get("content") or node.get("datetime") or node.get_text(" ", strip=True)
        if stamp := parse_date(DATE, value):
            return stamp
    return listed


def keywords(title, paragraphs, topics):
    body = " ".join(paragraphs)
    scores = {
        topic: 12 * sum(word in title for word in words)
        + sum(min(body.count(word), 4) for word in words)
        for topic, words in topics.items()
    }
    ranked = sorted(scores, key=scores.get, reverse=True)
    tags = [name for name in ranked if scores[name]][:4]
    if len(tags) == 1:
        variants = sorted(
            (word for word in topics[tags[0]] if word != tags[0] and (word in title or word in body)),
            key=lambda word: (word in title, len(word)), reverse=True,
        )
        if variants:
            tags.append(variants[0])
    return tags


def core_view(title, paragraphs, tags, topics):
    terms = {word for tag in tags for word in topics.get(tag, [tag])}
    candidates = []
    for paragraph in paragraphs:
        for sentence in re.findall(r"[^。！？]+[。！？]", paragraph):
            sentence = sentence.strip()
            if not 40 <= len(sentence) <= 80 or sentence.count("“") != sentence.count("”"):
                continue
            if sentence.startswith(("本报讯", "新华社", "记者从", "图为", "如图", "同期举办")):
                continue
            matched = [term for term in terms if term in sentence]
            if matched:
                score = sum(3 if term in title else 1 for term in matched)
                score += 3 * int(any(word in sentence for word in
                                     ("推动", "应当", "关键", "需要", "明确", "提出", "有助于")))
                score -= 3 * int(bool(re.match(r"(近[日期]|[0-9]+月[0-9]+日)", sentence)))
                candidates.append((score, sentence))
    return max(candidates, key=lambda item: item[0])[1] if candidates else MISSING


def category(title, section, source):
    if re.search(r"政策解读|专家解读|一图读懂|答记者问", title):
        return "政策解读"
    if source.get("type"):
        return source["type"]
    if re.search(r"评论|理论|时评|人民观点|人民时评|钟声|金台论道|经济时评|光明论坛|光明时评|思想纵横|智库", title + section):
        return "观点评论"
    return "新闻动态"


def discover(session, source, today, days, warnings):
    entries = {}
    listing_count = 0
    domain = source["domain"]
    edition = source.get("edition")
    starts = [(source["url"], today - timedelta(days=offset))
              for offset in range(min(days + 1, 3) if edition else 1)]
    starts.extend((url, today) for url in source.get("extra_urls", []))
    for start, issue in starts:
        start = start.format(date=issue)
        try:
            soup, base = fetch(session, start, domain)
        except (requests.RequestException, ValueError) as exc:
            warnings.append(str(exc))
            continue
        listing_count += 1
        pages = [(soup, base, "")]
        if edition:
            for link, section in dict(links(soup, base, source, edition)).items():
                if link == base or parse_date(EDITION_DATE, link) != issue:
                    continue
                try:
                    layout, layout_url = fetch(session, link, domain)
                    pages.append((layout, layout_url, clean(section.get_text(" ", strip=True))))
                except (requests.RequestException, ValueError) as exc:
                    warnings.append(str(exc))
        for page, page_url, section in pages:
            region = page
            if source.get("context"):
                region = BeautifulSoup("".join(map(str, page.select(source["context"]))), "html.parser")
            for link, anchor in links(region, page_url, source, source["article"]):
                title = clean(anchor.get_text(" ", strip=True) or anchor.get("title", ""))
                if edition and parse_date(EDITION_DATE, link) != issue:
                    continue
                if len(title) < 4 or link in entries:
                    continue
                stamp = issue if edition else None
                row = anchor.find_parent("li")
                if row and len(row.find_all("a", href=True)) == 1:
                    stamp = stamp or parse_date(DATE, row.get_text(" ", strip=True))
                entries[link] = (title, stamp, section)
    return entries, listing_count


def collect(source, topics, today, days, existing, limit):
    status = {"source": source["name"], "lists": 0, "links": 0, "checked": 0,
              "dated": 0, "body": 0, "accepted": 0, "other_origin": 0, "warnings": []}
    warnings = status["warnings"]
    items = []
    with requests.Session() as session:
        session.headers["User-Agent"] = "Mozilla/5.0 (compatible; EconResearchDaily/1.0)"
        entries, status["lists"] = discover(session, source, today, days, warnings)
        status["links"] = len(entries)
        cutoff = today - timedelta(days=days)
        candidates = [(link, values) for link, values in entries.items()
                      if (not values[1] or cutoff <= values[1] <= today)
                      and not (link in existing and existing[link]["summary"] != MISSING)]
        candidates.sort(key=lambda pair: (bool(keywords(pair[1][0], [], topics)),
                                          pair[1][1] or today), reverse=True)
        for link, (title, listed, section) in candidates[:limit]:
            status["checked"] += 1
            paragraphs = []
            stamp = listed
            origin = source.get("origin")
            byline = source["name"]
            try:
                soup, final_url = fetch(session, link, source["domain"])
                if not re.fullmatch(source["article"], urlsplit(final_url).path):
                    raise ValueError("返回页面地址与正文规则不匹配")
                attribution = soup.select_one('meta[name="source"], meta[name="ContentSource"]')
                actual = clean(attribution.get("content", "")) if attribution else ""
                if source.get("attribution"):
                    visible = soup.select_one(source["attribution"])
                    actual = re.sub(r"^来源\s*[:：]\s*", "", clean(visible.get_text(" ", strip=True))) if visible else ""
                if origin and origin not in actual:
                    status["other_origin"] += 1
                    continue
                if origin and actual:
                    byline = actual
                elif actual and source.get("show_attribution") and actual != byline:
                    byline += "（原载" + actual + "）"
                headline = soup.select_one('meta[name="ArticleTitle"], meta[name="articletitle"], '
                                           'meta[property="og:title"], h1, #title, .article h2, .m-article-main h2')
                if headline:
                    title = clean(headline.get("content") or headline.get_text(" ", strip=True)) or title
                stamp = published(soup, final_url, source.get("edition"), listed) or listed
                paragraphs = list(dict.fromkeys(
                    clean(p.get_text(" ", strip=True))
                    for p in soup.select(source["body"])
                    if len(clean(p.get_text(" ", strip=True))) >= 20
                ))
            except (requests.RequestException, ValueError) as exc:
                warnings.append(str(exc))
                if origin:
                    continue
            status["body"] += bool(paragraphs)
            if not stamp:
                continue
            status["dated"] += 1
            if not cutoff <= stamp <= today:
                continue
            tags = keywords(title, paragraphs, topics)
            if len(tags) < 2:
                continue
            items.append(dict(title=title, published=stamp.isoformat(), source=source["name"], byline=byline,
                              url=link, tags=tags, type=category(title, section, source),
                              summary=core_view(title, paragraphs, tags, topics)))
    status["accepted"] = len(items)
    return items, status


def write_file(path, content):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def render(items, statuses, now):
    cards = []
    for item in items:
        tags = "".join(f"<li>{html.escape(tag)}</li>" for tag in item["tags"])
        title, kind, source, stamp, summary, link = (
            html.escape(item.get("byline", item[key]) if key == "source" else item[key], quote=True) for key in ("title", "type", "source", "published", "summary", "url")
        )
        cards.append(
            f'<article data-kind="{kind}"><div class="meta">{kind} <span>·</span> {source}'
            f' <span>·</span> <time datetime="{stamp}">{stamp}</time></div>'
            f'<h2><a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a></h2>'
            f'<p>{summary}</p><ul class="tags">{tags}</ul></article>'
        )
    problems = [s["source"] for s in statuses if not s["links"] or s["warnings"]
                or (s["checked"] and not s["body"] and not s["dated"])]
    status = f"更新于 {now:%Y-%m-%d %H:%M} · 北京时间"
    if problems:
        status += " · 部分来源采集异常"
    template = (ROOT / "page.html").read_text(encoding="utf-8-sig")
    for token, value in {"{{CARDS}}": "\n".join(cards), "{{STATUS}}": html.escape(status)}.items():
        template = template.replace(token, value, 1)
    if cards:
        template = template.replace('id="empty" role="status"', 'id="empty" role="status" hidden')
    write_file(ROOT / "index.html", template)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=45)
    parser.add_argument("--limit", type=int, default=75, help="每个来源的文章请求上限")
    parser.add_argument("--source", action="append", help="仅检查指定来源，可重复传入")
    parser.add_argument("--check", action="store_true", help="打印诊断，不写入归档")
    args = parser.parse_args()
    config = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8-sig"))
    selected = [s for s in config["sources"] if not args.source or s["name"] in args.source]
    if not selected or args.days < 0 or args.limit < 1:
        parser.error("请检查来源名称、天数和请求上限")
    now = datetime.now(SHANGHAI)
    archive = DATA / "items.json"
    existing = {}
    if archive.exists() and not args.check:
        for item in json.loads(archive.read_text(encoding="utf-8-sig")):
            if item.get("type") in CATEGORIES and item.get("summary") and any(
                trusted(item["url"], s["domain"]) and s["name"] == item["source"] for s in config["sources"]
            ):
                existing[item["url"]] = item
    statuses = []
    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = [executor.submit(collect, s, config["topics"], now.date(), args.days,
                                   existing, args.limit) for s in selected]
        results = [future.result() for future in futures]
    for items, status in results:
        existing.update((item["url"], item) for item in items)
        statuses.append(status)
        print(json.dumps(status, ensure_ascii=False), flush=True)
        if args.check:
            for item in items[:2]:
                print(json.dumps(item, ensure_ascii=False), flush=True)
    if not args.check:
        items = sorted(existing.values(), key=lambda x: (x["published"], x["title"]), reverse=True)[:1000]
        write_file(archive, json.dumps(items, ensure_ascii=False, indent=2) + "\n")
        write_file(DATA / "last_run.json", json.dumps(
            {"updated": now.isoformat(), "total": len(items), "sources": statuses},
            ensure_ascii=False, indent=2,
        ) + "\n")
        render(items, statuses, now)


if __name__ == "__main__":
    main()

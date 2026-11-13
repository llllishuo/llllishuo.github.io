#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Menghan Studio 博客生成器
=========================

用法：
    pip install -r requirements.txt
    python build.py                # 生成整站
    python build.py --serve        # 生成 + 本地预览 http://127.0.0.1:8000

源码结构：
    content/posts/*.md        文章（front matter + markdown）
    content/projects/*.md     项目页（front matter + markdown，可内嵌 HTML）
    content/about.md          关于页
    assets/                   静态资源（css / js / img / video / files）
    templates/                —— 模板写在本文件里，不单独存放

产物直接写到仓库根目录，GitHub Pages 以 main 分支根目录发布（有 .nojekyll，
所以不走 Jekyll，生成什么就是什么）。
"""

from __future__ import annotations

import html
import io
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import date, datetime

import markdown
from pygments.formatters import HtmlFormatter

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")

# 站点地址与环境变量：
#   SITE_URL  站点绝对地址，用于 canonical / og / feed / sitemap
#   SITE_BASE 站点所在的路径前缀（部署在子目录时用，如 /menghan）
SITE_URL = os.environ.get("SITE_URL", "https://llllishuo.github.io").rstrip("/")
SITE_BASE = os.environ.get("SITE_BASE", "").rstrip("/")

# --------------------------------------------------------------------------
# 站点配置
# --------------------------------------------------------------------------

SITE = {
    "name": "Menghan Studio",
    "short": "Menghan",
    "monogram": "孟",
    "tagline": "代码 · 读书 · 折腾",
    "url": SITE_URL,
    "base": SITE_BASE,
    "description": "MenghanStudio 的个人主页：嵌入式与系统方向的开发笔记、笔面试整理、"
                   "马列毛经典读书笔记，以及自己动手做的小工具。",
    "author": "MenghanStudio",
    "github": "https://github.com/llllishuo",
    "email": "1756524586@qq.com",
    "keywords": "嵌入式, Rust, RTOS, C++, 操作系统, 读书笔记, 马列毛, 个人博客, MenghanStudio",
}

CATEGORIES = [
    {
        "slug": "dev",
        "name": "开发笔记",
        "hue": 210,
        "desc": "操作系统、内存管理、语言与工具链——踩过的坑和想明白的原理。",
    },
    {
        "slug": "interview",
        "name": "笔面试",
        "hue": 22,
        "desc": "C++ / Rust / RTOS 的笔试题、面试题与答题思路整理。",
    },
    {
        "slug": "reading",
        "name": "读书笔记",
        "hue": 348,
        "desc": "马克思、恩格斯、列宁、毛泽东经典原著的摘录与批注。",
    },
    {
        "slug": "special",
        "name": "专题",
        "hue": 268,
        "desc": "长线整理的专题：用一套材料把一条线索串起来。",
    },
]
CAT_BY_SLUG = {c["slug"]: c for c in CATEGORIES}

NAV = [
    ("/posts/", "文章", "posts"),
    ("/categories/", "分类", "categories"),
    ("/projects/", "项目", "projects"),
    ("/about/", "关于", "about"),
]

# 需要清理的历史产物（生成前删掉，避免陈旧文件堆积）
# 注意：demo/ 是手放的静态演示页（时薪计算器网页版），不在这里清理。
GENERATED = ["posts", "categories", "tags", "projects", "about",
             "2024", "index.html", "tags.html", "about.html", "feed.xml",
             "sitemap.xml", "robots.txt", "404.html"]
KEEP_AT_ROOT = {"assets", "content", "build.py", "requirements.txt", "README.md",
                ".nojekyll", ".git", ".gitignore", "LICENSE"}


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------

def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def strip_md(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^\s{0,3}[#>\-*+]+\s*", " ", text, flags=re.M)
    text = re.sub(r"[*_`~]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def reading_time(body: str) -> int:
    text = strip_md(body)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z0-9]+", text))
    return max(1, round((cjk + words * 1.4) / 400))


def slugify_heading(value: str, separator: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().lower()
    value = re.sub(r"[^\w\u4e00-\u9fff]+", separator, value, flags=re.U)
    return value.strip(separator) or "section"


def parse_front_matter(raw: str) -> tuple[dict, str]:
    """极简 front matter 解析：key: value，重复的 key 自动变成列表。"""
    meta: dict = {}
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            block = raw[3:end].strip("\n")
            body = raw[end + 4:].lstrip("\n")
            for line in block.splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                if val.startswith("[") and val.endswith("]"):
                    val = [v.strip() for v in val[1:-1].split(",") if v.strip()]
                if key in meta:
                    if not isinstance(meta[key], list):
                        meta[key] = [meta[key]]
                    meta[key].append(val)
                else:
                    meta[key] = val
    return meta, body


def as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in re.split(r"[,，]", value) if v.strip()]
    return [str(value)]


def fmt_date(value: str, human: bool = True) -> str:
    try:
        d = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return str(value)
    return f"{d.year} 年 {d.month} 月 {d.day} 日" if human else d.isoformat()

def parse_date(value: str) -> date:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return date(1970, 1, 1)


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------

MD = markdown.Markdown(
    extensions=[
        "fenced_code",
        "codehilite",
        "tables",
        "toc",
        "sane_lists",
        "md_in_html",
        "attr_list",
    ],
    extension_configs={
        "codehilite": {"guess_lang": False, "css_class": "codehilite"},
        "toc": {"slugify": slugify_heading, "toc_depth": "2-3", "permalink": False},
    },
    output_format="html5",
)


def render_md(body: str) -> tuple[str, str]:
    """返回 (正文 HTML, 目录 HTML)。"""
    MD.reset()
    out = MD.convert(body)
    toc = getattr(MD, "toc", "")
    if toc:
        toc = re.sub(r'^\s*<div class="toc">\s*', "", toc)
        toc = re.sub(r'\s*</div>\s*$', "", toc)
        toc = re.sub(r'<span class="toctitle">.*?</span>', "", toc, flags=re.S)
    return out, toc


# --------------------------------------------------------------------------
# 数据装载
# --------------------------------------------------------------------------

def load_posts() -> list[dict]:
    posts = []
    folder = os.path.join(CONTENT, "posts")
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".md"):
            continue
        raw = open(os.path.join(folder, name), encoding="utf-8").read()
        meta, body = parse_front_matter(raw)
        slug = meta.get("slug") or name[:-3]
        cat_slug = meta.get("category", "dev")
        cat = CAT_BY_SLUG.get(cat_slug, CATEGORIES[0])
        html_body, toc = render_md(body)
        content_text = strip_md(body)
        excerpt = meta.get("excerpt") or (content_text[:120] + ("…" if len(content_text) > 120 else ""))
        posts.append({
            "slug": slug,
            "title": meta.get("title", slug),
            "subtitle": meta.get("subtitle", ""),
            "date": meta.get("date", "1970-01-01"),
            "sort_date": parse_date(meta.get("date", "1970-01-01")),
            "category": cat,
            "tags": as_list(meta.get("tags")),
            "body_md": body,
            "html": html_body,
            "toc": toc,
            "excerpt": excerpt,
            "minutes": reading_time(body),
            "url": f"/posts/{slug}/",
            "old_url": meta.get("old_url", ""),
            "featured": str(meta.get("featured", "")).lower() in ("true", "yes", "1"),
        })
    posts.sort(key=lambda p: p["sort_date"], reverse=True)
    return posts


def load_projects() -> list[dict]:
    projects = []
    folder = os.path.join(CONTENT, "projects")
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".md"):
            continue
        raw = open(os.path.join(folder, name), encoding="utf-8").read()
        meta, body = parse_front_matter(raw)
        slug = meta.get("slug") or name[:-3]
        html_body, toc = render_md(body)
        links = []
        for item in as_list(meta.get("links")):
            parts = [p.strip() for p in str(item).split("|")]
            if len(parts) >= 2:
                links.append({"label": parts[0], "href": parts[1],
                              "desc": parts[2] if len(parts) > 2 else ""})
        projects.append({
            "slug": slug,
            "title": meta.get("title", slug),
            "tagline": meta.get("tagline", ""),
            "summary": meta.get("summary", ""),
            "badges": as_list(meta.get("badges")),
            "meta": as_list(meta.get("meta")),
            "actions": links,
            "order": int(meta.get("order", 99) or 99),
            "html": html_body,
            "toc": toc,
            "url": f"/projects/{slug}/",
            "card": meta.get("card", ""),
            "shape": meta.get("shape", "portrait"),
            "accent": meta.get("accent", ""),
        })
    projects.sort(key=lambda p: p["order"])
    return projects


# --------------------------------------------------------------------------
# 模板
# --------------------------------------------------------------------------

THEME_BOOT = """<script>(function(){try{
var p=new URLSearchParams(location.search).get('theme');
if(p==='dark'||p==='light'){localStorage.setItem('ms-theme',p);}
var t=(p==='dark'||p==='light')?p:localStorage.getItem('ms-theme');
if(!t){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>"""

ICON_SUN = ('<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="4.2"/>'
            '<path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2M5.4 5.4l1.6 1.6'
            'M17 17l1.6 1.6M18.6 5.4L17 7M7 17l-1.6 1.6"/></svg>')
ICON_MOON = ('<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
             'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
             '<path d="M20.5 14.6A8.6 8.6 0 0 1 9.4 3.5a8.6 8.6 0 1 0 11.1 11.1z"/></svg>')
ICON_MENU = ('<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" '
             'stroke-width="1.8" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>')
ICON_ARROW = ('<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" '
              'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
              '<path d="M5 12h13M13 6l6 6-6 6"/></svg>')


def header(active: str = "") -> str:
    items = []
    for href, label, key in NAV:
        cls = ' class="is-active"' if key == active else ""
        items.append(f'<a href="{href}"{cls}>{label}</a>')
    nav = "".join(items)
    return f"""
<header class="site-head">
  <div class="wrap head-row">
    <a class="brand" href="/" aria-label="{esc(SITE['name'])} 首页">
      <span class="brand-mark">{esc(SITE['monogram'])}</span>
      <span class="brand-text">
        <strong>{esc(SITE['name'])}</strong>
        <em>{esc(SITE['tagline'])}</em>
      </span>
    </a>
    <nav class="nav" id="site-nav">{nav}</nav>
    <div class="head-actions">
      <button class="icon-btn" id="theme-toggle" type="button"
              aria-label="切换深色/浅色模式" title="切换深色/浅色模式">
        <span class="ico-sun">{ICON_SUN}</span><span class="ico-moon">{ICON_MOON}</span>
      </button>
      <button class="icon-btn menu-btn" id="menu-toggle" type="button"
              aria-label="展开导航" aria-expanded="false" aria-controls="site-nav">{ICON_MENU}</button>
    </div>
  </div>
</header>"""


def footer() -> str:
    year = date.today().year
    return f"""
<footer class="site-foot">
  <div class="wrap foot-row">
    <div class="foot-brand">
      <span class="brand-mark small">{esc(SITE['monogram'])}</span>
      <p>{esc(SITE['name'])} · 记录学习与思考<br>
      <span class="muted">本博客内容仅作学习交流</span></p>
    </div>
    <div class="foot-links">
      <a href="/posts/">全部文章</a>
      <a href="/categories/">分类</a>
      <a href="/projects/">项目</a>
      <a href="{esc(SITE['github'])}" rel="noopener">GitHub</a>
      <a href="mailto:{esc(SITE['email'])}">邮箱</a>
      <a href="/feed.xml">RSS</a>
    </div>
  </div>
  <div class="wrap foot-base">
    <span>© {year} {esc(SITE['author'])}</span>
    <span>由 Python 生成的静态站点</span>
  </div>
</footer>"""


def apply_base(page: str) -> str:
    """把站内绝对路径（/assets/... 、/posts/...）加上部署前缀。"""
    if not SITE_BASE:
        return page
    return re.sub(r'((?:href|src|poster|action)=")/(?!/)', r"\1" + SITE_BASE + "/", page)


def layout(*, title: str, body: str, description: str = "", active: str = "",
           url: str = "", page_type: str = "website", body_class: str = "",
           extra_head: str = "") -> str:
    full_title = title if title == SITE["name"] else f"{title} · {SITE['name']}"
    desc = description or SITE["description"]
    canonical = SITE["url"] + (url or "/")
    return apply_base(f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="author" content="{esc(SITE['author'])}">
<meta name="keywords" content="{esc(SITE['keywords'])}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="{esc(page_type)}">
<meta property="og:site_name" content="{esc(SITE['name'])}">
<meta property="og:title" content="{esc(full_title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#f6f3ee" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#141311" media="(prefers-color-scheme: dark)">
<link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{esc(SITE['name'])}" href="/feed.xml">
<link rel="stylesheet" href="/assets/css/pygments.css">
<link rel="stylesheet" href="/assets/css/site.css">
{THEME_BOOT}
{extra_head}
</head>
<body class="{esc(body_class)}">
<a class="skip-link" href="#main">跳到正文</a>
{header(active)}
<main id="main">
{body}
</main>
{footer()}
<script src="/assets/js/site.js" defer></script>
</body>
</html>
""")


def section_head(title: str, more_href: str = "", more_label: str = "查看全部") -> str:
    more = (f'<a class="more-link" href="{more_href}">{esc(more_label)}{ICON_ARROW}</a>'
            if more_href else "")
    return f'<div class="section-head"><h2>{esc(title)}</h2>{more}</div>'


def chip(cat: dict) -> str:
    return (f'<a class="chip" href="/categories/{cat["slug"]}/" '
            f'style="--chip-hue:{cat["hue"]}">{esc(cat["name"])}</a>')


def post_row(post: dict) -> str:
    tags = "".join(f'<span class="tag">#{esc(t)}</span>' for t in post["tags"][:4])
    sub = (f'<p class="post-row-sub">{esc(post["subtitle"])}</p>'
           if post['subtitle'] else '')
    return f"""
<article class="post-row" data-cat="{esc(post['category']['slug'])}"
         data-search="{esc((post['title'] + ' ' + post['subtitle'] + ' ' + ' '.join(post['tags'])).lower())}">
  <div class="post-row-meta">
    {chip(post['category'])}
    <time datetime="{esc(post['date'])}">{esc(fmt_date(post['date']))}</time>
    <span class="dot">·</span><span class="muted">{post['minutes']} 分钟</span>
  </div>
  <a class="post-row-link" href="{post['url']}">
    <h3>{esc(post['title'])}</h3>
    {sub}
    <p class="post-row-excerpt">{esc(post['excerpt'])}</p>
  </a>
  <div class="tag-row">{tags}</div>
</article>"""


def project_card(p: dict) -> str:
    badges = "".join(f'<span class="badge">{esc(b)}</span>' for b in p["badges"][:4])
    accent = p.get("accent") or ""
    style = f' style="--card-accent:{esc(accent)}"' if accent else ""
    shot_cls = "card-shot is-wide" if p.get("shape") == "landscape" else "card-shot"
    shot = (f'<img class="{shot_cls}" src="{esc(p["card"])}" alt="{esc(p["title"])} 界面预览" loading="lazy">'
            if p.get("card") else "")
    return f"""
<a class="project-card" href="{p['url']}"{style}>
  <div class="card-visual">
    <div class="card-glow"></div>
    {shot}
  </div>
  <div class="card-body">
    <div class="badge-row">{badges}</div>
    <h3>{esc(p['title'])}</h3>
    <p>{esc(p['summary'] or p['tagline'])}</p>
    <span class="card-more">查看介绍与演示 {ICON_ARROW}</span>
  </div>
</a>"""


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------

def page_home(posts: list[dict], projects: list[dict]) -> str:
    latest = posts[:5]
    cat_counts = {c["slug"]: len([p for p in posts if p["category"]["slug"] == c["slug"]])
                  for c in CATEGORIES}
    cat_tiles = "".join(f"""
    <a class="cat-tile" href="/categories/{c['slug']}/" style="--chip-hue:{c['hue']}">
      <span class="cat-count">{cat_counts[c['slug']]:02d}</span>
      <span class="cat-name">{esc(c['name'])}</span>
      <span class="cat-desc">{esc(c['desc'])}</span>
    </a>""" for c in CATEGORIES)

    body = f"""
<section class="hero">
  <div class="wrap hero-inner">
    <p class="kicker">{esc(SITE['name'])} · 个人主页</p>
    <h1>写一点代码，<br>读一点书。</h1>
    <p class="hero-lead">
      嵌入式与系统方向的学习记录：内存管理、Rust / C++ / RTOS 的笔面试整理，
      马列毛经典原著的读书笔记，以及几个自己动手做的小工具。
    </p>
    <div class="hero-actions">
      <a class="btn btn-primary" href="/posts/">开始阅读 {ICON_ARROW}</a>
      <a class="btn btn-ghost" href="/projects/">看项目</a>
    </div>
    <dl class="hero-stats">
      <div><dt>文章</dt><dd>{len(posts)}</dd></div>
      <div><dt>项目</dt><dd>{len(projects)}</dd></div>
      <div><dt>分类</dt><dd>{len(CATEGORIES)}</dd></div>
    </dl>
  </div>
</section>

<section class="section wrap">
  {section_head('项目', '/projects/', '全部项目')}
  <div class="project-grid">
    {''.join(project_card(p) for p in projects)}
  </div>
</section>

<section class="section wrap">
  {section_head('最新文章', '/posts/', '全部文章')}
  <div class="post-list">
    {''.join(post_row(p) for p in latest)}
  </div>
</section>

<section class="section wrap">
  {section_head('按分类浏览', '/categories/', '分类总览')}
  <div class="cat-grid">{cat_tiles}</div>
</section>
"""
    return layout(title=SITE["name"], body=body, active="", url="/")


def page_posts(posts: list[dict]) -> str:
    chips = ('<button class="filter-chip is-active" data-cat="all" type="button">全部</button>' +
             "".join(f'<button class="filter-chip" data-cat="{c["slug"]}" type="button" '
                     f'style="--chip-hue:{c["hue"]}">{esc(c["name"])}</button>'
                     for c in CATEGORIES))
    years: dict[int, list[dict]] = {}
    for p in posts:
        years.setdefault(p["sort_date"].year, []).append(p)
    blocks = []
    for year in sorted(years, reverse=True):
        rows = "".join(post_row(p) for p in years[year])
        blocks.append(f'<div class="year-block"><h2 class="year">{year}'
                      f'<span class="year-count">{len(years[year])} 篇</span></h2>'
                      f'<div class="post-list">{rows}</div></div>')
    body = f"""
<section class="page-head wrap">
  <p class="kicker">文章</p>
  <h1>全部文章</h1>
  <p class="page-lead">共 {len(posts)} 篇，按时间倒序。可以按分类筛选，或直接搜索标题与标签。</p>
</section>

<section class="wrap">
  <div class="filter-bar">
    <div class="filter-chips">{chips}</div>
    <label class="search-box">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
           stroke-width="1.9" stroke-linecap="round"><circle cx="11" cy="11" r="6.4"/>
           <path d="M16 16l4.5 4.5"/></svg>
      <input id="post-filter" type="search" placeholder="搜索标题、副标题、标签…" autocomplete="off">
    </label>
  </div>
  <p class="filter-empty" id="filter-empty" hidden>没有匹配的文章，换个关键词试试。</p>
  {''.join(blocks)}
</section>
"""
    return layout(title="全部文章", body=body, active="posts", url="/posts/",
                  description="按时间归档的全部文章。")


def page_categories(posts: list[dict]) -> str:
    cards = []
    for c in CATEGORIES:
        items = [p for p in posts if p["category"]["slug"] == c["slug"]]
        lis = "".join(f'<li><time datetime="{esc(p["date"])}">{esc(fmt_date(p["date"], False))}</time>'
                      f'<a href="{p["url"]}">{esc(p["title"])}</a></li>' for p in items)
        cards.append(f"""
    <section class="cat-block" style="--chip-hue:{c['hue']}">
      <header>
        <h2><a href="/categories/{c['slug']}/">{esc(c['name'])}</a></h2>
        <span class="count-pill">{len(items)} 篇</span>
      </header>
      <p class="cat-block-desc">{esc(c['desc'])}</p>
      <ul class="cat-list">{lis or '<li class="muted">暂无文章</li>'}</ul>
    </section>""")
    body = f"""
<section class="page-head wrap">
  <p class="kicker">分类</p>
  <h1>分类总览</h1>
  <p class="page-lead">四类内容：工程笔记、笔面试整理、经典原著读书笔记、长线专题。</p>
</section>
<section class="wrap cat-blocks">{''.join(cards)}</section>
"""
    return layout(title="分类总览", body=body, active="categories", url="/categories/",
                  description="按主题分类浏览全部文章。")


def page_category(cat: dict, posts: list[dict]) -> str:
    items = [p for p in posts if p["category"]["slug"] == cat["slug"]]
    rows = "".join(post_row(p) for p in items) or '<p class="muted">这个分类还没有文章。</p>'
    others = "".join(f'<a class="chip" href="/categories/{c["slug"]}/" '
                     f'style="--chip-hue:{c["hue"]}">{esc(c["name"])}</a>'
                     for c in CATEGORIES if c["slug"] != cat["slug"])
    body = f"""
<section class="page-head wrap cat-head" style="--chip-hue:{cat['hue']}">
  <a class="back-link" href="/categories/">← 全部分类</a>
  <p class="kicker">分类 · {len(items)} 篇</p>
  <h1>{esc(cat['name'])}</h1>
  <p class="page-lead">{esc(cat['desc'])}</p>
  <div class="chip-row">{others}</div>
</section>
<section class="wrap">
  <div class="post-list">{rows}</div>
</section>
"""
    return layout(title=cat["name"], body=body, active="categories",
                  url=f"/categories/{cat['slug']}/", description=cat["desc"])


def page_tags(posts: list[dict]) -> str:
    tag_map: dict[str, list[dict]] = {}
    for p in posts:
        for t in p["tags"]:
            tag_map.setdefault(t, []).append(p)
    ordered = sorted(tag_map.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    cloud = "".join(f'<a href="#tag-{esc(t)}" class="cloud-tag">{esc(t)}'
                    f'<span>{len(ps)}</span></a>' for t, ps in ordered)
    blocks = []
    for t, ps in ordered:
        lis = "".join(f'<li><time datetime="{esc(p["date"])}">{esc(fmt_date(p["date"], False))}</time>'
                      f'<a href="{p["url"]}">{esc(p["title"])}</a></li>' for p in ps)
        blocks.append(f"""
    <section class="tag-block" id="tag-{esc(t)}">
      <h2>#{esc(t)}<span class="count-pill">{len(ps)} 篇</span></h2>
      <ul class="cat-list">{lis}</ul>
    </section>""")
    body = f"""
<section class="page-head wrap">
  <p class="kicker">标签</p>
  <h1>标签索引</h1>
  <p class="page-lead">共 {len(ordered)} 个标签。点击跳到对应分组。</p>
  <div class="tag-cloud">{cloud}</div>
</section>
<section class="wrap tag-blocks">{''.join(blocks)}</section>
"""
    return layout(title="标签索引", body=body, url="/tags/",
                  description="按标签浏览全部文章。")


def page_projects(projects: list[dict]) -> str:
    cards = "".join(project_card(p) for p in projects)
    body = f"""
<section class="page-head wrap">
  <p class="kicker">项目</p>
  <h1>自己做的工具</h1>
  <p class="page-lead">都是能直接拿来用的东西：一个 VSCode 串口调试扩展、一个 Android 黑名单清理器，一个三端一致的时薪计算器。</p>
</section>
<section class="wrap">
  <div class="project-grid wide">{cards}</div>
</section>
"""
    return layout(title="项目", body=body, active="projects", url="/projects/",
                  description="MenghanStudio 的开源项目与应用。")


def page_post(post: dict, prev: dict | None, nxt: dict | None) -> str:
    tags = "".join(f'<a class="tag" href="/tags/#tag-{esc(t)}">#{esc(t)}</a>' for t in post["tags"])
    toc_html = ""
    if post["toc"] and post["toc"].count("<li>") >= 3:
        toc_html = f"""
  <aside class="post-toc" aria-label="目录">
    <p class="toc-title">目录</p>
    {post['toc']}
  </aside>"""
    nav_parts = []
    if prev:
        nav_parts.append(f'<a class="post-nav-item prev" href="{prev["url"]}">'
                         f'<span class="k">← 上一篇</span><strong>{esc(prev["title"])}</strong></a>')
    if nxt:
        nav_parts.append(f'<a class="post-nav-item next" href="{nxt["url"]}">'
                         f'<span class="k">下一篇 →</span><strong>{esc(nxt["title"])}</strong></a>')
    body = f"""
<article class="post">
  <header class="post-head wrap" style="--chip-hue:{post['category']['hue']}">
    <a class="back-link" href="/posts/">← 全部文章</a>
    <div class="post-meta-row">
      {chip(post['category'])}
      <time datetime="{esc(post['date'])}">{esc(fmt_date(post['date']))}</time>
      <span class="dot">·</span><span class="muted">{post['minutes']} 分钟阅读</span>
    </div>
    <h1>{esc(post['title'])}</h1>
    {f'<p class="post-sub">{esc(post["subtitle"])}</p>' if post['subtitle'] else ''}
  </header>
  <div class="wrap post-layout">
    <div class="prose">{post['html']}</div>
    {toc_html}
  </div>
  <footer class="wrap post-foot">
    <div class="tag-row">{tags}</div>
    <div class="post-nav">{''.join(nav_parts)}</div>
  </footer>
</article>
"""
    return layout(title=post["title"], body=body, active="posts", url=post["url"],
                  page_type="article", description=post["excerpt"],
                  body_class="has-post")


def page_project(p: dict) -> str:
    badges = "".join(f'<span class="badge">{esc(b)}</span>' for b in p["badges"])
    meta = "".join(f'<div><dt>{esc(m.split("|")[0])}</dt><dd>{esc(m.split("|")[1])}</dd></div>'
                   for m in p["meta"] if "|" in m)
    actions = []
    for i, a in enumerate(p["actions"]):
        cls = "btn btn-primary" if i == 0 else "btn btn-ghost"
        ext = ' target="_blank" rel="noopener"' if a["href"].startswith("http") else ""
        actions.append(f'<a class="{cls}" href="{esc(a["href"])}"{ext}>{esc(a["label"])}'
                       f'{ICON_ARROW}</a>')
    toc_html = ""
    if p["toc"] and p["toc"].count("<li>") >= 3:
        toc_html = f"""
  <aside class="post-toc" aria-label="目录">
    <p class="toc-title">本页内容</p>
    {p['toc']}
  </aside>"""
    info = f'<dl class="project-meta">{meta}</dl>' if meta else ""
    body = f"""
<article class="project">
  <header class="project-head wrap" style="--card-accent:{esc(p.get('accent') or 'var(--accent)')}">
    <a class="back-link" href="/projects/">← 全部项目</a>
    <div class="badge-row">{badges}</div>
    <h1>{esc(p['title'])}</h1>
    <p class="project-tagline">{esc(p['tagline'])}</p>
    <div class="hero-actions">{''.join(actions)}</div>
    {info}
  </header>
  <div class="wrap project-layout">
    <div class="prose">{p['html']}</div>
    {toc_html}
  </div>
</article>
"""
    return layout(title=p["title"], body=body, active="projects", url=p["url"],
                  description=p["summary"] or p["tagline"], body_class="has-project")


def page_about() -> str:
    raw = open(os.path.join(CONTENT, "about.md"), encoding="utf-8").read()
    meta, body_md = parse_front_matter(raw)
    html_body, _ = render_md(body_md)
    links = "".join(f'<a class="btn btn-ghost" href="{esc(l.split("|")[1])}"'
                    f'{" target=\"_blank\" rel=\"noopener\"" if l.split("|")[1].startswith("http") else ""}>'
                    f'{esc(l.split("|")[0])}</a>'
                    for l in as_list(meta.get("links")) if "|" in l)
    body = f"""
<section class="page-head wrap">
  <p class="kicker">关于</p>
  <h1>{esc(meta.get('title', '关于我'))}</h1>
  <p class="page-lead">{esc(meta.get('lead', ''))}</p>
  <div class="hero-actions">{links}</div>
</section>
<section class="wrap">
  <div class="prose about-prose">{html_body}</div>
</section>
"""
    return layout(title="关于", body=body, active="about", url="/about/",
                  description=meta.get("lead", SITE["description"]))


def page_404() -> str:
    body = """
<section class="wrap notfound">
  <p class="kicker">404</p>
  <h1>这页不见了</h1>
  <p class="page-lead">可能链接写错了，或者文章已经挪了位置。</p>
  <div class="hero-actions">
    <a class="btn btn-primary" href="/">回首页</a>
    <a class="btn btn-ghost" href="/posts/">全部文章</a>
  </div>
</section>
"""
    return layout(title="404", body=body, url="/404.html")


def redirect_page(target: str, label: str = "") -> str:
    return apply_base(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>正在跳转…</title>
<link rel="canonical" href="{esc(target)}">
<meta http-equiv="refresh" content="0; url={esc(target)}">
<meta name="robots" content="noindex">
<style>body{{font-family:system-ui,"Microsoft YaHei",sans-serif;margin:4rem auto;max-width:34rem;
padding:0 1.2rem;color:#222;line-height:1.8}}a{{color:#a8322d}}</style>
<script>location.replace("{target}");</script>
</head>
<body>
<p>页面已迁移到 <a href="{esc(target)}">{esc(label or target)}</a>。</p>
</body>
</html>
""")


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

def write_out(rel_path: str, text: str) -> None:
    path = os.path.join(ROOT, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def clean() -> None:
    for name in GENERATED:
        path = os.path.join(ROOT, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)


def build_pygments_css() -> str:
    """只保留 token 颜色，容器底色交给 site.css 管（深浅色统一）。"""
    def clean(css: str) -> str:
        keep = []
        for line in css.splitlines():
            low = line.lower()
            if "background" in low and "{" in low or low.strip().startswith("background"):
                continue
            keep.append(line)
        return "\n".join(keep)

    light = clean(HtmlFormatter(style="friendly").get_style_defs(".codehilite"))
    dark = clean(HtmlFormatter(style="monokai").get_style_defs(".codehilite"))
    dark = dark.replace(".codehilite", 'html[data-theme="dark"] .codehilite')
    light = light.replace(".codehilite", 'html[data-theme="light"] .codehilite')
    return "/* 由 build.py 用 Pygments 生成（容器底色见 site.css） */\n" + light + "\n\n" + dark + "\n"


def build_feed(posts: list[dict]) -> str:
    items = []
    for p in posts[:20]:
        items.append(f"""  <item>
    <title>{esc(p['title'])}</title>
    <link>{esc(SITE['url'] + p['url'])}</link>
    <guid isPermaLink="true">{esc(SITE['url'] + p['url'])}</guid>
    <pubDate>{p['sort_date'].strftime('%a, %d %b %Y 00:00:00 +0800')}</pubDate>
    <category>{esc(p['category']['name'])}</category>
    <description>{esc(p['excerpt'])}</description>
  </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{esc(SITE['name'])}</title>
  <link>{esc(SITE['url'])}/</link>
  <description>{esc(SITE['description'])}</description>
  <language>zh-CN</language>
  <lastBuildDate>{datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')}</lastBuildDate>
  <atom:link href="{esc(SITE['url'])}/feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
</channel>
</rss>
"""


def build_sitemap(posts: list[dict], projects: list[dict]) -> str:
    urls = [("/", "1.0", "daily"), ("/posts/", "0.9", "daily"),
            ("/categories/", "0.8", "weekly"), ("/projects/", "0.8", "weekly"),
            ("/about/", "0.5", "monthly"), ("/tags/", "0.5", "weekly")]
    for c in CATEGORIES:
        urls.append((f"/categories/{c['slug']}/", "0.7", "weekly"))
    for p in posts:
        urls.append((p["url"], "0.7", "monthly"))
    for p in projects:
        urls.append((p["url"], "0.8", "monthly"))
    entries = "".join(
        f"  <url><loc>{esc(SITE['url'] + u)}</loc>"
        f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>\n"
        for u, prio, freq in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + entries + "</urlset>\n")


# --------------------------------------------------------------------------
# 自检：内部链接是否都能落到文件上
# --------------------------------------------------------------------------

LINK_RE = re.compile(r'(?:href|src)="(/[^"#?]*)(?:[?#][^"]*)?"')


def check_links() -> int:
    problems = []
    pages = []
    for base, _dirs, files in os.walk(ROOT):
        rel = os.path.relpath(base, ROOT).replace("\\", "/")
        if rel.startswith(("content", "assets", ".git")):
            continue
        for f in files:
            if f.endswith(".html"):
                pages.append(os.path.join(base, f))
    for page in pages:
        text = open(page, encoding="utf-8").read()
        rel_page = os.path.relpath(page, ROOT).replace("\\", "/")
        for m in LINK_RE.finditer(text):
            target = m.group(1)
            if target.startswith("//"):
                continue
            if SITE_BASE and target.startswith(SITE_BASE + "/"):
                target = target[len(SITE_BASE):]
            elif SITE_BASE and target == SITE_BASE:
                target = "/"
            local = os.path.join(ROOT, target.lstrip("/").replace("%20", " "))
            if target.endswith("/"):
                ok = os.path.exists(os.path.join(local, "index.html"))
            else:
                ok = os.path.exists(local) or os.path.exists(local + ".html") \
                     or os.path.exists(os.path.join(local, "index.html"))
            if not ok:
                problems.append(f"{rel_page} → {target}")
    if problems:
        print("!! 断链 %d 处：" % len(problems))
        for p in sorted(set(problems)):
            print("   ", p)
    else:
        print("链接自检：%d 个页面，内部链接全部命中。" % len(pages))
    return len(problems)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    posts = load_posts()
    projects = load_projects()
    clean()

    write_out("index.html", page_home(posts, projects))
    write_out("posts/index.html", page_posts(posts))
    write_out("categories/index.html", page_categories(posts))
    for c in CATEGORIES:
        write_out(f"categories/{c['slug']}/index.html", page_category(c, posts))
    write_out("tags/index.html", page_tags(posts))
    write_out("projects/index.html", page_projects(projects))
    for p in projects:
        write_out(f"projects/{p['slug']}/index.html", page_project(p))
    write_out("about/index.html", page_about())
    write_out("404.html", page_404())

    for i, post in enumerate(posts):
        prev_post = posts[i + 1] if i + 1 < len(posts) else None   # 更旧的一篇
        next_post = posts[i - 1] if i - 1 >= 0 else None          # 更新的一篇
        write_out(f"posts/{post['slug']}/index.html",
                  page_post(post, prev_post, next_post))
        if post["old_url"]:
            write_out(f"{post['old_url'].strip('/')}/index.html",
                      redirect_page(post["url"], post["title"]))

    # 老地址兜底
    for old, new in (("tags", "/tags/"), ("about.html", "/about/")):
        if old == "tags":
            write_out("tags.html", redirect_page(new, "标签索引"))
        else:
            write_out(old, redirect_page(new, "关于"))

    write_out("assets/css/pygments.css", build_pygments_css())
    write_out("feed.xml", build_feed(posts))
    write_out("sitemap.xml", build_sitemap(posts, projects))
    write_out("robots.txt", "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE["url"])

    open(os.path.join(ROOT, ".nojekyll"), "w").close()

    print("生成完成：%d 篇文章，%d 个项目。" % (len(posts), len(projects)))
    bad = check_links()

    if "--serve" in argv:
        import http.server
        import socketserver
        port = 8000
        for i, a in enumerate(argv):
            if a == "--port" and i + 1 < len(argv):
                port = int(argv[i + 1])
        os.chdir(ROOT)
        handler = http.server.SimpleHTTPRequestHandler

        class Quiet(handler):
            def log_message(self, *args):  # noqa: D102
                pass

        with socketserver.TCPServer(("127.0.0.1", port), Quiet) as httpd:
            print("预览：http://127.0.0.1:%d/  （Ctrl+C 退出）" % port)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

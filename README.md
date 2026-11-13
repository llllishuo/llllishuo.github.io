# MenghanStudio 的博客

纯静态站点，用 Python 脚本生成，托管在 GitHub Pages：<https://llllishuo.github.io>

没有前端框架，没有第三方 CDN，不需要 Jekyll。生成什么就是什么——仓库根目录里的 HTML
就是线上跑的东西（有 `.nojekyll`，GitHub Pages 不会再去解释一层）。

## 写一篇新文章

在 `content/posts/` 里新建一个 `.md` 文件，正文用 Markdown，开头写 front matter：

```markdown
---
title: 标题
subtitle: 一句话副标题（可省）
date: 2026-11-13
category: dev
tags: 操作系统, Rust
excerpt: 列表页显示的摘要，一到两句话。
old_url:                      # 可选：旧站地址，会生成一个跳转页
---

## 正文从这里开始
```

- `category` 必须是 `build.py` 里 `CATEGORIES` 定义过的 slug，现有四个：
  `dev`（开发笔记）、`interview`（笔面试）、`reading`（读书笔记）、`special`（专题）。
- `tags` 用逗号分隔，会出现在列表页和 `/tags/` 索引里。
- 文件名随意，默认用文件名做 URL 的一部分；想固定链接就加 `slug: my-post`，
  文章地址是 `/posts/<slug>/`。

## 加一个项目页

在 `content/projects/` 里新建 `.md`。front matter 决定页面骨架，正文写内容
（正文里可以直接嵌 HTML，比如视频、截图墙、在线演示的 iframe）：

```markdown
---
title: 项目名
tagline: 一句话卖点
summary: 卡片上显示的简介
badges: Android, Java, Apache-2.0
meta: 当前版本|v1.0.0
meta: 平台|Android 9+
links: 源码仓库|https://github.com/llllishuo/xxx
card: /assets/img/projects/xxx/card.jpg
accent: '#3f8f74'
order: 3
---
```

`meta` 和 `links` 都写成 `名称|值`，可以写多行，重复的键会自动收集成列表。

## 生成与预览

```bash
pip install -r requirements.txt
python build.py            # 生成整站
python build.py --serve    # 生成 + 本地预览 http://127.0.0.1:8000/
```

`build.py` 每次会先清掉旧的生成物（`posts/`、`categories/`、`tags/`、`projects/`、
`about/`、`index.html` 等），再重新生成，顺便跑一遍内部链接自检——有断链会直接报出来。

## 发布

生成物就在仓库根目录，所以发布就是提交：

```bash
python build.py
git add -A
git commit -m "写点什么"
git push
```

推送后 GitHub Pages 会自动更新（main 分支根目录）。

## 目录结构

```text
content/            源文件
  posts/*.md          文章
  projects/*.md       项目页
  about.md            关于页
assets/             静态资源（css / js / img / video / files）
demo/hourlywage/    时薪计算器网页版（手放的静态演示页，不参与生成）
build.py            生成器
index.html 等        生成产物
```

## 站内页面

| 路径 | 内容 |
| --- | --- |
| `/` | 首页：项目卡片 + 最新文章 + 分类入口 |
| `/posts/` | 全部文章，支持按分类筛选和关键词搜索 |
| `/categories/` 与 `/categories/<slug>/` | 分类总览与分类列表 |
| `/tags/` | 标签索引 |
| `/projects/` 与 `/projects/<slug>/` | 项目列表与项目详情（含截图、视频、在线演示） |
| `/about/` | 关于 |
| `/feed.xml` `/sitemap.xml` | RSS 与站点地图 |

## 旧地址

旧版用 Jekyll 的 `permalink: pretty`，文章地址形如 `/2024/10/26/备忘录-开发/`。
新站会为每篇带 `old_url` 的文章生成一个 meta-refresh 跳转页，老链接不会 404。

## 历史

旧版是 Jekyll + [Hux Blog](https://github.com/Huxpro/huxpro.github.io) 主题
（经 [BY Blog](https://github.com/qiubaiying/qiubaiying.github.io) 二次整理）。
2026 年 11 月重做：换成 Python 生成的纯静态站点，重排了分类，图片全部本地化，
并补上了两个项目的介绍与演示页。

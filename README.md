# Indie Explorer Practice

这是一个聚合中文独立开发者作品的前端练习项目。目前收录以下开源仓库：

- [`1c7/chinese-independent-developer`](https://github.com/1c7/chinese-independent-developer)
- [`DevEloLin/chinese-indie-vibe-coding`](https://github.com/DevEloLin/chinese-indie-vibe-coding)
- [`XiaomingX/1000-chinese-independent-developer-plus`](https://github.com/XiaomingX/1000-chinese-independent-developer-plus)

## 更新项目目录

在本目录执行：

```bash
python3 scripts/update_catalog.py
```

脚本会下载各仓库的最新 README，并生成：

- `data/projects.json`：合并后的项目数据，每条记录包含收录来源。
- `data/sources.json`：来源仓库、许可信息、解析数量和实际新增数量。

跨仓库中指向同一网址的项目会按来源顺序去重，网址中的常见跟踪参数也会被忽略。主来源仓库内部允许多个项目共享同一网址，以兼容原始数据。

## 自动更新

本地练习时使用自动更新服务器：

```bash
python3 scripts/auto_update_server.py --port 4173
```

服务器启动时会立即更新一次目录，之后每 6 小时重新抓取。可以通过 `--interval-hours` 修改间隔。网页保持打开时还会每 30 分钟检查一次本地 JSON，检测到变化后无刷新更新列表。

仓库中的 `.github/workflows/update-catalog.yml` 会在北京时间每天 04:15 自动运行，也可以在 GitHub Actions 页面手动触发。工作流会重新生成数据、运行测试，并且只在目录确实发生变化时提交 JSON。

如果只想练习基础解析器，也可以继续使用本地单仓库命令：

```bash
python3 scripts/parse_readme.py ../repo/README.md data/projects.json
```

## 运行测试

```bash
python3 -m unittest discover -s tests -v
```

## 启动页面

只需要静态预览、不需要本地自动更新时，可以使用：

```bash
python3 -m http.server 4173
```

然后访问 `http://localhost:4173`。

# family_story

家庭每日小故事 —— 把截图里的多格漫画 / 绘本，自动整理成给小孩讲故事的单文件网页（带拼音、章节目录、双层进度条、触屏 / 键盘翻页、水印背景）。

## 目录结构

```
family_story/
├── README.md                     ← 本文件
├── skill/
│   ├── comic-story-builder/      ← Claude 用的 skill 源码（可编辑）
│   │   ├── SKILL.md              ← skill 入口说明，里面写死了工作流和 IP 规则
│   │   ├── crop_panels.py        ← 抠图 + build 单文件 HTML 的 Python 脚本
│   │   ├── viewer.html           ← 网页模板（数据由 build 时注入）
│   │   ├── build_ppt.py          ← 可选：导出 .pptx
│   │   └── background/           ← 默认水印图池，可替换为家庭照片
│   └── comic-story-builder.skill ← 同上目录的 zip 打包版，方便安装到 Claude Code
└── story/
    └── 父子小故事/                ← 一个故事一个目录
        ├── index.html            ← ⭐ 最终产物：双击即可看，单文件 2-3MB
        ├── captions.json         ← 配文 / 章节配置，可编辑
        ├── comics/               ← 抠出来的漫画格，作为 build 的源
        ├── background/           ← 这次用到的水印图
        └── source_screenshots/   ← 原始截图（Snipaste），方便回溯
```

## skill 是干什么的

`comic-story-builder` 让 Claude（或我自己）以零交互的方式，把一组漫画截图变成一个可挂载的单文件网页。流程：

1. 抠图：自动检测每张截图里的漫画格，裁剪到 `comics/`
2. 归类：根据截图里可见的章节标题，把 panels 分到对应章节
3. 配文：Claude 看每张漫画格的画面，用**自己的话**写一句简短中英描述（不抄出版书里的对白和翻译 —— SKILL.md 里硬要求）
4. 烘焙：把 captions + 所有图片（base64）+ 水印图 全部内联进单个 `index.html`
5. 验证：用浏览器无头模式打开 `file://` 链接截图确认

最终产物是一个完全自包含的 `index.html`，没有外链文件、没有依赖（拼音库从 CDN 加载，那是唯一的网络依赖），可以：
- 双击本地打开
- 发邮件 / U盘 / 上传服务器，单文件即可

## 怎么装 skill

**方法 1：装到 Claude Code 全局 skills 目录**

```
mkdir -p "$HOME/.claude/skills"
cp -r skill/comic-story-builder "$HOME/.claude/skills/"
```
重启 Claude Code，让它扫到。

**方法 2：用 `.skill` 安装包**

在 Claude Code 里跑：
```
/plugin install
```
选 "From file"，指到 `skill/comic-story-builder.skill`。

装完之后，下次跟 Claude 说类似的话就会自动触发：
> 把 `<某目录>` 里的截图做成给孩子看的网页，标题《XXX》

skill 会按上面的 5 步跑完，生成单文件 HTML，告诉你在哪。

## 怎么看故事

最简单 —— **直接双击** `story/<故事名>/index.html`，会在默认浏览器里打开。

也可以挂到任何静态服务器（GitHub Pages / Vercel / 自家 NAS），把对应 `<story>/index.html` 上传即可（其它文件夹是源文件，发布时不需要）。

## 加新故事

```
# 1. 把新截图放到任意目录，比如 ~/Documents/family/0610
# 2. 让 Claude 调 skill 生成（或者手动跑）：
python skill/comic-story-builder/crop_panels.py ~/Documents/family/0610
# 3. 把生成的目录拷到 story/ 下：
mv ~/Documents/family/0610 story/<新故事名>/
```

或者直接让 Claude 帮你做整套，包括拷到本仓里。

## 编辑已有故事

```
# 1. 改 story/<故事名>/captions.json 里的配文
# 2. （可选）替换 story/<故事名>/background/ 里的水印图
# 3. 重新 build：
python skill/comic-story-builder/crop_panels.py "story/<故事名>" --rebuild
# 4. 刷新浏览器或重新双击 index.html
```

## 关于配文 / IP

SKILL.md 里写死了一条：**配文不抄出版社的翻译**，Claude 会用自己的话描述每一格画里发生的事。如果你想要原书的精确对白，编辑 `captions.json` 自己换上去就行 —— Claude 不会替你抄。

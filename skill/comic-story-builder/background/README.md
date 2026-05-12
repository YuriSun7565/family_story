# background/ — 给 viewer 用的水印背景图池

往这里放任意几张 `.jpg` / `.jpeg` / `.png` / `.webp`。

跑 `crop_panels.py` 的时候，这个目录会被整体拷到故事目录里，
并自动生成一份 `background/manifest.json` 列出文件名。

`viewer.html` 渲染每一页时会从这份名单里挑一张做半透明水印，
铺在整张页面背后（用 CSS opacity / blur 处理过）。

## 怎么挑？

按页索引做个稳定哈希 —— **同一页每次打开都是同一张背景**，
但相邻几页之间的背景会换，看上去像随机分布。
（不是真随机：那样翻页会闪、孩子会分心。）

## 想换图？

1. 直接把新图扔进这个目录（或者扔进故事目录的 `background/`）
2. 跑 `python crop_panels.py <story_dir> --refresh-bg`
3. 浏览器刷新

## 想关掉水印？

把故事目录的 `background/` 清空（或删掉 `manifest.json`），
viewer 找不到图就自动不显示水印。

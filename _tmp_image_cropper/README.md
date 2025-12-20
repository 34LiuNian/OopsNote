# 临时图片裁剪工具（Pillow）

一个轻量的命令行图片裁剪脚本：支持按像素框裁剪、按归一化比例框裁剪、居中裁剪、按固定宽高比做最大化居中裁剪。

## 依赖

- Python 3
- Pillow（你说全局大概已安装）

## 用法

### 1) 按像素框裁剪

```bash
python crop.py input.jpg --box 100 80 900 680 -o out.jpg
```

`--box left top right bottom`（单位：像素，右/下为开区间边界，符合 Pillow 的 box 约定）。

### 2) 按比例框裁剪（0~1）

```bash
python crop.py input.jpg --boxf 0.1 0.1 0.9 0.9 -o out.jpg
```

`--boxf` 会按当前图片宽高换算到像素。

### 3) 居中裁剪到指定尺寸

```bash
python crop.py input.jpg --center 512 512
```

默认输出文件名为 `input_cropped.jpg`。

### 4) 按固定宽高比做“最大化居中裁剪”

比如裁成 16:9：

```bash
python crop.py input.jpg --aspect 16 9
```

这会在不拉伸的前提下，从中心裁出尽可能大的 16:9 区域。

## 说明

- 会自动处理 EXIF 方向（拍照图片常见的旋转信息）。
- JPEG 保存默认 `quality=95`、`optimize=True`。

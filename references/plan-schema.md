# 剪辑计划 JSON

`scripts/build_mixcut_drafts.py` 接收一个 UTF-8 JSON 文件。

## 顶层字段

| 字段 | 必填 | 说明 |
|---|---:|---|
| `reference_video` | 是 | 参考视频本地绝对路径，不接受 `smb://` URI |
| `drafts_root` | 否 | 剪映草稿根目录；省略时由 JyWrapper 自动探测 |
| `output_dir` | 否 | 生成 `build-manifest.json` 的目录，默认是计划文件同目录下的 `outputs` |
| `width` / `height` | 否 | 默认 1080×1920 |
| `duration` | 否 | 成片秒数；省略时读取参考视频时长 |
| `subtitles` | 否 | 原语言字幕数组 |
| `variants` | 是 | 至少一个版本，通常为三个 |

## 字幕字段

```json
{
  "start": 0.0,
  "end": 2.5,
  "text": "Original-language subtitle"
}
```

## 版本与镜头字段

```json
{
  "name": "产品_混剪_01_钩子",
  "theme": "测试痛点钩子",
  "segments": [
    {
      "start": 0.0,
      "end": 2.5,
      "source": "/absolute/path/to/hook.mp4",
      "source_start": 1.2,
      "origin": "素材库"
    },
    {
      "start": 2.5,
      "end": 8.0,
      "source": "reference",
      "origin": "参考视频"
    }
  ]
}
```

- `start`、`end`：镜头在目标时间线上的秒数。
- `source`：使用 `reference` 表示参考视频，否则必须是本地绝对路径。
- `source_start`：素材内部起始秒数。参考视频省略时默认与目标时间线起始秒数相同；替换素材省略时默认从 0 秒开始。
- `origin`：报告标签，建议使用 `参考视频` 或 `素材库`。
- 每个版本的镜头必须从 0 秒连续覆盖到成片结尾，不能有空洞或重叠。

完整示例见 `examples/plan.example.json`。


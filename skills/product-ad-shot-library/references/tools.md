# 本地工具与清单格式

`scripts/shot_tools.py` 只提供技术辅助：候选切点、联系表、审核计划裁剪。不会理解画面、自动分类或预测 CTR，不是完整全自动流水线。

需要 Python 3、PATH 中的 ffmpeg（或用全局 `--ffmpeg` 指定），联系表另需 Pillow。优先 ffprobe 获取元数据，可用全局 `--ffprobe` 指定；未安装时退回 ffmpeg 文本探测，收据元数据精度约百分之一秒。缺依赖时说明，不静默安装。

```bash
python3 scripts/shot_tools.py inspect --source /absolute/path/video.mp4 --output /absolute/path/work/inspection.json
python3 scripts/shot_tools.py contact --source /absolute/path/video.mp4 --output /absolute/path/work/contact.jpg --start 0 --end 12 --count 9
python3 scripts/shot_tools.py export --plan /absolute/path/reviewed-plan.json --output /absolute/path/library
```

以实际 skill 路径定位脚本，先看 `--help`。代理负责递归扫描、日期筛选、缓存、语义审核与报告。长视频分段采样，防止联系表稀疏漏镜头。

计划是 JSON 数组，例如：

```json
[{"clip_id":"V0001_S001","source":"/absolute/path/video.mp4","start":1.2,"end":6.8,"category":"05_搓泥演示/手臂","review_method":"manual_keyframes","review_notes":"查看1.3、3.5、6.5秒，未完整播放","needs_recut":false}]
```

计划须经过视觉判断。分类为相对目录不能含 `..`，编号限字母数字下划线短横线。工具拒绝覆盖、源目录内输出、越界时间及未知审核方式。需保留复合段时标 needs_recut，不代表已拆好。

导出 H.264/AAC，保留可用音轨和原画幅；新编码非字节无损。导出后完整解码检查、核对时长（容差 max(0.15秒, 2/源帧率)），逐条生成 receipt JSON 并保留审核字段。单条失败即停止，保留已完成收据；恢复时检查完成项并生成仅含未完成项的新计划，不覆盖重跑。

已有素材整理不调用 export，先保存清单和路径映射再迁移，核对大小或哈希；技术通过和语义通过分别汇报。

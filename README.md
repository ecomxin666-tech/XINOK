# JianYing TikTok Mixcut Skill

一个面向剪映专业版的 Codex skill：从参考短视频和分类素材库中拆解口播与分镜，保留完整原音轨，并生成三个受控变量的混剪草稿。默认只保存草稿，不导出。

## 能做什么

- 选择并拆解参考视频
- 转写原语言口播并生成中文翻译报告
- 设计钩子、护理过程、产品质感等三版受控测试
- 完整保留参考视频口播和背景音
- 按 JSON 计划生成 Mac/Windows 剪映草稿
- 输出逐镜头来源与替换比例清单
- 接收 TikTok 发布数据，形成下一轮优化规则

## 依赖

- Python 3.9+
- 剪映专业版
- 已安装的 `jianying-editor` skill
- `imageio-ffmpeg`

## 安装

从本仓库直接安装到 Codex skills 目录：

```bash
git clone https://github.com/ecomxin666-tech/XINOK.git ~/.codex/skills/jianying-tiktok-mixcut
```

私有仓库需要先在终端配置 GitHub 登录；也可以下载 ZIP 后，将解压目录重命名为 `jianying-tiktok-mixcut` 并放入 `~/.codex/skills/`。

重新启动 Codex 后，可以使用：

```text
使用 $jianying-tiktok-mixcut，根据参考视频和素材目录生成三版剪映草稿，保留原口播，保存但不导出。
```

## 使用配置脚本

复制示例计划并替换为本机已经挂载的绝对路径：

```bash
cp examples/plan.example.json plan.json
python scripts/build_mixcut_drafts.py plan.json --validate-only
python scripts/build_mixcut_drafts.py plan.json
```

同名草稿默认不会覆盖。只有确认可以覆盖时才执行：

```bash
python scripts/build_mixcut_drafts.py plan.json --overwrite
```

## 隐私

不要提交真实视频、客户素材、转写内容、剪映草稿、公司共享盘地址、账号信息、Cookie、Token 或 API Key。仓库中的示例路径和数据均应保持虚构。

## 目录

```text
jianying-tiktok-mixcut/
├── SKILL.md
├── agents/openai.yaml
├── scripts/build_mixcut_drafts.py
├── references/
│   ├── workflow.md
│   ├── plan-schema.md
│   └── feedback-loop.md
└── examples/plan.example.json
```

## License

MIT

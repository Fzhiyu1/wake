# wake

> 把整个个人知识库灌进长上下文 LLM,作为"形状记忆"——不存事件,只存形状。回忆是重构,不是检索。

## 这是什么

传统记忆系统 = 向量检索 + RAG。**wake 不是检索,是注入**:把你整个 markdown 知识库(几百 KB - 几 MB)一次性塞进 DeepSeek 1M context 的 system prompt,触发 prompt cache,每次提问让模型按"被 KB 塑型过的 substrate"输出**联想**——不是回答问题,是给出"这个问题在你的 KB 上激活了什么"。

为什么这样做能工作:

1. **DeepSeek 的 1M context + prompt cache** 让"全量注入"在经济和延迟上都可行(单次召回 ¥0.001 量级)
2. **注意力本身就是有损压缩** —— 把整个 KB 都给模型,模型自己决定哪部分浮起来,这比 top-k 余弦检索更接近"人脑想起一件事"
3. **substrate 被塑型** —— 同一个 query 在不同 KB 下激活完全不同的"记忆"。KB 是 substrate,不是数据库

详见 wake 作者的知识库快照:`kb-snapshot.txt` (这就是 demo;同时也是这套方法论的 dogfood)。

## 架构

```
你的 markdown 知识库 (Obsidian / 任何 .md 目录)
    ↓ build_snapshot.sh
kb-snapshot.txt (单个文件,约几百 KB)
    ↓ 注入 system prompt
DeepSeek 1M context (prompt cache 命中)
    ↓ query → recall(query) 返回联想式片段
    ↓
三种集成路径任选:
  1. lens 插件     ── 每次请求自动注入 (最深度集成)
  2. MCP 工具      ── 模型按需主动调用 (最克制)
  3. shell hook    ── Claude Code UserPromptSubmit (最轻量)
```

## 快速开始

```bash
git clone https://github.com/Fzhiyu1/wake.git
cd wake
python3 -m venv .venv
.venv/bin/pip install openai                    # daemon / mcp / hook 必须
.venv/bin/pip install fastapi uvicorn httpx     # 如果要用集成 A (lens 代理)
cp .env.example .env
# 填入 DEEPSEEK_API_KEY,从 https://platform.deepseek.com/ 拿
```

试一次召回:

```bash
.venv/bin/python3 daemon.py "怎么判断 AI 在幻觉"
```

应该看到几行带 `[[wikilink]]` 的"联想式"输出,而不是百科全书答案。如果输出像答题,检查是否在用 demo 的 `kb-snapshot.txt`(下方"换成你自己的 KB"一节)。

## 三种集成方式

### A. lens 代理(每次对话自动注入,推荐)

`lens/` 是仓库内置的 Anthropic API 代理,自带 `wake_memory` 插件——直接启动:

```bash
.venv/bin/pip install fastapi uvicorn httpx     # 一次性
.venv/bin/python3 lens/proxy.py
```

客户端切到代理:

```bash
unset HTTP_PROXY HTTPS_PROXY
export ANTHROPIC_BASE_URL=http://localhost:8765
export NO_PROXY=localhost,127.0.0.1
claude  # 或 cursor / 任何用 Anthropic API 的客户端
```

每次发消息,lens 拦截 → 调 wake 召回 → 把 `[当前相关记忆]` 块塞进 system → 转发给 Anthropic。最深度的"形状被塑型"形态。

如果你在中国大陆访问 api.anthropic.com 需要走代理:

```bash
LENS_UPSTREAM_PROXY=http://your-proxy:port .venv/bin/python3 lens/proxy.py
```

`lens/plugins/examples/` 里有两个 hello-world 插件(`echo`、`system_prefix`),可以参考着写自己的。

### B. 注册成 MCP 工具(模型按需主动调用)

`~/.claude.json` 里加:

```json
{
  "mcpServers": {
    "wake": {
      "command": "/path/to/wake/.venv/bin/python3",
      "args": ["/path/to/wake/mcp_server.py"],
      "type": "stdio"
    }
  }
}
```

模型会在判断"用户提到他过去想过的东西"时主动调 `memory_recall`。代价:模型可能不调,但调用很精准。

### C. UserPromptSubmit hook(最轻量,无 lens 依赖)

`~/.claude/settings.json` 里加:

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "hooks": [{"type": "command", "command": "/path/to/wake/hook.sh"}]
    }]
  }
}
```

每次发消息时把 wake 召回结果以 `[记忆] ...` 形式 stdout 注入。Claude Code 把它当 hook 输出。

## 换成你自己的 KB

仓库里的 `kb-snapshot.txt` 是 wake 作者的知识库快照(~600KB)——既是教学 demo,也是"形状记忆能产出什么"的实证样本。

替换成你自己的:

```bash
# 1. 改 build_snapshot.sh 里的 KB 路径
vi build_snapshot.sh
#   把 KB="/path/to/knowledge-base" 指向你的笔记目录

# 2. 重建快照
./build_snapshot.sh

# 3. 改 system-prompt.md(可选但强烈推荐)
#    里面的 example queries / KB 概念命名风格是为某一份 KB 调的,
#    换 KB 后建议至少替换 4-5 个示例,否则 wake 召回质量会打折
```

KB 结构推荐(不强制):

```
your-kb/
├── 1-concepts/        ← 原子概念卡(一卡一念)
├── 2-explorations/    ← 长对话整理
├── 3-projects/        ← 在做的事
├── 4-references/      ← 外部资料笔记
├── INDEX.md           ← 一卡一行 + summary(可选,但能大幅提升召回)
└── CLUSTERS.md        ← 主题聚类(可选)
```

任何能转成 markdown 的笔记系统都可以(Obsidian、Logseq、纯文件夹)。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | (必填) | 从 platform.deepseek.com 申请 |
| `WAKE_OWNER` | (空) | KB 归属人名字,影响 MCP 工具描述里的措辞 |
| `WAKE_TIMEOUT` | `15` | daemon 调用超时(秒) |
| `LENS_PORT` | `8765` | lens 监听端口 |
| `LENS_UPSTREAM` | `https://api.anthropic.com` | lens 上游 API |
| `LENS_UPSTREAM_PROXY` | (空) | lens 上游代理(中国大陆通常需要) |
| `LENS_PLUGINS` | `wake_memory` | 启用的插件,逗号分隔 |

## 文件说明

| 路径 | 角色 |
|---|---|
| `daemon.py` | 召回入口。`recall(query) -> str`,也能直接命令行调用 |
| `system-prompt.md` | 注入给 DeepSeek 的 system prompt,定义"联想"输出风格 |
| `kb-snapshot.txt` | KB 序列化产物,daemon 启动时一次性载入 |
| `build_snapshot.sh` | 从 markdown 目录重建 kb-snapshot.txt |
| `mcp_server.py` | 把 daemon 包装成 MCP stdio server |
| `hook.sh` | Claude Code UserPromptSubmit hook |
| `lens/proxy.py` | 内置 Anthropic API 代理(集成 A 用) |
| `lens/plugins/wake_memory.py` | lens 默认插件,负责拦截请求 + 注入记忆 + 剥旧累积 |
| `lens/plugins/examples/` | hello-world 插件示例(`echo`、`system_prefix`),写自己插件的起点 |

## 是不是 RAG?

**不是**。RAG 是把 KB 切片 + 向量化 + 检索 top-k + 拼到 prompt 里。
wake 是把 KB 整个塞进 system prompt,不切片、不向量化、不检索——靠模型自己的注意力做"自然有损压缩"。

|   | RAG | wake |
|---|---|---|
| KB 量级 | GB 级、文档级 | KB 到几 MB,概念级 |
| 召回风格 | 引用原文 | 联想浮现(可能不点名出处) |
| 适合 | 客服、检索、知识查询 | 个人思考记忆、第二大脑、写作助手 |
| 单次成本 | ~10K token | ~150K-1M token,但 prompt cache 后接近 RAG |

如果你的 KB > 几 MB,wake 就不合适了——这是个人 KB 工具,不是企业知识库方案。

## 灵感来源

- DeepSeek 1M context + prompt cache 让"全量注入"在 2026 变得可行
- "记忆 ≠ 检索,是 substrate 对新输入的形状响应"——wake 作者 2026-05-02 的 KB 笔记
- Madeleine cookie / 双过程理论 / 自由能原理:浮现 vs 主动检索的二元结构

完整方法论在 `kb-snapshot.txt` 里,搜 `多层有损压缩` `失败可见性` `塑型源的多样性` 等概念。

## 限制

- 必须有 DeepSeek API key(模型可换,改 `daemon.py` 里 base_url 即可——但 1M context 是关键依赖)
- 单次召回 1-3 秒(daemon 冷启动 + DeepSeek 推理),lens 集成时每次对话延迟 +1-3s
- KB 改了要手动跑 `build_snapshot.sh`(可以挂 git post-commit hook)
- 召回质量强依赖 system-prompt.md 的调教,以及 KB 本身的概念结构。空 KB 或纯流水账 KB 出不来"联想"

# novel-agent

基于 LLM 的小说续写与问答工具，支持世界观按章快照、事件时间线追踪（BM25 + 向量 + 实体匹配三路混合检索）、近章摘要管理、多小说并行更新。

## 环境要求

- Python 3.10+
- 可访问的 OpenAI 兼容 API（如 vLLM、Ollama）

## 安装与启动

```bash
cd novel-agent
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # 编辑 .env 填入你的 LLM 配置
python -m uvicorn app.main:app --host 0.0.0.0 --port 7860
```

打开浏览器访问 `http://localhost:7860`。

## 配置

通过 `.env` 文件或环境变量配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_BASE` | LLM API 地址 | `http://localhost:8000/v1` |
| `LLM_API_KEY` | API Key（本地 vLLM 可填 `not-needed`） | `not-needed` |
| `LLM_MODEL` | 模型名 | `your-model-name` |
| `LLM_MAX_TOKENS` | 最大生成 token 数 | `4096` |
| `LLM_CONTEXT_WINDOW` | 上下文窗口大小 | `128000` |

## 目录结构

```
novel-agent/
├── app/
│   ├── config.py                 # 应用配置（读取 .env）
│   ├── main.py                   # FastAPI 入口
│   ├── routers/                  # API 路由（chat, memory, novel）
│   ├── agents/                   # 多 Agent 协作（writer, planner, critic 等）
│   └── services/
│       ├── llm_service.py        # LLM 调用（OpenAI 兼容）
│       ├── memory_service.py     # 记忆读写（世界观/时间线/实体索引）
│       ├── novel_service.py      # 小说管理
│       ├── context_builder.py    # 上下文组装
│       ├── embedding_service.py  # 向量嵌入（bge-small-zh-v1.5）
│       ├── timeline_retriever.py # 三路混合检索
│       └── txt_parser.py         # TXT 小说智能章节切分
├── static/                       # 前端（HTML + CSS + JS）
├── models/                       # 嵌入模型缓存（首次运行自动下载）
├── user_data/                    # 用户数据（自动创建）
├── sample/                       # 格式示例参考
└── tests/                        # 测试
```

## 运行测试

```bash
python -m pytest tests/ -v
```

## 功能

- **续写模式**：基于上下文 LLM 续写小说（流式逐字显示）
- **提问模式**：针对小说内容进行问答
- **自由聊天**：不关联小说，纯 LLM 对话
- **TXT 上传**：支持直接上传 .txt 小说，自动识别章节格式并切分
- **记忆系统**：世界观按章快照、时间线事件提取、实体倒排索引、近章摘要
- **三路混合检索**：BM25 + 向量 + 实体匹配，RRF 融合
- **多 Agent 协作**：Writer / Planner / Critic / Chief Editor 分工写作
- **并行更新**：不同小说可同时更新记忆
- **断点续传**：记忆更新支持中断后继续
- **删除回滚**：删除最近一章时自动回退记忆

## License

MIT

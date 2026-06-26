# Hermes Engine

> 具备自进化能力的多功能 AI Agent 后端 — Feature-based FastAPI + REST + WebSocket + SSE
> A multi-capability AI Agent backend with self-evolution — rebuilt from NousResearch Hermes Agent

[![CI](https://github.com/eafenzhang/hermes-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/eafenzhang/hermes-engine/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![mypy](https://img.shields.io/badge/mypy-0%20errors-green)](https://mypy-lang.org/)
[![tests](https://img.shields.io/badge/tests-241%20passed-brightgreen)](https://github.com/eafenzhang/hermes-engine/actions/workflows/ci.yml)
[![coverage](https://img.shields.io/badge/coverage-%E2%89%A575%25-yellow)](https://github.com/eafenzhang/hermes-engine/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

---

## 概述 / Overview

**Hermes Engine** 是一个面向 AI Agent 的生产级后端服务，基于 [NousResearch Hermes Agent](https://github.com/NousResearch/hermes-agent) 核心能力重构。支持 **15+** AI Provider、持久化记忆（SQLite FTS5）、自我进化（Skill 自动生成/修补 + Memory 合成 + Curator 分级淘汰）、有状态多轮对话、MCP 工具桥接，并通过 REST API、SSE 流和 WebSocket 事件对外暴露。

**Hermes Engine** is a production-grade backend service for AI agents. Supports **15+** AI providers, persistent memory (SQLite FTS5), self-evolution (Skill auto-generation/patching + Memory synthesis + Curator grading), stateful multi-turn conversations, MCP tool bridging, and exposes everything via REST, SSE, and WebSocket.

---

## 核心能力 / Core Capabilities

### 自我进化 / Self-Evolution

| 能力 Capability | 描述 Description |
|----------------|-----------------|
| **Memory Curator** | LLM 语义合并 + 使用统计分级淘汰（active → stale → archived） |
| **Skill Auto-Create** | 复杂多工具任务（≥5 tool calls）自动生成可复用 SKILL.md |
| **Skill Patching** | 精确 `old_string/new_string` 修补，Skill 在使用中自我优化 |
| **Memory Synthesis** | 每轮对话自动提取摘要写入长期记忆 |
| **Context Builder** | 自动注入相关记忆 + Skill + MEMORY.md/USER.md 到系统提示 |
| **Context Compression** | 长对话中间轮次 Lossy 摘要，防止 Token 溢出 |
| **Cross-Session Recall** | FTS5 搜索历史对话，跨 Session 上下文注入 |

### 功能 / Features

| 功能 Feature | 描述 Description |
|-------------|-----------------|
| **AI Agent** | 多 Provider 对话 + 工具调用 + SSE 流式响应 + 上下文压缩 |
| **Memory** | SQLite FTS5 + LLM 驱动语义记忆 + Curator 自动归档 + 使用统计 |
| **Conversation** | 有状态多轮对话 (`conversation_id`) + `/api/sessions/{id}/chat` |
| **Skills** | 文件系统 Skill + 自动生成 + 精确修补 + LLM 语义匹配 |
| **MCP Bridge** | 连接外部 MCP 服务器，聚合远程工具，健康检查 + 超时保护 |
| **Event Bus** | WebSocket 实时广播 + Redis pub/sub 跨实例 fan-out |
| **Cron Scheduler** | 自然语言 Cron 解析 ("每天下午3点" → `0 15 * * *`) + REST CRUD |
| **Sub-Agent** | 隔离子 Agent 委托 + `asyncio.gather` 并行执行 |
| **Plugin System** | 三源发现: `~/.hermes-engine/plugins/` / `.hermes-engine/plugins/` / pip entry points |
| **Gateway** | Webhook 适配器框架，支持多平台接入 |
| **Trajectory Export** | ShareGPT JSONL 格式轨迹导出 |

---

## AI Providers

### 国际 / International

| Provider | 协议 | 说明 |
|----------|------|------|
| **Anthropic** | Native Messages API | 官方 + 自定义代理 (可配 `base_url`) |
| **OpenAI** | Chat Completions | 官方 + 自定义 `base_url` |
| **Google Gemini** | Native GenerateContent | 官方 API |
| **Anthropic Compat** | Messages API | 自定义 Anhtropic 兼容网关/代理 |

### 国内 / Chinese (OpenAI-compatible)

| Provider | Base URL | 模型 |
|----------|----------|------|
| **DeepSeek (深度求索)** | `api.deepseek.com/v1` | deepseek-chat, deepseek-reasoner |
| **Moonshot/Kimi (月之暗面)** | `api.moonshot.cn/v1` | moonshot-v1-8k/32k/128k, kimi-* |
| **Zhipu AI (智谱)** | `open.bigmodel.cn/api/paas/v4` | glm-4, glm-4-flash, chatglm-* |
| **Qwen/通义千问 (阿里云)** | `dashscope.aliyuncs.com/compatible-mode/v1` | qwen-turbo, qwen-plus, qwen-max |
| **Xiaomi Mimo (小米)** | 需配置 | mimo-* |
| **MiniMax (稀宇科技)** | `api.minimax.chat/v1` | abab6.5s-chat, abab6.5s-pro |

### 自动路由 / Auto-Routing

`/v1/chat/completions` 端点根据模型名自动选择 Provider：

| 模型前缀 | → Provider |
|---------|-----------|
| `claude-*` | anthropic |
| `gpt-*`, `o1-*` | openai |
| `gemini-*` | gemini |
| `deepseek-*` | deepseek |
| `moonshot-*`, `kimi-*` | moonshot |
| `glm-*`, `chatglm-*` | zhipu |
| `qwen-*` | qwen |
| `mimo-*` | xiaomi |
| `abab-*`, `minimax-*` | minimax |
| `ac-*` | anthropic_compat |

---

## 架构 / Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         FastAPI App                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────┐ │
│  │  Agent   │ │  Memory  │ │Conversat.│ │  Skill   │ │  MCP  │ │
│  │  Router  │ │  Router  │ │  Router  │ │  Router  │ │ Router│ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬───┘ │
│  ┌────┴────────────┴────────────┴────────────┴───────────┴────┐ │
│  │                    Self-Evolution Layer                     │ │
│  │  Context Builder │ Compressor │ Memory Synth │ Skill Gen   │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Execution Layer                          │ │
│  │  Terminal (local/docker/ssh) │ Browser (fetch/search)       │ │
│  │  Sub-Agent Pool │ Cron Scheduler │ Plugin Loader           │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Infrastructure                           │ │
│  │  Provider Registry │ Event Bus │ Gateway │ Trajectory      │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## 快速开始 / Quick Start

### 前置要求 / Prerequisites

- Python 3.11+
- [可选/optional] API Key: Anthropic / OpenAI / DeepSeek / ...

### 安装 / Installation

```bash
git clone https://github.com/eafenzhang/hermes-engine.git
cd hermes-engine
pip install -e ".[dev]"
```

### 运行 / Run

```bash
# 默认 127.0.0.1:8080
python run.py

# 调试模式 + 国内 Provider
HERMES_DEEPSEEK_API_KEY=sk-xxx \
HERMES_MOONSHOT_API_KEY=sk-xxx \
python run.py --debug

# Docker 一键启动
docker compose up -d

# 带 Redis 事件总线（多实例）
docker compose --profile redis up -d
```

---

## API 一览 / API at a Glance

### Agent & Chat

| Method | Endpoint | 说明 Description |
|--------|----------|-----------------|
| `POST` | `/api/agent/chat` | Agent 对话 (支持 `conversation_id` 多轮) |
| `POST` | `/api/agent/chat/stream` | Agent 对话 (SSE 流式) |
| `POST` | `/api/sessions/{id}/chat` | 有状态多轮对话（自动加载/持久化历史） |
| `POST` | `/api/sessions/{id}/chat/stream` | 有状态多轮流式对话 |
| `GET` | `/api/sessions` | 列出所有会话 |
| `POST` | `/v1/chat/completions` | OpenAI 兼容 Chat Completions |

### Memory & Conversation

| Method | Endpoint | 说明 Description |
|--------|----------|-----------------|
| `GET/POST` | `/api/memories` | 记忆 CRUD + FTS5 搜索 |
| `POST` | `/api/memories/curator/run` | 运行记忆整理 (`?use_llm=true`) |
| `GET` | `/api/memories/curator/state` | 查看 Curator 状态 |
| `GET/POST` | `/api/conversations` | 对话管理 |

### Skills

| Method | Endpoint | 说明 Description |
|--------|----------|-----------------|
| `GET/POST` | `/api/skills` | Skill CRUD |
| `PATCH` | `/api/skills/{name}` | 精确修补 Skill (old_string/new_string) |
| `POST` | `/api/skills/scan` | 扫描 Skill 目录 |
| `POST` | `/api/skills/match` | Skill 匹配 (关键词 + LLM 语义) |

### Tools & Execution

| Method | Endpoint | 说明 Description |
|--------|----------|-----------------|
| `GET` | `/api/tools` | 内置工具列表 (5 tools) |
| `POST` | `/api/tools/execute` | 执行工具 |

### MCP

| Method | Endpoint | 说明 Description |
|--------|----------|-----------------|
| `GET/POST` | `/api/mcp/servers` | MCP 服务器管理 |
| `GET` | `/api/mcp/servers/{name}/health` | 单个健康检查 |
| `GET` | `/api/mcp/health` | 批量探测 |

### Models & Providers

| Method | Endpoint | 说明 Description |
|--------|----------|-----------------|
| `GET` | `/api/providers` | Provider 列表 |
| `GET` | `/api/providers/models` | 列出所有模型 (TTL 缓存) |
| `POST` | `/api/providers/models/refresh` | 强制刷新模型缓存 |

### Cron & Trajectories

| Method | Endpoint | 说明 Description |
|--------|----------|-----------------|
| `GET/POST` | `/api/cron` | Cron 任务管理 |
| `POST` | `/api/cron/parse` | 自然语言 → Cron 表达式 |
| `POST` | `/api/trajectories/export` | ShareGPT 格式导出 |

### Gateway & System

| Method | Endpoint | 说明 Description |
|--------|----------|-----------------|
| `POST` | `/api/gateway/webhook` | 通用 Webhook 入口 |
| `GET` | `/api/health` | 健康检查 |
| `WS` | `/ws?token=xxx` | WebSocket 事件订阅 |

---

## 配置 / Configuration

### 通用 / General

| 环境变量 Env | 默认 Default | 说明 Description |
|-------------|-------------|-----------------|
| `HERMES_HOST` | `127.0.0.1` | 监听地址 |
| `HERMES_PORT` | `8080` | 监听端口 |
| `HERMES_DEBUG` | `false` | 调试模式 |
| `HERMES_DATA_DIR` | `~/.hermes-engine` | 数据目录 |
| `HERMES_API_TOKEN` | (空) | 认证 Token (空=本地模式) |
| `HERMES_CORS_ORIGINS` | `*` | CORS 允许源（多值用逗号分隔） |

### Provider API Keys

| 环境变量 Env | 说明 Description |
|-------------|-----------------|
| `HERMES_ANTHROPIC_API_KEY` | Anthropic API Key |
| `HERMES_ANTHROPIC_BASE_URL` | Anthropic 自定义代理 (可选) |
| `HERMES_OPENAI_API_KEY` | OpenAI API Key |
| `HERMES_OPENAI_BASE_URL` | OpenAI 自定义 Base URL |
| `HERMES_GEMINI_API_KEY` | Google Gemini API Key |
| `HERMES_ANTHROPIC_COMPAT_API_KEY` | Anhtropic 兼容 Provider Key |
| `HERMES_ANTHROPIC_COMPAT_BASE_URL` | Anhtropic 兼容 Provider URL |
| `HERMES_ANTHROPIC_COMPAT_MODEL` | 连通性检查用模型 |
| `HERMES_DEEPSEEK_API_KEY` | DeepSeek API Key |
| `HERMES_MOONSHOT_API_KEY` | Moonshot/Kimi API Key |
| `HERMES_ZHIPU_API_KEY` | 智谱 GLM API Key |
| `HERMES_QWEN_API_KEY` | 通义千问 API Key |
| `HERMES_XIAOMI_API_KEY` | 小米 Mimo API Key |
| `HERMES_XIAOMI_BASE_URL` | 小米 Mimo Base URL (必填) |
| `HERMES_MINIMAX_API_KEY` | MiniMax API Key |

### 执行层 / Execution

| 环境变量 Env | 默认 Default | 说明 Description |
|-------------|-------------|-----------------|
| `HERMES_TERMINAL_BACKEND` | `local` | 终端后端: `local` / `docker` / `ssh` |
| `HERMES_DOCKER_IMAGE` | `python:3.12-slim` | Docker 容器镜像 |
| `HERMES_SSH_HOST` | (空) | SSH 主机 |
| `HERMES_SSH_USER` | (空) | SSH 用户 |
| `HERMES_SSH_KEY_PATH` | (空) | SSH 私钥路径 |
| `HERMES_SSH_PORT` | `22` | SSH 端口 |
| `HERMES_EXTRA_ALLOWED_COMMANDS` | `[]` | 额外命令白名单 |
| `HERMES_MCP_TIMEOUT` | `30.0` | MCP 超时 (秒) |

### 自我进化 / Self-Evolution

| 环境变量 Env | 默认 Default | 说明 Description |
|-------------|-------------|-----------------|
| `HERMES_CURATOR_ENABLED` | `true` | 启用 Curator |
| `HERMES_CURATOR_INTERVAL_MESSAGES` | `10` | 自动触发间隔 |
| `HERMES_CURATOR_PROVIDER` | `anthropic` | Curator 使用的 Provider |
| `HERMES_CURATOR_GRADING_ENABLED` | `true` | 使用统计分级淘汰 |
| `HERMES_CURATOR_STALE_DAYS` | `30` | 进入 stale 状态天数 |
| `HERMES_CURATOR_ARCHIVE_DAYS` | `90` | 进入 archived 状态天数 |
| `HERMES_CONTEXT_COMPRESSION_ENABLED` | `true` | 启用上下文压缩 |
| `HERMES_CONTEXT_MAX_CHARS` | `60000` | 压缩触发字符数 |
| `HERMES_CONTEXT_KEEP_LAST_MESSAGES` | `6` | 保留最近 N 条 |
| `HERMES_SKILL_AUTO_CREATE_ENABLED` | `true` | 自动生成 Skill |
| `HERMES_SKILL_AUTO_CREATE_MIN_TOOL_CALLS` | `5` | 触发最少工具调用数 |
| `HERMES_USER_CONTEXT_ENABLED` | `true` | 加载 MEMORY.md/USER.md |

### 基础设施 / Infrastructure

| 环境变量 Env | 默认 Default | 说明 Description |
|-------------|-------------|-----------------|
| `HERMES_EVENT_BACKEND` | `memory` | 事件后端: `memory` / `redis` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `HERMES_SUBAGENT_TIMEOUT` | `300.0` | 子 Agent 超时 (秒) |
| `HERMES_SUBAGENT_MAX_CONCURRENT` | `3` | 子 Agent 最大并发 |
| `HERMES_CRON_ENABLED` | `true` | 启用 Cron 调度 |
| `HERMES_GATEWAY_ENABLED` | `true` | 启用 Webhook 网关 |
| `HERMES_PLUGINS_ENABLED` | `true` | 启用插件系统 |
| `HERMES_PLUGINS_DIRS` | `[]` | 额外插件目录 |
| `HERMES_TRAJECTORIES_ENABLED` | `true` | 启用轨迹导出 |
| `HERMES_SESSION_ENABLED` | `true` | 启用有状态会话 |
| `HERMES_MODEL_CACHE_TTL` | `300.0` | 模型列表缓存 (秒) |
| `HERMES_BROWSER_ENABLED` | `true` | 启用浏览器工具 |

---

## 项目结构 / Project Structure

```
hermes-engine/
├── agent/                    # Agent 引擎 + 流式对话 + 自我进化集成
├── api_compat/               # OpenAI 兼容 /v1/chat/completions
├── config/                   # Pydantic Settings (~60+ 配置项)
├── conversation/             # 对话存储 + 服务 + 路由
├── gateway/                  # Webhook 网关适配器
├── mcp/                      # MCP Bridge + 路由
├── memory/                   # SQLite FTS5 + Curator (LLM 合并 + 分级淘汰)
├── provider/                 # 15+ AI Provider 适配器 + 注册中心
├── shared/                   # 共享基础设施
│   ├── context_builder.py    #   记忆/Skill/用户上下文注入
│   ├── context_compressor.py #   长对话 Lossy 摘要压缩
│   ├── memory_synthesizer.py #   对话→记忆自动提取
│   ├── scheduler.py          #   Cron 调度 + NL 解析
│   ├── scheduler_router.py   #   /api/cron 端点
│   ├── session_router.py     #   /api/sessions 有状态多轮
│   ├── subagent.py           #   隔离子 Agent 委托
│   ├── plugin.py             #   三源插件系统
│   ├── trajectory.py         #   ShareGPT 轨迹导出
│   ├── user_context.py       #   MEMORY.md/USER.md
│   ├── model_cache.py        #   模型列表 TTL 缓存
│   └── utils.py              #   公共工具 (flatten/extract_json)
├── skill/                    # Skill 发现/创建/修补/匹配
├── tools/                    # 内置工具 + 扩展
│   ├── builtin/              #   read_file/write_file/execute_command
│   ├── browser/              #   web_fetch/web_search
│   └── terminal_backends/    #   local/docker/ssh 终端后端
├── tests/                    # 241 个 Pytest 用例
├── Dockerfile                # 生产容器镜像 (+ Healthcheck)
├── docker-compose.yml        # 一键启动
├── main.py                   # FastAPI 入口 + 生命周期
├── pyproject.toml            # 项目配置
└── .github/workflows/ci.yml  # CI/CD
```

---

## 开发 / Development

### 测试 / Testing

```bash
pytest                         # 241 tests
python -m pytest --cov         # with coverage
mypy .                         # 0 errors (105 source files)
ruff check .                   # lint
```

### CI/CD

GitHub Actions: lint → typecheck → test (3.11/3.12/3.13) → coverage ≥75% → security scan.

---

## 安全 / Security

- **命令执行**：白名单 + 危险模式正则 + PATH 消毒 + Docker/SSH 隔离后端
- **文件访问**：限制在项目目录，符号链接验证
- **认证**：可选 Bearer Token (`HERMES_API_TOKEN`) + WebSocket Token
- **SQL 注入**：参数化查询 + WAL 模式
- **WebSocket**：Token 认证 (`/ws?token=...`)，非本地模式必须认证

---

## 许可证 / License

Apache 2.0 — 基于 NousResearch Hermes Agent 改编 / adapted from NousResearch Hermes Agent.

---

## 评分 / Quality Score

| 维度 Dimension | 评分 Score |
|---------------|-----------|
| 架构 Architecture | **A+** |
| 代码质量 Code Quality | **A** — mypy 0 errors, ruff clean |
| 安全性 Security | **A** — WS auth + Docker sandbox |
| 测试 Tests | **A** — 241 passed / coverage ≥75% |
| 工程化 Engineering | **A+** — Docker + Graceful Shutdown + Healthcheck |
| 自我进化 Self-Evolution | **A** — Skill auto-create/patch + Memory synthesis + Curator |
| Provider 覆盖 Provider Coverage | **A+** — 15+ providers (国际 + 国内) |
| **综合 Overall** | **A+** |

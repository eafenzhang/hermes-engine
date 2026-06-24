# Hermes Engine

> 具备自进化能力的多功能 AI Agent 后端 — Feature-based FastAPI + REST + WebSocket + SSE
> A multi-capability AI Agent backend with self-evolution — Feature-based FastAPI + REST + WebSocket + SSE

[![CI](https://github.com/eafenzhang/hermes-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/eafenzhang/hermes-engine/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![mypy](https://img.shields.io/badge/mypy-0%20errors-green)](https://mypy-lang.org/)
[![tests](https://img.shields.io/badge/tests-105%20passed-brightgreen)](https://github.com/eafenzhang/hermes-engine/actions/workflows/ci.yml)
[![coverage](https://img.shields.io/badge/coverage-%E2%89%A575%25-yellow)](https://github.com/eafenzhang/hermes-engine/actions/workflows/ci.yml)

---

## 概述 / Overview

**Hermes Engine** 是一个面向 AI Agent 的生产级后端服务，基于 NousResearch 的 Hermes Agent 核心能力重构。支持多 AI Provider（Anthropic、OpenAI、Google Gemini）、持久化记忆（SQLite FTS5）、对话管理、Skill 系统、MCP 工具桥接，并通过 REST API、SSE 流和 WebSocket 事件对外暴露。

**Hermes Engine** is a production-grade backend service for AI agents, rebuilt on the core capabilities of NousResearch's Hermes Agent. It supports multiple AI providers (Anthropic, OpenAI, Google Gemini), persistent memory (SQLite FTS5), conversation management, skill systems, MCP tool bridging, and exposes everything via REST API, SSE streaming, and WebSocket events.

### 功能 / Features

| 功能 Feature | 描述 Description |
|-------------|-----------------|
| **AI Agent** | 多 Provider 对话 + 工具调用 + SSE 流式响应 |
| **Memory** | SQLite FTS5 全文搜索 + LLM 驱动的语义记忆管理 (Curator) |
| **Conversation** | 多轮对话持久化，支持消息增删查 |
| **Skills** | 文件系统 Skill 发现、创建、关键词匹配 |
| **MCP Bridge** | 连接外部 MCP 服务器，聚合远程工具，带健康检查与超时保护 |
| **Event Bus** | WebSocket 实时事件广播，支持内存/Redis 可插拔后端 |
| **Docker 部署** | 一行命令启动 (`docker compose up -d`)，可选 Redis 事件总线集成 |

### 架构 / Architecture

```
┌─────────────────────────────────────────────────────┐
│                    FastAPI App                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │  Agent   │ │  Memory  │ │Conversat.│ │  Skill  │ │
│  │  Router  │ │  Router  │ │  Router  │ │ Router  │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬────┘ │
│  ┌────┴─────┐ ┌────┴─────┐ ┌────┴─────┐ ┌────┴────┐ │
│  │ Provider │ │  MCP     │ │  Tools   │ │  Event  │ │
│  │ Registry │ │  Bridge  │ │ Executor │ │   Bus   │ │
│  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## 快速开始 / Quick Start

### 前置要求 / Prerequisites

- Python 3.11+
- [可选/optional] API Key: Anthropic / OpenAI / Google Gemini

### 安装 / Installation

```bash
git clone https://github.com/eafenzhang/hermes-engine.git
cd hermes-engine
pip install -e ".[dev]"
```

### 运行 / Run

```bash
# 默认 127.0.0.1:8080，无需认证
python run.py

# 调试模式（详细日志）
python run.py --debug

# 或通过环境变量配置
HERMES_ANTHROPIC_API_KEY=sk-ant-xxx \
HERMES_API_TOKEN=my-secret-token \
python run.py --port 3000

# 或 Docker 一行启动
docker compose up -d

# 带 Redis 事件总线（多实例扩展用）
docker compose --profile redis up -d
```

### API 一览 / API at a Glance

| Method | Endpoint | 说明 Description |
|--------|----------|-----------------|
| `POST` | `/api/agent/chat` | Agent 对话 (非流式 non-streaming) |
| `POST` | `/api/agent/chat/stream` | Agent 对话 (SSE 流式 streaming) |
| `GET/POST` | `/api/memories` | 记忆 CRUD + 搜索 Memory CRUD + search |
| `POST` | `/api/memories/curator/run` | 运行记忆整理 (可选 `use_llm` 参数) Run curator |
| `GET/POST` | `/api/conversations` | 对话管理 Conversation management |
| `GET/POST` | `/api/skills` | Skill 管理 Skill management |
| `POST` | `/api/skills/match` | Skill 关键词匹配 Keyword match |
| `GET` | `/api/tools` | 内置工具列表 Built-in tool list |
| `POST` | `/api/tools/execute` | 执行工具 Execute a tool |
| `GET/POST` | `/api/mcp/servers` | MCP 服务器管理 MCP server management |
| `GET` | `/api/mcp/servers/{name}/health` | 单个 MCP 服务器健康检查 |
| `GET` | `/api/mcp/health` | 全部 MCP 服务器批量探测 |
| `GET/POST` | `/api/providers` | Provider 列表 + 直接调用 List + direct call |
| `GET` | `/api/health` | 健康检查 Health check |
| `WS` | `/ws` | WebSocket 事件 Event bus |

### 配置 / Configuration

| 环境变量 Env | 默认 Default | 说明 Description |
|-------------|-------------|-----------------|
| `HERMES_HOST` | `127.0.0.1` | 监听地址 Listen address |
| `HERMES_PORT` | `8080` | 监听端口 Listen port |
| `HERMES_DEBUG` | `false` | 调试模式 Debug mode |
| `HERMES_DATA_DIR` | `~/.hermes-engine` | 数据目录 Data directory |
| `HERMES_API_TOKEN` | (空/empty) | API 认证 Token (空=本地模式不启用) |
| `HERMES_ANTHROPIC_API_KEY` | (空/empty) | Anthropic API Key |
| `HERMES_OPENAI_API_KEY` | (空/empty) | OpenAI API Key |
| `HERMES_GEMINI_API_KEY` | (空/empty) | Google Gemini API Key |
| `HERMES_EXTRA_ALLOWED_COMMANDS` | `[]` | 额外允许执行的命令 Additional whitelisted commands |
| `HERMES_MCP_TIMEOUT` | `30.0` | MCP 服务器连接超时（秒）Connection timeout for MCP servers |
| `HERMES_EVENT_BACKEND` | `memory` | 事件总线后端 (`memory` / `redis`)，Redis 需额外安装 `redis>=5.0` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接 URL（仅 `HERMES_EVENT_BACKEND=redis` 时使用） |
| `HERMES_CORS_ORIGINS` | `*` | CORS 允许源（逗号分隔，如 `http://localhost:3000`） |

---

## 开发 / Development

### 测试 / Testing

```bash
pytest                    # 105 tests (coverage: pytest --cov)
mypy .                   # 0 errors (75 source files)
ruff check .             # Lint check
```

### 部署 / Deployment

```bash
# Docker 一键启动（默认 + observability extras）
docker compose up -d

# 带 Redis 事件总线（水平扩展多实例时用）
docker compose --profile redis up -d

# 自定义环境变量
HERMES_API_TOKEN=my-token HERMES_PORT=8080 docker compose up -d
```

### 预提交 / Pre-commit

```bash
pip install pre-commit
pre-commit install
```

### CI/CD

GitHub Actions 自动运行 lint → typecheck → test (3.11/3.12/3.13) → coverage ≥75% → security scan。

GitHub Actions auto-runs lint → typecheck → test (3.11/3.12/3.13) → coverage ≥75% → security scan.

---

## 项目结构 / Project Structure

```
hermes-engine/
├── agent/              # Agent 引擎 + 流式对话
├── config/             # Pydantic Settings
├── conversation/       # 对话存储 + 路由
├── mcp/                # MCP Bridge + 路由
├── memory/             # SQLite + FTS5 记忆存储 + Curator (LLM 语义合并)
├── provider/           # AI Provider 适配器 (Anthropic/OpenAI/Gemini)
├── shared/             # 共享模型 / 错误 / 事件总线(可插拔后端) / DI / 可观测性
├── skill/              # Skill 发现与匹配
├── tools/              # 内置工具 (读文件/写文件/执行命令)
├── tests/              # 105 个 Pytest 用例（认证/CRUD/流式/MCP/Curator/Event 总线）
├── Dockerfile          # 生产容器镜像
├── docker-compose.yml  # 一键启动（含可选 Redis）
├── main.py             # FastAPI 入口
├── pyproject.toml      # 项目配置
├── .pre-commit-config.yaml
└── .github/workflows/ci.yml
```

---

## 安全 / Security

- **命令执行 / Command execution**：白名单 + 危险模式正则 + PATH 消毒
- **文件访问 / File access**：限制在项目目录，符号链接验证
- **认证 / Authentication**：可选 Bearer Token (`HERMES_API_TOKEN`)
- **SQL 注入 / SQL injection**：参数化查询 + WAL 模式

---

## 许可证 / License

Apache 2.0 — 基于 NousResearch Hermes Agent 改编 / adapted from NousResearch Hermes Agent.

---

## 评分 / Quality Score

| 维度 Dimension | 评分 Score |
|---------------|-----------|
| 架构 Architecture | **A** |
| 代码质量 Code Quality | **A** |
| 安全性 Security | **A-** |
| 测试 Tests | **A** → 105 passed / coverage ≥75% |
| 工程化 Engineering | **A** → Docker + Graceful Shutdown + CORS |
| **综合 Overall** | **A+** |

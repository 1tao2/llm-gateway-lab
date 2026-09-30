# LLM Gateway & Reliability Platform

## FDE 简历项目学习手册 V2

> **定位**：面向 Forward Deployed Engineer（FDE）/ AI Engineer
> 的个人项目学习手册\
> **环境约束**：个人 Windows 电脑 + VS
> Code；真实模型 API
> 由个人账号承担费用\
> **核心策略**：Mock First → Compatible Integration → 少量 Zhipu API
> E2E。把项目价值放在系统设计、集成、可靠性、可观测性、评测和故障排查，而不是模型调用次数。\
> **模型资源**：真实文本生成与 Embedding 均使用智谱开放平台赠送
> Token；可靠性测试全部使用 Mock，不购买或依赖其他付费模型。本地模型仅为可选项。\
> **最终成果**：一个可以公开放
> GitHub、可以现场演示、可以在简历中解释设计取舍的多模型 AI Gateway
> 与智能故障诊断平台。

------------------------------------------------------------------------

# 1. 为什么重构原学习项目

原方案的学习链路是：

`LLM → RAG → MCP → Agent → Memory → 工程化`

这条链路适合学习完整 AI Agent，但对于已经有
Python/API/模型接入经验、目标转向 FDE 的开发者，存在三个问题：

1.  前半程偏"聊天机器人入门"，简历区分度有限。
2.  工程化只在最后出现，可靠性、评测、故障处理训练不足。
3.  项目价值容易被"用了什么模型"绑架，而个人开发者不适合大量承担模型费用。

因此 V2 改成：

`Provider SDK → Model Router → Reliability → Observability → Evaluation → RAG Runbook → Diagnosis Agent → API Gateway → Deployment & Failure Drill`

原则是：**Agent 是最后的能力整合层，而不是项目本体。**

------------------------------------------------------------------------

# 2. 最终项目定义

项目名称：

**LLM Gateway & Reliability Platform**

项目要解决的问题：

> 不同模型渠道具有不同延迟、错误率和成本。如何通过统一 API 接入多个
> Provider，并在 Provider 出现
> Timeout、429、5xx、连接失败等异常时进行重试、熔断和降级，同时提供完整
> Trace、稳定性评测以及 AI 辅助故障诊断？

最终调用方式：

``` python
response = await gateway.chat(
    capability="text_generation",
    messages=[{"role": "user", "content": "hello"}],
)
```

业务代码不应该知道当前真正调用的是：

``` text
MockProvider
LocalProvider
RealAPIProvider
```

这些由 Router 决定。

------------------------------------------------------------------------

# 3. 环境与费用控制

## 3.1 三层测试体系

  层级          Provider                    成本 使用场景
  ------------- ------------------------- ------ ------------------------------
  Unit          Mock Provider                  0 日常开发、故障注入、单元测试
  Integration   Mock Server / 本地模型（可选） 0 验证协议、流式响应和生成链路
  E2E           智谱赠送 Token              少量 验证真实生成与 Embedding 接入

**不要用付费 API 做压力测试、熔断测试和大规模评测。**

建议开发期间 90% 以上请求由 Mock 完成。

## 3.2 最低硬件路线

如果电脑不适合运行本地 LLM，完全可以：

`Mock Provider + 智谱赠送 Token`

本地 LLM 是加分项，不是项目完成条件。

## 3.3 Token 使用边界

-   文本生成和 Embedding 都使用智谱赠送 Token。
-   Mock Provider 承担超时、429、5xx、连接失败、熔断、压力及回归测试。
-   智谱 API 只用于少量正常 E2E、响应映射、流式输出、usage 和诊断验证。
-   Runbook 文档建立内容哈希并缓存 Embedding；内容没有变化时不重复生成向量。
-   在测试中禁止因随机故障注入调用真实 API。

------------------------------------------------------------------------

# 4. 最终架构

``` text
Client / Swagger / CLI
          │
          ▼
┌─────────────────────────┐
│     FastAPI Gateway     │
│ /chat /models /diagnose │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│       Model Router      │
│ produce route candidates│
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Reliability Orchestrator│
│ deadline / retry        │
│ fallback / circuit      │
└────────────┬────────────┘
             │
     ┌───────┼─────────┐
     ▼       ▼         ▼
   Mock    Compatible   Zhipu API
 Provider Mock Server   Provider
     └───────┼─────────┘
             ▼
┌─────────────────────────┐
│     Observability       │
│ logs / trace / metrics  │
└────────────┬────────────┘
             │
     ┌───────┴────────┐
     ▼                ▼
 Evaluation      Diagnosis Agent
                      │
                 RAG Runbook
```

------------------------------------------------------------------------

# 5. 最终项目目录

``` text
llm-gateway-lab/
├── app/
│   ├── api/
│   │   ├── routes_chat.py
│   │   ├── routes_models.py
│   │   └── routes_diagnose.py
│   ├── providers/
│   │   ├── base.py
│   │   ├── mock.py
│   │   ├── local.py
│   │   ├── openai_compatible.py
│   │   └── zhipu.py
│   ├── router/
│   │   ├── registry.py
│   │   ├── router.py
│   │   └── schemas.py
│   ├── reliability/
│   │   ├── retry.py
│   │   ├── circuit_breaker.py
│   │   ├── rate_limiter.py
│   │   └── errors.py
│   ├── observability/
│   │   ├── logging.py
│   │   ├── trace.py
│   │   └── metrics.py
│   ├── evaluation/
│   │   ├── runner.py
│   │   ├── metrics.py
│   │   └── report.py
│   ├── rag/
│   │   ├── indexer.py
│   │   └── retriever.py
│   ├── agent/
│   │   ├── tools.py
│   │   └── diagnosis.py
│   └── config.py
├── configs/
│   ├── models.yaml
│   └── providers.yaml
├── docs/
│   └── runbooks/
├── eval/
│   ├── cases/
│   └── reports/
├── tests/
├── data/
├── docker/
├── .env.example
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

------------------------------------------------------------------------

# 6. 学习规则

每个阶段严格执行：

``` text
① 阅读需求与验收标准
        ↓
② 自己先设计接口/数据结构
        ↓
③ 实现最小版本
        ↓
④ 跑测试
        ↓
⑤ 主动制造异常
        ↓
⑥ Debug
        ↓
⑦ Code Review / 重构
        ↓
⑧ 写学习记录
        ↓
⑨ 进入下一阶段
```

**从 Phase 2 开始，不建议直接复制完整答案。**

每个阶段至少回答三个问题：

-   为什么这样设计？
-   如果当前依赖挂了会发生什么？
-   如何证明修改后系统真的更好了？

------------------------------------------------------------------------

# 7. Phase 0：项目骨架与工程基线

**预计：1 小时**

## 目标

建立可长期迭代的 Python 项目，而不是单文件 Demo。

## 任务

-   创建 Git 仓库。
-   建立 `app/`、`tests/`、`configs/`。
-   使用 `.env` 管理密钥。
-   定义统一配置对象。
-   建立 `/health`。
-   配置 pytest。
-   API Key 绝不能提交 Git。

## 完成标准

-   `pytest` 可以执行。
-   FastAPI 能启动。
-   `/health` 返回 200。
-   `.env.example` 存在且没有真实密钥。
-   README 可以让另一台电脑完成初始化。

## Debug Drill

-   缺少环境变量。
-   配置文件不存在。
-   YAML 格式错误。
-   端口被占用。

## FDE 关注点

FDE 拿到客户环境后的第一件事通常不是写 Agent，而是确认：

`环境 / 配置 / 网络 / 权限 / 依赖 / 可复现性`

------------------------------------------------------------------------

# 8. Phase 1：Unified Provider SDK

**预计：2 小时**

## 目标

让上层业务不依赖具体 Provider SDK。

定义统一接口：

``` python
class BaseProvider:
    async def chat(self, request):
        ...
```

统一返回：

``` json
{
  "request_id": "req_xxx",
  "provider": "mock",
  "model": "mock-v1",
  "content": "hello",
  "latency_ms": 120,
  "usage": {}
}
```

## 第一版 Provider

必须：

-   MockProvider
-   ZhipuProvider（唯一真实云端 Provider）
-   OpenAICompatibleProvider（通过本地 Mock Server 验证协议兼容性）

可选：

-   LocalProvider

这里的“多 Provider”首先表示统一接口和可扩展架构，不表示已经购买并接入多个商业平台。

## MockProvider 必须支持故障注入

至少：

``` text
normal
timeout
429
500
connection_error
invalid_response
slow_response
```

## 学习点

-   ABC / Protocol
-   Adapter Pattern
-   async/await
-   httpx
-   Pydantic
-   Exception Mapping

## 完成标准

同一段业务代码只修改 Provider 配置即可运行。

## Debug Drill

Provider 返回：

-   HTTP 200 + 非法 JSON
-   HTTP 401
-   HTTP 429
-   HTTP 500
-   ReadTimeout
-   ConnectionError

要求全部转换成自己的统一异常，而不是把第三方异常泄露到业务层。

## 面试题

> 为什么不让 Router 直接调用 OpenAI SDK？

> 为什么需要统一 Response Schema？

------------------------------------------------------------------------

# 9. Phase 2：Model Registry & Router

**预计：2～3 小时**

这是整个项目第一个核心模块。

## 目标

实现：

`业务能力 ≠ model_name ≠ provider`

配置示例：

``` yaml
capabilities:
  text_generation:
    routes:
      - channel: primary
        provider: local
        model: qwen-local
        priority: 1
      - channel: backup
        provider: api
        model: small-model
        priority: 2
```

调用：

``` python
await router.route(
    capability="text_generation",
    request=request,
)
```

## 必做能力

-   Provider Registry
-   Model Registry
-   capability → route
-   primary / backup
-   enabled
-   priority
-   配置热加载可作为进阶项

## 关键设计

不要：

``` python
if model == "xxx":
    call_xxx()
elif model == "yyy":
    call_yyy()
```

而使用：

`Registry + Adapter + Router`

## 完成标准

-   新增 Provider 不修改 Router 核心代码。
-   主备顺序由配置决定。
-   禁用 primary 后可以选择 backup。
-   model_name 相同但 provider 不同仍可正确区分。

## Debug Drill

-   Provider 不存在。
-   Model 未注册。
-   所有 Route disabled。
-   Primary 配置错误。
-   两个渠道使用相同 model_name。

## 简历价值

这一阶段已经可以形成：

> 基于 Adapter + Registry 架构实现 Provider/Model
> 解耦及配置驱动的动态模型路由。

------------------------------------------------------------------------

# 10. Phase 3：Reliability Layer

**预计：3～4 小时**

这是项目最重要的阶段之一。

## 目标

实现：

``` text
Timeout
Retry
Exponential Backoff
Fallback
Circuit Breaker
```

Rate Limit、全局并发控制和分布式状态放入 V3，不作为本手册的完成条件。

## 推荐执行链

``` text
Request
  ↓
Router 生成有序候选路由
  ↓
Reliability Orchestrator
  ├ 检查候选路由的 Circuit Breaker
  ├ 执行有单次超时限制的 Provider Attempt
  ├ 对可恢复错误进行 Retry
  └ 当前路由不可用时选择下一个候选路由 Fallback
```

Circuit Breaker 至少按 `(provider, model)` 隔离。Router 只负责产生候选路由，
Reliability Orchestrator 负责尝试、重试和切换，避免 Router 与 Fallback 相互调用。

## 时间预算

必须区分：

-   `attempt_timeout`：单次 Provider 调用的超时。
-   `request_deadline`：包括重试、退避和 Fallback 在内的总截止时间。
-   `max_attempts`：一次逻辑请求允许的最大 Provider 尝试次数。
-   客户端取消后应向上游传播取消，不能继续消耗 Token。

## Retry

只对"可能恢复"的错误重试。

思考：

-   400 是否应该 retry？
-   401 是否应该 retry？
-   429 呢？
-   Timeout 呢？
-   500 呢？

不要机械地所有异常重试三次。

指数退避需要加入 jitter。429 优先遵循 `Retry-After`；400、401、内容安全拒绝、
上下文超长等错误不应作为 Provider 可用性故障计入熔断器。

## 流式输出边界

-   首个 token 输出前失败，可以按策略 Retry 或 Fallback。
-   已向客户端输出 token 后，不允许透明切换 Provider，避免拼接出不一致响应。
-   客户端断开时取消上游流式请求。
-   记录首 token 延迟（TTFT）、流式总时长和中途失败。
-   如果 V2 暂不实现流式输出，必须在 README 中明确列为已知限制。

## Circuit Breaker

状态：

``` text
CLOSED
  ↓ failures threshold
OPEN
  ↓ cooldown
HALF_OPEN
  ↓ success
CLOSED
```

## Failure Injection

使用 MockProvider 自动制造：

``` text
30% Timeout
20% HTTP 500
2 秒固定延迟
连续 5 次失败
```

## 完成标准

必须有自动化测试证明：

-   Timeout 会 retry。
-   400 不会无意义 retry。
-   Primary 失败可以 fallback。
-   连续失败触发 breaker。
-   OPEN 状态不会继续轰炸 Provider。
-   cooldown 后进入 HALF_OPEN。
-   恢复后重新 CLOSED。

## 必须思考

> Retry 为什么可能让故障更严重？

> Retry + Fallback 会不会导致重复计费？

> 如果请求不是幂等的怎么办？

------------------------------------------------------------------------

# 11. Phase 4：Observability

**预计：2～3 小时**

不能只写：

``` python
print("调用失败")
```

## 目标

做到"拿一个 request_id 就能还原一次请求发生了什么"。

每个请求记录：

``` json
{
  "request_id": "req_xxx",
  "capability": "text_generation",
  "provider": "mock",
  "model": "mock-v1",
  "route": "primary",
  "latency_ms": 823,
  "retry_count": 1,
  "fallback": false,
  "status": "success",
  "error_type": null
}
```

## Metrics

至少：

-   logical_request_count：客户端逻辑请求数。
-   provider_attempt_count：实际 Provider 调用次数。
-   first_attempt_success_rate：首次尝试成功率。
-   final_success_rate：重试和降级后的最终成功率。
-   provider_error_rate 与 gateway_error_rate。
-   retry_rate 与 fallback_rate。
-   end_to_end_latency P50/P95。
-   provider_latency P50/P95。
-   TTFT、token usage 与估算成本（真实 API 场景）。

P99 作为进阶。

## Trace

一次请求：

``` text
req_001

gateway       1260ms
 ├ router       10ms
 ├ provider    800ms FAILED timeout
 ├ backoff     200ms
 └ provider    230ms SUCCESS
```

## 完成标准

给你任意 `request_id`，可以回答：

-   调用了哪个 provider？
-   哪个 model？
-   是否重试？
-   是否 fallback？
-   慢在哪里？
-   最终为什么失败？

## Debug Drill

制造"偶发慢请求"，只通过日志定位。

------------------------------------------------------------------------

# 12. Phase 5：Evaluation Pipeline

**预计：3 小时**

## 目标

不是评价"哪个 LLM 最聪明"，而是评价**Gateway 是否稳定**。

## Case Schema

``` yaml
id: timeout_fallback_001
scenario: timeout
provider: primary
expected:
  retry: true
  fallback: true
  final_status: success
```

Mock Case 必须使用固定故障序列或固定随机种子，保证回归结果可重复。

## 第一批 Case

至少 30 个：

``` text
Normal × 5
Timeout × 5
429 × 5
500 × 5
Connection Error × 3
Slow Response × 3
Invalid Response × 2
Circuit Breaker × 2
```

全部可以使用 Mock，费用为 0。

## 输出报告

``` text
Total Requests: 30
Success Rate: 96.7%
P50 Latency: 320ms
P95 Latency: 1250ms
Retry Rate: 23%
Fallback Rate: 10%

Error Distribution:
timeout: 2
500: 1
```

建议同时导出：

-   `report.json`
-   `report.md`

## 进阶

对 Router V1 和 Router V2 做 Regression Test。

## 完成标准

任何 Reliability 代码修改后：

``` bash
python -m app.evaluation.runner
```

都能回答：

> 这次修改让系统变好还是变坏？

------------------------------------------------------------------------

# 13. Phase 6：RAG Runbook

**预计：3 小时**

这时再学习 RAG。

## 知识库

自己编写公开、安全、不包含公司信息的 Runbook：

``` text
docs/runbooks/
├── timeout.md
├── rate_limit.md
├── provider_5xx.md
├── invalid_response.md
├── high_latency.md
├── circuit_breaker.md
└── fallback.md
```

## Pipeline

``` text
Runbook
 ↓
Chunk
 ↓
智谱 Embedding API
 ↓
Vector Store
```

默认使用智谱赠送 Token 支持的 Embedding 模型。索引器必须按文档内容哈希缓存结果，
只为新增或发生变化的 Chunk 重新生成 Embedding。本地 Embedding 仅作为无网络时的可选替代，
不是项目完成条件。

在线：

``` text
Query
 ├ Vector Retrieval
 └ Keyword Retrieval
        ↓
       RRF
        ↓
    Top Documents
```

rerank 可以先不调用付费 LLM。

## 目标问题

``` text
“Provider 连续 timeout 怎么排查？”

“为什么 circuit breaker 一直 OPEN？”

“429 是否应该重试？”
```

## 完成标准

-   能返回正确 Runbook。
-   能显示 source。
-   没有知识时明确说明。
-   检索和生成逻辑分离。
-   建立一组带相关文档标注的检索测试问题，并至少报告 Recall@K。
-   重建未变化的索引时，不重复调用 Embedding API。

## 不要过度工程

第一版不需要：

-   GraphRAG
-   Agentic RAG
-   多级知识图谱

先把 Retrieval 做对。

------------------------------------------------------------------------

# 14. Phase 7：Diagnosis Agent

**预计：3～4 小时**

Agent 到这里才出现。

## 目标

让 LLM 负责"判断下一步需要什么信息"，工具负责提供事实。

## Tools

第一版只提供：

``` text
get_gateway_metrics
get_request_trace
get_recent_errors
get_router_config
search_runbook
```

全部读取你自己项目产生的数据，不需要公司系统权限。

## 示例

用户：

> 最近为什么失败率突然升高？

Agent：

``` text
get_gateway_metrics
        ↓
发现 error_rate = 31%
        ↓
get_recent_errors
        ↓
Timeout 占 82%
        ↓
get_router_config
        ↓
Primary 没有 fallback
        ↓
search_runbook
        ↓
生成 Root Cause + Recommendation
```

## Agent 边界

Agent **不能直接修改配置**。

第一版只允许：

``` text
Read
Diagnose
Recommend
```

不允许：

``` text
Write
Delete
Restart
Modify
```

这样既安全，也更容易演示。

## 完成标准

Agent 回答必须区分：

-   Evidence
-   Diagnosis
-   Recommendation

不能凭空编造不存在的 metrics。

每项 Diagnosis 必须引用 request trace、metric 或 Runbook source；证据不足时返回
`insufficient_evidence`，而不是补全不存在的事实。真实生成调用使用智谱赠送 Token。

------------------------------------------------------------------------

# 15. Phase 8：FastAPI Gateway

**预计：2 小时**

## API

至少：

``` text
POST /v1/chat
GET  /v1/models
GET  /v1/requests/{request_id}
GET  /v1/metrics
POST /v1/diagnose
GET  /health
```

## Middleware

加入：

-   request_id
-   request logging
-   global exception handler
-   latency

日志默认不保存完整 Prompt、模型响应或 API Key；请求查询和诊断接口需要明确仅用于
本地演示，并对敏感字段进行脱敏。

## 完成标准

Swagger 可以完整演示：

``` text
调用模型
→ 查看 request trace
→ 查看 metrics
→ 发起 diagnose
```

这形成一条完整 Demo 链路。

------------------------------------------------------------------------

# 16. Phase 9：Docker & Production Simulation

**预计：3 小时**

## 目标

另一台机器：

``` bash
git clone ...
docker compose up
```

即可启动项目。

## 最低 Compose

``` text
gateway
```

可选：

``` text
ollama
prometheus
grafana
```

不要为了"技术栈丰富"强行加入 Redis、Kafka、Kubernetes。

## 完成标准

-   Docker Build 成功。
-   容器健康检查正常。
-   配置通过环境变量注入。
-   容器重启后项目仍可运行。
-   README 从零启动步骤验证通过。

------------------------------------------------------------------------

# 17. Phase 10：Final Failure Drill

**预计：2～3 小时**

这是最终答辩。

## Scenario A：Primary Timeout

``` text
Primary 延迟 5 秒
Gateway timeout = 2 秒
```

要求展示：

``` text
Timeout
→ Retry
→ Failure
→ Fallback
→ Success
→ Trace
→ Metrics
```

## Scenario B：Provider 持续 500

展示：

``` text
连续失败
→ Circuit Breaker OPEN
→ 后续请求不再访问故障 Provider
→ cooldown
→ HALF_OPEN
→ 恢复
```

## Scenario C：429

说明：

-   为什么 retry？
-   backoff 怎么设计？
-   是否考虑 Retry-After？
-   为什么不能立即疯狂重试？

## Scenario D：系统诊断

问 Agent：

> 为什么 Primary 最近被绕过？

要求 Agent 从 Metrics + Trace + Router Config + Runbook 找到证据。

------------------------------------------------------------------------

# 18. 少量真实 API 验证

整个项目开发完成后才接智谱真实 API。

建议只准备 5～10 个 E2E Case。

验证：

-   智谱生成模型与 Embedding 模型接入。
-   SDK/API 兼容。
-   Response Mapping。
-   usage。
-   timeout。
-   request_id。
-   正常生成。
-   流式响应或明确记录其暂缓原因。

**不要用真实 API 验证 30% timeout、连续 500 等人为故障。**

这些属于 Mock Failure Injection 的职责。

------------------------------------------------------------------------

# 19. 测试策略

## Unit Test

重点：

``` text
Provider Adapter
Router
Retry
Circuit Breaker
Error Mapping
Metrics
```

## Integration Test

重点：

``` text
Router → Reliability → MockProvider
API → Router → Provider
Evaluation → Gateway
Agent → Tools → Metrics/RAG
```

## E2E

少量智谱真实 API。

不以测试数量作为硬指标。建立“错误类型 × Retry × Fallback × Breaker 状态”的风险矩阵，
优先覆盖核心 failure path，并确保测试可重复。

------------------------------------------------------------------------

# 20. 安全要求

公开 GitHub 前必须检查：

-   无 API Key。
-   无公司域名。
-   无公司 IP。
-   无公司模型名/内部渠道名。
-   无公司日志。
-   无内部 Prompt。
-   无真实用户数据。
-   无公司架构截图。

`.env.example`：

``` text
ZHIPU_API_KEY=
ZHIPU_BASE_URL=
ZHIPU_CHAT_MODEL=
ZHIPU_EMBEDDING_MODEL=
```

README 明确：

> The project uses synthetic data and mock providers for reliability
> testing.

------------------------------------------------------------------------

# 21. README 必须展示什么

README 不要从"这是一个 AI Agent"开始。

第一屏直接回答：

## Problem

Multi-provider LLM services can suffer from latency spikes, rate limits
and provider outages.

## Solution

A reliability-oriented LLM Gateway providing:

``` text
Unified Provider API
Dynamic Routing
Retry / Fallback
Circuit Breaker
Failure Injection
Tracing & Metrics
Evaluation
RAG-assisted Diagnosis
```

然后放架构图。

再放一个 Failure Drill：

``` text
Primary timeout
→ Retry failed
→ Circuit opened
→ Backup selected
→ Request succeeded
```

最后才介绍 Agent。

------------------------------------------------------------------------

# 22. 简历项目描述模板

项目真正完成后，可根据真实实现修改为：

## LLM Gateway & Reliability Platform

**Python / FastAPI / Pydantic / httpx / Docker / 智谱 API / RAG**

-   设计并实现可扩展的多 Provider AI Gateway，采用 Adapter +
    Registry 架构实现 Provider、Model 与业务 Capability
    解耦，完成智谱真实模型接入，并使用 Mock/OpenAI-compatible 测试服务验证配置驱动的主备路由。
-   构建 Timeout、Retry、Exponential Backoff、Fallback 与 Circuit
    Breaker 等可靠性机制，通过 Mock Failure Injection 模拟
    429、5xx、连接异常及高延迟场景。
-   建立请求级 Trace 与稳定性 Evaluation Pipeline，统计 Success
    Rate、P50/P95 Latency、Retry Rate 与 Fallback Rate，并用于 Router
    版本回归测试。
-   使用智谱 Embedding 建立可增量缓存的 Runbook 索引，并基于运行指标、错误 Trace、
    Router Config 与 RAG Runbook 构建只读
    Diagnosis Agent，生成证据驱动的 Root Cause 与处理建议。
-   使用 FastAPI + Docker 完成本地 Production-like 部署，并采用 Mock /
    Local / Real API 分层测试降低真实模型调用成本。

**注意：只能写你真正完成并能解释的功能。只有一个真实云端 Provider 时，不写“接入多个
商业模型平台”或“经过多平台生产压测”。**

------------------------------------------------------------------------

# 23. 面试必须能回答的问题

完成项目不等于会讲项目。

至少准备：

1.  为什么需要 Provider Adapter？
2.  Model 和 Provider 为什么要解耦？
3.  Retry 哪些错误应该做，哪些不应该？
4.  指数退避解决什么问题？
5.  Retry 为什么可能造成雪崩？
6.  Circuit Breaker 三种状态怎么切换？
7.  Fallback 会带来哪些风险？
8.  如何避免重复请求/重复计费？
9.  P50 和 P95 分别说明什么？
10. 为什么 Failure Injection 用 Mock 而不是真实 API？
11. Router 配置错误怎么发现？
12. 如何根据 Trace 定位慢请求？
13. 为什么 Agent 不直接执行修改操作？
14. RAG 在这个项目中解决什么问题？
15. 如果有 10 个 Provider，当前架构哪里需要升级？
16. 单机版和真正生产系统最大的差距是什么？

最后一个尤其重要。

不要把个人项目包装成生产级平台。可以明确说：

> 这是一个 Production-like 单机实验平台，用来验证多 Provider
> 路由、可靠性、可观测性与诊断方案。真正生产环境还需要分布式状态、集中配置、持久化
> Metrics、认证鉴权、租户隔离、容量规划等能力。

这个回答比声称"生产级"更专业。

------------------------------------------------------------------------

# 24. 推荐学习节奏

如果每天约 1～2 小时，下面是理想推进顺序；实际建议预留 5～7 周：

  Day   内容            当天产出
  ----- --------------- ------------------------
  1     Phase 0         项目骨架
  2     Provider SDK    MockProvider
  3     Provider SDK    Zhipu Adapter
  4     Router          Registry + Route
  5     Router          Primary/Backup
  6     Reliability     Timeout + Retry
  7     Reliability     Fallback
  8     Reliability     Circuit Breaker
  9     Observability   Structured Log + Trace
  10    Metrics         P50/P95/Error Rate
  11    Evaluation      Eval Runner
  12    Evaluation      Regression Report
  13    RAG             Zhipu Embedding + Retrieval
  14    Agent           Tools
  15    Agent           Diagnosis
  16    FastAPI         API Gateway
  17    Docker          Compose
  18    Failure Drill   Timeout/500/429
  19    E2E             少量智谱真实 API
  20    Portfolio       README + 简历 + Demo

不必追求 20 天完成。每一阶段跑通并理解后再继续。

------------------------------------------------------------------------

# 25. 每阶段学习记录模板

``` markdown
## Phase X 学习记录

### 今天完成了什么

### 我的设计

### 为什么这么设计

### 测试结果

### 主动制造的故障

### 如何定位

### 修改前后对比

### 还不理解的问题

### 如果用于生产还缺什么

### 是否通过验收
- [ ] 是
- [ ] 否
```

------------------------------------------------------------------------

# 26. 最终验收 Checklist

## Architecture

-   [ ] Provider 与 Model 解耦
-   [ ] Router 配置驱动
-   [ ] Provider 可扩展
-   [ ] 业务层不知道具体 Provider

## Reliability

-   [ ] Timeout
-   [ ] Retry
-   [ ] Backoff
-   [ ] Fallback
-   [ ] Circuit Breaker
-   [ ] Failure Injection
-   [ ] 总请求时间预算与最大尝试次数
-   [ ] 客户端取消传播

## Observability

-   [ ] Request ID
-   [ ] Structured Log
-   [ ] Trace
-   [ ] Error Classification
-   [ ] P50/P95
-   [ ] Retry/Fallback Metrics
-   [ ] 逻辑请求与 Provider Attempt 分开统计
-   [ ] TTFT/Token Usage（真实 API）

## Evaluation

-   [ ] 自动 Case Runner
-   [ ] Reliability Cases
-   [ ] JSON/Markdown Report
-   [ ] Regression Test

## AI

-   [ ] RAG Runbook
-   [ ] 智谱 Embedding 与增量缓存
-   [ ] Source-aware Retrieval
-   [ ] Diagnosis Tools
-   [ ] Evidence-based Agent

## Engineering

-   [ ] FastAPI
-   [ ] pytest
-   [ ] Docker
-   [ ] `.env.example`
-   [ ] README
-   [ ] GitHub 无敏感信息

## Portfolio

-   [ ] 架构图
-   [ ] Failure Drill 截图/录屏
-   [ ] Evaluation Report
-   [ ] 设计取舍说明
-   [ ] 简历项目描述
-   [ ] 能在 5 分钟内演示

------------------------------------------------------------------------

# 27. 最终 Demo 脚本

面试或作品展示时，不要从 Chat 开始。

## Demo 1：正常路由

``` text
发送 Request
→ Primary
→ Success
→ 查看 Trace
```

## Demo 2：故障

``` text
设置 Mock Primary = Timeout
→ Request
→ Retry
→ Fallback
→ Success
```

## Demo 3：熔断

``` text
连续制造失败
→ Breaker OPEN
→ 新请求直接绕过 Primary
```

## Demo 4：指标

展示：

``` text
Success Rate
P95
Retry Rate
Fallback Rate
```

## Demo 5：AI Diagnosis

输入：

> 为什么 Primary 被大量 fallback？

Agent 根据真实模拟数据输出：

``` text
Evidence
Root Cause
Recommendation
```

这五步展示完，面试官基本已经能理解整个项目。

------------------------------------------------------------------------

# 28. 项目完成后的第二阶段

完成本项目后再考虑：

``` text
Redis 分布式 Circuit Breaker
Prometheus + Grafana
OpenTelemetry
动态配置中心
Rate Limit / Concurrency Limit / Bulkhead
Weighted Routing
Latency-aware Routing
Cost-aware Routing
Load Balancing
API Authentication
Multi-Tenant
Kubernetes
```

这些属于 V3。

**不要在 V1/V2 阶段一次性全部加入。**

------------------------------------------------------------------------

# 29. 开始前准备清单

``` text
□ Python 3.11+
□ VS Code
□ Git
□ Docker Desktop（Phase 9 前安装即可）
□ 一个 GitHub 仓库
□ 智谱开放平台 API Key 与赠送 Token（Phase 1 可暂时不填）
□ pytest
□ FastAPI
□ httpx
□ Pydantic
□ PyYAML
```

第一阶段完全不需要花模型费用。

本文件使用 UTF-8 编码。Windows PowerShell 5 读取时建议显式执行：

```powershell
Get-Content -Encoding UTF8 <文件路径>
```

------------------------------------------------------------------------

# 30. 第一阶段真正的起点

不要先写 Agent，也不要先写 RAG。

第一步只做：

``` text
Phase 0
项目骨架
   ↓
Phase 1
BaseProvider
   ↓
MockProvider
   ↓
故障注入
   ↓
自动化测试
```

等 MockProvider 能稳定模拟：

``` text
Success / Timeout / 429 / 500 / Slow Response
```

再开始 Model Router。

这是整个学习项目的地基。

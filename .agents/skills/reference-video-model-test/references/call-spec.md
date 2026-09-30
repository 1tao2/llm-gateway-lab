# 声明式调用规格

首次测试一个尚未固化适配器的模型时，根据官方 API 文档生成脱敏 `call_spec.json`。该文件属于单次测试运行产物，放入 `artifacts/`，不提交 Git。

调用规格只保存接口结构、字段映射和凭证环境变量名称，不得保存 API Key、Token、签名或认证 Header 的实际值。

## 适用边界

声明式执行器支持两种传输方式：

- `http`：创建与查询均为返回 JSON 的 HTTPS GET/POST 请求，使用 Bearer Token 或固定 Header 传递环境变量中的凭证。
- `project_client`：仓库已经接入或带复杂签名的厂商，通过 `clients.factory.get_aigc_client` 取得现有 Client，再声明创建和查询方法及参数映射。

两种方式都要求 Task ID、状态、视频 URL 和耗时能够通过固定 JSON 路径提取。仓库尚未接入的特殊签名、厂商 SDK、multipart、流式协议、回调驱动或复杂状态合并不应硬塞进 HTTP 调用规格；这些情况才新增协议级代码适配器。

## 数据结构

```json
{
  "schema_version": "1.0",
  "transport": {
    "kind": "http",
    "allowed_hosts": ["api.vendor.example"],
    "timeout_seconds": 120,
    "headers": {
      "Content-Type": "application/json",
      "X-Async": "enable"
    },
    "auth": {
      "type": "bearer_env",
      "env": "VENDOR_API_KEY"
    }
  },
  "prompt": {
    "image_reference_template": "图 {index}"
  },
  "assets": {
    "alpha_policy": "preserve"
  },
  "media": {
    "item_template": {
      "type": "reference_image",
      "url": "{{url}}"
    }
  },
  "create": {
    "method": "POST",
    "url": "https://api.vendor.example/v1/video/tasks",
    "body": {
      "model": "{{model}}",
      "input": {
        "prompt": "{{prompt}}",
        "media": "{{media}}"
      },
      "parameters": {
        "resolution": "{{resolution}}",
        "ratio": "{{ratio}}",
        "duration": "{{duration}}",
        "audio": "{{audio}}"
      }
    },
    "task_id_path": "output.task_id"
  },
  "query": {
    "method": "GET",
    "url": "https://api.vendor.example/v1/tasks/{{task_id}}",
    "status_path": "output.task_status",
    "success_values": ["SUCCEEDED"],
    "failure_values": ["FAILED", "CANCELED", "EXPIRED"],
    "video_url_path": "output.video_url",
    "poll_interval_seconds": 10,
    "time_paths": {
      "submit_time": "output.submit_time",
      "scheduled_time": "output.scheduled_time",
      "end_time": "output.end_time"
    },
    "usage_path": "usage"
  }
}
```

支持的模板变量：

- 创建请求：`model`、`provider`、`scene_index`、`prompt`、`media`、`resolution`、`ratio`、`duration`、`audio`、`prompt_extend`、`watermark`。
- 单个媒体项：`url`、`name`、`index`。
- 查询请求：`task_id`、`model`。

当字段值完全等于一个模板变量，例如 `"{{media}}"` 或 `"{{audio}}"`，执行器保留数组、布尔值或数值类型；模板嵌入普通字符串时转换为文本。

`assets.alpha_policy` 控制带透明通道图片的上传方式：

- `preserve`：保持 PNG 等原始格式直接上传，适用于明确支持该格式的模型。
- `flatten_white_jpeg`：在内存中铺白并转成 RGB JPEG 后上传，不覆盖本地源文件。为兼容既有调用规格，省略该字段时使用此策略。

`transport.auth.type` 支持：

- `none`：无认证。
- `bearer_env`：从 `env` 指定的环境变量取值并构造 Bearer Header。
- `header_env`：从 `env` 取值，并写入 `header` 指定的 Header。

已有项目 Client 的传输配置示例：

```json
{
  "transport": {
    "kind": "project_client",
    "provider": "provider-route-key",
    "factory_provider": "existing-factory-route-key",
    "task_type": "video",
    "credential_envs": ["PROVIDER_API_KEY"]
  },
  "create": {
    "method": "create_video_task",
    "kwargs": {
      "model": "{{model}}",
      "prompt": "{{prompt}}",
      "image_urls": "{{media}}",
      "duration": "{{duration}}",
      "resolution": "{{resolution}}"
    },
    "task_id_path": "response.task_id"
  },
  "query": {
    "method": "query_video_task",
    "kwargs": {"task_id": "{{task_id}}"},
    "status_path": "response.status",
    "success_values": ["SUCCEEDED"],
    "failure_values": ["FAILED"],
    "video_url_path": "response.video_url"
  }
}
```

`credential_envs` 只列出环境变量名称，用于真实执行前校验项目安全配置，不记录对应值。

`factory_provider` 仅用于测试调用规格需要复用已有工厂路由、但报告中的逻辑厂商名与工厂键不一致时；省略时使用 `provider`。它不会修改生产工厂映射。

需要先审核素材并传入 `asset://` 的模型，先使用技能内的 `prepare_tencent_vod_materials.py` 生成素材注册表，真实视频执行时增加 `--asset-registry <registry.json>`。执行器会校验每个本地文件的 SHA-256 与注册表一致，再按冻结顺序传入 `asset_uri`。

## 离线验证

真实上传和付费调用前，必须先运行：

```text
conda run --no-capture-output -n kino python -B -X utf8 \
  .agents/skills/reference-video-model-test/scripts/run_reference_video_test.py \
  --manifest <manifest.json> \
  --call-spec <call_spec.json> \
  --output-dir <validation-output> \
  --validate-only
```

离线验证使用不可访问的占位素材 URL，仅检查：调用规格安全边界、Prompt 资产编号、媒体顺序、模板字段和最终请求结构；不会读取凭证、上传资产或调用模型。

检查 `validation-output/requests/scene_<index>.json` 与官方文档一致后，用户明确授权真实执行，去掉 `--validate-only` 并设置允许的并发数。

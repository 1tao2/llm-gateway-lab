# 测试数据契约

## Manifest

预检脚本输出 JSON 对象，关键字段如下：

```json
{
  "schema_version": "1.0",
  "source": {
    "prompt_file": "...",
    "asset_dir": "..."
  },
  "test_config": {
    "provider": "vendor-route-key",
    "model": "vendor-video-model",
    "resolution": "480P",
    "ratio": "9:16",
    "default_audio": true
  },
  "preflight": {
    "passed": true,
    "errors": [],
    "warnings": []
  },
  "assets": [],
  "scenes": []
}
```

每个 `scenes[]` 至少包含：

- `scene_index`、`scene_title`
- `scene_video_prompt` 原值
- `duration` 和 `duration_source`
- `audio`：布尔值或 `null`（表示调用时省略）
- `references[]`：`index`、`name`、`file`
- `missing_assets[]`

## Results

报告脚本接受 JSON 数组，或包含 `results` 数组的对象。每条记录建议包含：

```json
{
  "test_id": "QH-03B",
  "scene_index": 3,
  "variant": "音画同出重跑",
  "task_id": "provider-task-id",
  "status": "SUCCEEDED",
  "audio": true,
  "video_url": "https://stable.example/video.mp4",
  "submit_time": "2026-08-25 19:43:17.863",
  "scheduled_time": "2026-08-25 19:43:17.938",
  "end_time": "2026-08-25 19:52:43.906",
  "usage": {
    "duration": 15,
    "fps": 30,
    "ratio": "9:16",
    "SR": 480
  },
  "issues": ""
}
```

同一 `scene_index` 可以有多个变体。不得覆盖旧任务；用唯一 `test_id` 和 `variant` 区分音频、Prompt、种子或参数变化。

如果厂商不返回某个时间字段，保留为 `null`。报告脚本只对可计算的提交到完成耗时做统计。

每次执行目录还应保存 `manifest.snapshot.json`、`call_spec.snapshot.json` 和请求快照。运行状态中的 `inputs` 记录两个输入文件的 SHA-256，用于确认报告、请求和实际执行来自同一组冻结输入；这些运行产物放在被 Git 忽略的 `artifacts/` 中。

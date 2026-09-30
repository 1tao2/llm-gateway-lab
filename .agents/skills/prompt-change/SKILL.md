---
name: prompt-change
description: 用于新增、修改、删除或排查本仓库的 Prompt YAML，以及关联的 Prompt 路由、版本、模型映射、占位符、输出 Schema、本地化和回归行为；普通 Python 代码修改或与运行时 Prompt 无关的文案编辑不使用。
---

# Prompt 变更

以最小、可验证的改动维护本仓库 Prompt。复用项目已有的 Prompt 门禁和测试，不真实调用 LLM 或外部厂商。

## 变更前

1. 阅读根目录 `AGENTS.md`、`prompts/AGENTS.md` 和 `docs/yaml_prompt_optimization_checklist.md`；涉及其他目录时继续遵循对应的嵌套 `AGENTS.md`。
2. 检查当前 `git status` 和相关 diff，保留与任务无关的用户修改。
3. 沿 `prompts/`、Manifest 和 `prompt_engine/` 追踪实际加载与路由链路，并与 `HEAD` 对比。明确受影响的 `project_type`、`prompt_version`、`video_model_name`、`user_preference` 组合以及失败或回退路径。
4. 记录变更前的契约：模板占位符、必填字段、输出 Schema、语言要求、格式和下游消费者。信息不足时先从代码和测试中确认，不臆测契约。

## 实施变更

- 只修改完成目标所需的模板、Manifest、路由、测试或文档，不顺带统一无关版本、客户包或模型目录。
- 不静默改变版本、模型路由、回退行为、占位符、输出 Schema 或语言契约；如果任务确实要求改变，应同步更新消费者、文档和契约测试，并在交付说明中明确指出兼容性影响。
- 修改 Manifest 或路由时，同步检查目标 YAML 和对应的版本/模型路由测试。保持默认 Prompt 与客户定制 Prompt 物理隔离，不引入跨版本、跨模型或跨 Prompt 包的隐式回退。
- 将字段、JSON 结构、语言、示例或格式变化视为接口契约变化。检查最终渲染结果，而不只检查 YAML 文本。
- Bug 修复增加能够复现原问题的回归用例；新增行为覆盖新分支和失败路径。测试只渲染或校验 Prompt，并 Mock 外部服务。

## 验证

1. 每次修改 Prompt/YAML 都运行：

   ```text
   ./prompt-gate.cmd
   ```

2. 再运行范围最小的相关功能或契约测试：

   - 视频模型、版本或 Manifest 路由：`conda run --no-capture-output -n kino python -m pytest tests/test_video_model_prompt_profiles.py -q`
   - 语言隔离或语言字段：`conda run --no-capture-output -n kino python -m pytest tests/unit/test_language_separation.py -q`
   - 其他输出契约：选择对应的 `tests/unit/test_*_prompt_contract.py`；没有覆盖时先补契约或快照测试。

3. 变更横跨多个模块、影响路由或 Schema，或者需要项目级收尾时，运行 `./verify.cmd`。`./verify.cmd --quick` 只能确认环境和测试发现，不能替代相关测试。
4. 仅在清理历史 YAML 格式问题或发布前全量扫描时额外运行：

   ```text
   conda run --no-capture-output -n kino python scripts/check_yaml_format.py --strict
   ```

门禁失败时修复 Prompt、路由、回归数据或契约测试。不得降低阈值、删除失败用例、放宽高风险规则或跳过检查来制造通过结果。除非用户明确授权，不安装依赖、不启动服务、不真实调用模型或厂商 API。

## 交付说明

说明以下内容：

- 修改的 Prompt、Manifest、路由、测试和文档，以及受影响的版本、模型和用户偏好组合。
- 占位符、输出 Schema、语言或回退行为是否发生变化，以及兼容性结论。
- 实际执行的命令、结果、警告和未执行的检查。

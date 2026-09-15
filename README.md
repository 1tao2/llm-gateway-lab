# LLM Gateway Lab

面向 FDE 学习与实践的、可靠性导向的多供应商 LLM 网关。

当前完成 Phase 0：FastAPI 工程骨架、统一配置、健康检查与自动化测试。此阶段不需要智谱 API Key，也不会产生模型调用费用。

## 环境要求

- Python 3.11+
- Git
- Windows PowerShell

## 初始化

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

如果系统的 `python` 命令不可用，但已安装 Conda，可使用以下命令创建虚拟环境：

```powershell
conda run -n base python -m venv .venv
```

## 运行测试

```powershell
.\.venv\Scripts\python -m pytest -v
```

## 启动服务

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

启动后访问：

- 健康检查：http://127.0.0.1:8000/health
- Swagger：http://127.0.0.1:8000/docs

健康检查响应：

```json
{"status":"ok"}
```

## 配置

配置统一定义在 `app/config.py`，本地值放在 `.env`。`.env` 已被 Git 忽略，不要在代码、README、日志或提交历史中保存真实 API Key。

智谱相关变量已在 `.env.example` 中预留，但 Phase 0 不读取或要求这些变量；它们将在 Phase 1 接入真实 Provider 时启用。

## 常见问题

- `python` 不存在：安装 Python 3.11+，并在安装时启用 Add Python to PATH；已有 Conda 时也可使用上面的 Conda 命令。
- 无法运行激活脚本：无需激活虚拟环境，直接使用 `.\.venv\Scripts\python`。
- 端口 8000 被占用：启动命令追加 `--port 8001`，并访问对应端口。
- 配置加载失败：核对 `.env` 中的变量名和值；`APP_ENV` 只接受 `local`、`test` 或 `production`，`PORT` 必须在 1–65535 之间。
- 配置文件不存在：运行 `Copy-Item .env.example .env`；Phase 0 即使没有 `.env` 也能使用安全默认值启动。
- PowerShell 显示中文乱码：使用 `Get-Content -Encoding UTF8 <文件路径>`。

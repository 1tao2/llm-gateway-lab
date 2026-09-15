class ProviderError(Exception):
    """供应商边界的安全异常，仅公开固定类别消息与诊断上下文。"""

    safe_message = "provider operation failed"

    def __init__(
        self,
        *,
        provider: str,
        status_code: int | None = None,
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        context = f"provider={provider}"
        if status_code is not None:
            context = f"{context}, status_code={status_code}"
        super().__init__(f"{self.safe_message} ({context})")


class ProviderAuthenticationError(ProviderError):
    """供应商拒绝身份认证。"""

    safe_message = "provider authentication failed"


class ProviderRateLimitError(ProviderError):
    """供应商触发请求限流。"""

    safe_message = "provider rate limit exceeded"


class ProviderServerError(ProviderError):
    """供应商服务端处理失败。"""

    safe_message = "provider server error"


class ProviderTimeoutError(ProviderError):
    """供应商请求超时。"""

    safe_message = "provider request timed out"


class ProviderConnectionError(ProviderError):
    """无法连接到供应商。"""

    safe_message = "provider connection failed"


class ProviderInvalidResponseError(ProviderError):
    """供应商成功响应无法归一化。"""

    safe_message = "provider returned an invalid response"


class ProviderConfigurationError(ProviderError):
    """供应商配置缺失或非法。"""

    safe_message = "provider configuration is invalid"


class ProviderRequestError(ProviderError):
    """供应商拒绝了非认证、非限流的客户端请求。"""

    safe_message = "provider request failed"

class ProviderError(Exception):
    """供应商边界的安全异常，仅保留已脱敏消息与诊断上下文。"""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class ProviderAuthenticationError(ProviderError):
    """供应商拒绝身份认证。"""


class ProviderRateLimitError(ProviderError):
    """供应商触发请求限流。"""


class ProviderServerError(ProviderError):
    """供应商服务端处理失败。"""


class ProviderTimeoutError(ProviderError):
    """供应商请求超时。"""


class ProviderConnectionError(ProviderError):
    """无法连接到供应商。"""


class ProviderInvalidResponseError(ProviderError):
    """供应商成功响应无法归一化。"""


class ProviderConfigurationError(ProviderError):
    """供应商配置缺失或非法。"""


class ProviderRequestError(ProviderError):
    """供应商拒绝了非认证、非限流的客户端请求。"""

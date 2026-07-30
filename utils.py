"""Validation and provider-health-check helpers."""

import json
from urllib.parse import urlparse

import requests


class ValidationError(ValueError):
    """Raised when user-supplied configuration is invalid."""


def parse_json_object(value, field_name):
    """Parse a non-empty JSON object, treating blank input as an empty object."""
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValidationError("%s 不是有效 JSON：%s" % (field_name, error.msg)) from error
    if not isinstance(parsed, dict):
        raise ValidationError("%s 必须是 JSON 对象。" % field_name)
    return parsed


def validate_url(value):
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValidationError("Base URL 必须是有效的 http:// 或 https:// 地址。")
    return value


def validate_positive_int(value, field_name, allow_zero=False):
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError("%s 必须是整数。" % field_name) from error
    if number < 0 or (number == 0 and not allow_zero):
        raise ValidationError("%s 必须大于%s 0。" % (field_name, "或等于" if allow_zero else ""))
    return number


def build_models_url(base_url):
    """Build Pi-compatible provider health endpoint from a base API URL."""
    base_url = validate_url(base_url)
    parsed = urlparse(base_url)
    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        path = (path + "/v1") if path else "/v1"
    return parsed._replace(path=path + "/models", params="", query="", fragment="").geturl()


def build_request_headers(provider):
    """Build provider request headers with custom headers taking precedence."""
    headers = {}
    api_key = provider.get("apiKey", "")
    if api_key:
        headers["Authorization"] = "Bearer " + str(api_key)
    custom_headers = provider.get("headers", {})
    if isinstance(custom_headers, dict):
        headers.update({str(key): str(value) for key, value in custom_headers.items()})
    return headers


def _response_detail(response, fallback):
    detail = response.text.strip().replace("\n", " ")[:500]
    return detail or fallback


def test_provider_connection(provider):
    """Request the provider models endpoint and return (success, message)."""
    try:
        url = build_models_url(provider.get("baseUrl", ""))
        response = requests.get(url, headers=build_request_headers(provider), timeout=10)
        if response.ok:
            return True, "连接成功（HTTP %s）：%s" % (response.status_code, url)
        return False, "连接失败（HTTP %s）：%s" % (
            response.status_code,
            _response_detail(response, url),
        )
    except requests.RequestException as error:
        return False, "连接请求失败：%s" % error
    except ValidationError as error:
        return False, str(error)


def fetch_provider_models(provider):
    """Fetch and normalize model IDs from an OpenAI-compatible /models response."""
    try:
        url = build_models_url(provider.get("baseUrl", ""))
        response = requests.get(url, headers=build_request_headers(provider), timeout=10)
        if not response.ok:
            return False, "获取模型列表失败（HTTP %s）：%s" % (
                response.status_code,
                _response_detail(response, url),
            )
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as error:
            return False, "模型列表响应不是有效 JSON：%s" % error
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return False, "模型列表响应格式无效：需要包含 data 数组。"
        model_ids = {
            item.get("id").strip()
            for item in payload["data"]
            if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("id").strip()
        }
        return True, sorted(model_ids, key=str.casefold)
    except requests.RequestException as error:
        return False, "获取模型列表请求失败：%s" % error
    except ValidationError as error:
        return False, str(error)

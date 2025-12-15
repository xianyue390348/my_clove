import os
import json
import re
import time
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from loguru import logger

from app.dependencies.auth import AdminAuthDep
from app.core.config import settings
from app.core.http_client import create_session


class ProxyCreate(BaseModel):
    """Model for creating a proxy."""

    url: str = Field(..., description="SOCKS5 proxy URL (e.g., socks5://user:pass@host:port)")

    @field_validator("url")
    def validate_proxy_url(cls, v: str) -> str:
        """Validate proxy URL format."""
        # Basic validation for SOCKS5 proxy format
        pattern = r"^socks5://[\w.-]+(?::[\w.-]+)?@[\w.-]+:\d+$"
        if not re.match(pattern, v):
            raise ValueError(
                "Invalid proxy URL format. Expected: socks5://user:pass@host:port"
            )
        return v


class ProxyResponse(BaseModel):
    """Model for proxy response."""

    index: int
    url: str
    masked_url: str = Field(..., description="URL with masked credentials")


class ProxyTestResult(BaseModel):
    """Model for proxy test result."""

    success: bool
    response_time: Optional[float] = None  # Response time in seconds
    error: Optional[str] = None
    status_code: Optional[int] = None


router = APIRouter()


def mask_proxy_url(url: str) -> str:
    """Mask credentials in proxy URL for display.

    Args:
        url: Full proxy URL with credentials

    Returns:
        URL with masked credentials (e.g., socks5://***:***@host:port)
    """
    # Extract parts using regex
    match = re.match(r"^(socks5://)([\w.-]+):([\w.-]+)@([\w.-]+:\d+)$", url)
    if match:
        protocol, username, password, host_port = match.groups()
        return f"{protocol}***:***@{host_port}"
    return url  # Return as-is if format doesn't match


@router.get("", response_model=List[ProxyResponse])
async def list_proxies(_: AdminAuthDep):
    """List all proxies in the pool."""
    proxies = []

    for index, proxy_url in enumerate(settings.proxy_pool):
        proxies.append(
            ProxyResponse(
                index=index, url=proxy_url, masked_url=mask_proxy_url(proxy_url)
            )
        )

    logger.info(f"Listed {len(proxies)} proxies from pool")
    return proxies


@router.post("", response_model=ProxyResponse)
async def add_proxy(proxy_data: ProxyCreate, _: AdminAuthDep):
    """Add a new proxy to the pool."""
    # Add to in-memory settings
    if proxy_data.url in settings.proxy_pool:
        logger.warning(f"Attempted to add duplicate proxy: {mask_proxy_url(proxy_data.url)}")
        raise HTTPException(status_code=400, detail="Proxy already exists in pool")

    settings.proxy_pool.append(proxy_data.url)
    logger.info(f"Added new proxy to pool: {mask_proxy_url(proxy_data.url)} (total: {len(settings.proxy_pool)})")

    # Save to config file
    if not settings.no_filesystem_mode:
        config_path = settings.data_folder / "config.json"
        settings.data_folder.mkdir(parents=True, exist_ok=True)

        # Load existing config
        config_data = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                config_data = {}

        # Update proxy_pool
        config_data["proxy_pool"] = settings.proxy_pool

        # Save config
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)
            logger.debug(f"Saved proxy pool configuration to {config_path}")
        except IOError as e:
            logger.error(f"Failed to save proxy pool config: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to save config: {str(e)}"
            )

    index = len(settings.proxy_pool) - 1
    return ProxyResponse(
        index=index, url=proxy_data.url, masked_url=mask_proxy_url(proxy_data.url)
    )


@router.delete("/{index}")
async def delete_proxy(index: int, _: AdminAuthDep):
    """Delete a proxy from the pool by index."""
    if index < 0 or index >= len(settings.proxy_pool):
        logger.warning(f"Attempted to delete non-existent proxy at index {index}")
        raise HTTPException(status_code=404, detail="Proxy not found")

    removed_proxy = settings.proxy_pool.pop(index)
    logger.info(f"Removed proxy from pool: {mask_proxy_url(removed_proxy)} (remaining: {len(settings.proxy_pool)})")

    # Save to config file
    if not settings.no_filesystem_mode:
        config_path = settings.data_folder / "config.json"
        settings.data_folder.mkdir(parents=True, exist_ok=True)

        # Load existing config
        config_data = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                config_data = {}

        # Update proxy_pool
        config_data["proxy_pool"] = settings.proxy_pool

        # Save config
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)
            logger.debug(f"Updated proxy pool configuration in {config_path}")
        except IOError as e:
            logger.error(f"Failed to save proxy pool config after deletion: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to save config: {str(e)}"
            )

    return {"message": "Proxy deleted successfully", "removed_url": mask_proxy_url(removed_proxy)}


@router.post("/{index}/test", response_model=ProxyTestResult)
async def test_proxy(index: int, _: AdminAuthDep):
    """Test a proxy by making a request to Google."""
    if index < 0 or index >= len(settings.proxy_pool):
        logger.warning(f"Attempted to test non-existent proxy at index {index}")
        raise HTTPException(status_code=404, detail="Proxy not found")

    proxy_url = settings.proxy_pool[index]
    masked_url = mask_proxy_url(proxy_url)

    logger.info(f"Testing proxy {index}: {masked_url}")

    start_time = time.time()

    try:
        # Create session with the specific proxy
        session = create_session(
            proxy=proxy_url,
            timeout=10,  # 10 second timeout for test
            impersonate="chrome",
            follow_redirects=True,
        )

        # Make a test request to Google
        response = await session.request(
            method="GET",
            url="https://www.google.com",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )

        response_time = time.time() - start_time

        await session.close()

        if response.status_code == 200:
            logger.info(f"Proxy {index} test successful: {response_time:.2f}s")
            return ProxyTestResult(
                success=True,
                response_time=round(response_time, 2),
                status_code=response.status_code
            )
        else:
            logger.warning(f"Proxy {index} returned status {response.status_code}")
            return ProxyTestResult(
                success=False,
                response_time=round(response_time, 2),
                status_code=response.status_code,
                error=f"HTTP {response.status_code}"
            )

    except Exception as e:
        response_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"Proxy {index} test failed after {response_time:.2f}s: {error_msg}")

        # Simplify error message for display
        if "TimeoutError" in error_msg or "TimedOut" in error_msg:
            error_display = "连接超时"
        elif "ConnectionError" in error_msg or "Connection" in error_msg:
            error_display = "连接失败"
        elif "SSL" in error_msg or "TLS" in error_msg:
            error_display = "SSL/TLS 错误"
        else:
            error_display = "请求失败"

        return ProxyTestResult(
            success=False,
            response_time=round(response_time, 2) if response_time < 10 else None,
            error=error_display
        )

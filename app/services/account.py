import asyncio
from datetime import datetime, UTC
from typing import List, Optional, Dict, Set

from collections import defaultdict
from loguru import logger
import threading
import json
import uuid

from app.core.config import settings
from app.core.exceptions import NoAccountsAvailableError
from app.core.account import Account, AccountStatus, AuthType, OAuthToken
from app.services.oauth import oauth_authenticator


class AccountManager:
    """
    Singleton manager for Claude.ai accounts with load balancing and rate limit recovery.
    Supports both cookie and OAuth authentication.
    """

    _instance: Optional["AccountManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        """Implement singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the AccountManager."""
        self._accounts: Dict[str, Account] = {}  # organization_uuid -> Account
        self._cookie_to_uuid: Dict[str, str] = {}  # cookie_value -> organization_uuid
        self._session_accounts: Dict[str, str] = {}  # session_id -> organization_uuid
        self._account_sessions: Dict[str, Set[str]] = defaultdict(
            set
        )  # organization_uuid -> set of session_ids
        self._account_task: Optional[asyncio.Task] = None
        self._max_sessions_per_account = settings.max_sessions_per_cookie
        self._account_task_interval = settings.account_task_interval

        logger.info("AccountManager initialized")

    async def add_account(
        self,
        cookie_value: Optional[str] = None,
        oauth_token: Optional[OAuthToken] = None,
        organization_uuid: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
    ) -> Account:
        """Add a new account to the manager.

        Args:
            cookie_value: The cookie value (optional)
            oauth_token: The OAuth token (optional)
            organization_uuid: The organization UUID (optional, will be fetched or generated if not provided)
            capabilities: The account capabilities (optional)

        Raises:
            ValueError: If neither cookie_value nor oauth_token is provided
        """
        if not cookie_value and not oauth_token:
            raise ValueError("Either cookie_value or oauth_token must be provided")

        if cookie_value and cookie_value in self._cookie_to_uuid:
            return self._accounts[self._cookie_to_uuid[cookie_value]]

        if cookie_value and (not organization_uuid or not capabilities):
            (
                fetched_uuid,
                capabilities,
            ) = await oauth_authenticator.get_organization_info(cookie_value)
            if fetched_uuid:
                organization_uuid = fetched_uuid

        if organization_uuid and organization_uuid in self._accounts:
            existing_account = self._accounts[organization_uuid]

            if cookie_value and existing_account.cookie_value != cookie_value:
                if existing_account.cookie_value:
                    del self._cookie_to_uuid[existing_account.cookie_value]
                existing_account.cookie_value = cookie_value
                self._cookie_to_uuid[cookie_value] = organization_uuid
            return existing_account

        if not organization_uuid:
            organization_uuid = str(uuid.uuid4())
            logger.info(f"Generated new organization UUID: {organization_uuid}")

        # Create new account
        if cookie_value and oauth_token:
            auth_type = AuthType.BOTH
        elif cookie_value:
            auth_type = AuthType.COOKIE_ONLY
        else:
            auth_type = AuthType.OAUTH_ONLY

        account = Account(
            organization_uuid=organization_uuid,
            capabilities=capabilities,
            cookie_value=cookie_value,
            oauth_token=oauth_token,
            auth_type=auth_type,
        )
        self._accounts[organization_uuid] = account
        self.save_accounts()

        if cookie_value:
            self._cookie_to_uuid[cookie_value] = organization_uuid

        logger.info(
            f"Added new account: {organization_uuid[:8]}... "
            f"(auth_type: {auth_type.value}, "
            f"cookie: {cookie_value[:20] + '...' if cookie_value else 'None'}, "
            f"oauth: {'Yes' if oauth_token else 'No'})"
        )

        if auth_type == AuthType.COOKIE_ONLY:
            asyncio.create_task(self._attempt_oauth_authentication(account))

        return account

    async def remove_account(self, organization_uuid: str) -> None:
        """Remove an account from the manager."""
        if organization_uuid in self._accounts:
            account = self._accounts[organization_uuid]
            sessions_to_remove = list(
                self._account_sessions.get(organization_uuid, set())
            )

            for session_id in sessions_to_remove:
                if session_id in self._session_accounts:
                    del self._session_accounts[session_id]

            if account.cookie_value and account.cookie_value in self._cookie_to_uuid:
                del self._cookie_to_uuid[account.cookie_value]

            del self._accounts[organization_uuid]

            if organization_uuid in self._account_sessions:
                del self._account_sessions[organization_uuid]

            logger.info(f"Removed account: {organization_uuid[:8]}...")
            self.save_accounts()

    async def get_account_for_session(
        self,
        session_id: str,
        is_pro: Optional[bool] = None,
        is_max: Optional[bool] = None,
    ) -> Account:
        """
        Get an available account for the session with load balancing.

        Args:
            session_id: Unique identifier for the session
            is_pro: Filter by pro capability. None means any.
            is_max: Filter by max capability. None means any.

        Returns:
            Account instance if available
        """
        # Convert single auth_type to list for uniform handling
        if session_id in self._session_accounts:
            organization_uuid = self._session_accounts[session_id]
            if organization_uuid in self._accounts:
                account = self._accounts[organization_uuid]
                if account.status == AccountStatus.VALID:
                    return account
                else:
                    del self._session_accounts[session_id]
                    self._account_sessions[organization_uuid].discard(session_id)

        best_account = None
        min_sessions = float("inf")
        earliest_last_used = None

        for organization_uuid, account in self._accounts.items():
            if account.status != AccountStatus.VALID:
                continue

            # Filter by auth type if specified
            if account.auth_type not in [AuthType.BOTH, AuthType.COOKIE_ONLY]:
                continue

            # Filter by capabilities if specified
            if is_pro is not None and account.is_pro != is_pro:
                continue
            if is_max is not None and account.is_max != is_max:
                continue

            session_count = len(self._account_sessions[organization_uuid])
            if session_count >= self._max_sessions_per_account:
                continue

            # Select account with least sessions
            # If multiple accounts have the same least sessions, select the one with earliest last_used
            if session_count < min_sessions or (
                session_count == min_sessions
                and (
                    earliest_last_used is not None
                    and account.last_used < earliest_last_used
                )
            ):
                min_sessions = session_count
                earliest_last_used = account.last_used
                best_account = account

        if best_account:
            self._session_accounts[session_id] = best_account.organization_uuid
            self._account_sessions[best_account.organization_uuid].add(session_id)

            logger.debug(
                f"Assigned account to session {session_id}, "
                f"account now has {len(self._account_sessions[best_account.organization_uuid])} sessions"
            )

            return best_account

        raise NoAccountsAvailableError()

    async def get_account_for_oauth(
        self,
        is_pro: Optional[bool] = None,
        is_max: Optional[bool] = None,
    ) -> Account:
        """
        Get an available account for OAuth authentication.

        Args:
            is_pro: Filter by pro capability. None means any.
            is_max: Filter by max capability. None means any.

        Returns:
            Account instance if available
        """
        earliest_account = None
        earliest_last_used = None

        for account in self._accounts.values():
            if account.status != AccountStatus.VALID:
                continue

            if account.auth_type not in [AuthType.OAUTH_ONLY, AuthType.BOTH]:
                continue

            # Filter by capabilities if specified
            if is_pro is not None and account.is_pro != is_pro:
                continue
            if is_max is not None and account.is_max != is_max:
                continue

            if earliest_last_used is None or account.last_used < earliest_last_used:
                earliest_last_used = account.last_used
                earliest_account = account

        if earliest_account:
            logger.debug(
                f"Selected OAuth account: {earliest_account.organization_uuid[:8]}... "
                f"(last used: {earliest_account.last_used.isoformat()})"
            )
            return earliest_account

        raise NoAccountsAvailableError()

    async def get_account_by_id(self, account_id: str) -> Optional[Account]:
        """
        Get an account by its organization UUID.

        Args:
            account_id: The organization UUID of the account

        Returns:
            Account instance if found and valid, None otherwise
        """
        account = self._accounts.get(account_id)
        
        if account and account.status == AccountStatus.VALID:
            logger.debug(f"Retrieved account by ID: {account_id[:8]}...")
            return account
        
        if account:
            logger.debug(
                f"Account {account_id[:8]}... found but not valid: status={account.status}"
            )
        else:
            logger.debug(f"Account {account_id[:8]}... not found")
        
        return None

    async def test_account(self, organization_uuid: str) -> Dict:
        """
        Test an account to check if its credentials are still valid.

        Args:
            organization_uuid: The organization UUID of the account to test

        Returns:
            Dict with test results including success status, messages, and updated account info
        """
        if organization_uuid not in self._accounts:
            return {
                "success": False,
                "error": "Account not found",
            }

        account = self._accounts[organization_uuid]
        test_results = {
            "success": True,
            "cookie_valid": None,
            "oauth_valid": None,
            "error": None,
        }

        logger.info(f"Testing account: {organization_uuid[:8]}... (auth_type: {account.auth_type.value})")

        # Test cookie authentication if available
        if account.auth_type in [AuthType.COOKIE_ONLY, AuthType.BOTH] and account.cookie_value:
            try:
                org_uuid, capabilities = await oauth_authenticator.get_organization_info(
                    account.cookie_value
                )
                
                if org_uuid:
                    test_results["cookie_valid"] = True
                    # Update capabilities if they've changed
                    if capabilities and capabilities != account.capabilities:
                        account.capabilities = capabilities
                        logger.info(f"Updated capabilities for account {organization_uuid[:8]}...")
                    logger.info(f"Cookie authentication test passed for account {organization_uuid[:8]}...")
                else:
                    test_results["cookie_valid"] = False
                    test_results["success"] = False
                    test_results["error"] = "Failed to get organization info with cookie"
                    logger.warning(f"Cookie authentication test failed for account {organization_uuid[:8]}...")
                    
            except Exception as e:
                test_results["cookie_valid"] = False
                test_results["success"] = False
                test_results["error"] = f"Cookie test error: {str(e)}"
                logger.error(f"Cookie authentication test error for account {organization_uuid[:8]}...: {e}")

        # Test OAuth authentication if available
        if account.auth_type in [AuthType.OAUTH_ONLY, AuthType.BOTH] and account.oauth_token:
            try:
                current_timestamp = datetime.now(UTC).timestamp()
                
                # Check if token is expired or about to expire
                if account.oauth_token.expires_at - current_timestamp < 300:
                    logger.info(f"OAuth token expired or expiring soon for account {organization_uuid[:8]}..., attempting refresh")
                    refresh_success = await oauth_authenticator.refresh_account_token(account)
                    
                    if refresh_success:
                        test_results["oauth_valid"] = True
                        logger.info(f"OAuth token refresh successful for account {organization_uuid[:8]}...")
                    else:
                        test_results["oauth_valid"] = False
                        test_results["success"] = False
                        test_results["error"] = "Failed to refresh OAuth token"
                        logger.warning(f"OAuth token refresh failed for account {organization_uuid[:8]}...")
                else:
                    # Token is still valid
                    test_results["oauth_valid"] = True
                    logger.info(f"OAuth token is valid for account {organization_uuid[:8]}...")
                    
            except Exception as e:
                test_results["oauth_valid"] = False
                test_results["success"] = False
                test_results["error"] = f"OAuth test error: {str(e)}"
                logger.error(f"OAuth authentication test error for account {organization_uuid[:8]}...: {e}")

        # Update account status based on test results
        if test_results["success"]:
            account.status = AccountStatus.VALID
            account.resets_at = None
            logger.info(f"Account {organization_uuid[:8]}... test passed, status set to VALID")
        else:
            # Only mark as invalid if all auth methods failed
            if account.auth_type == AuthType.BOTH:
                # For BOTH type, only invalid if both methods failed
                if test_results["cookie_valid"] is False and test_results["oauth_valid"] is False:
                    account.status = AccountStatus.INVALID
                    logger.warning(f"Account {organization_uuid[:8]}... test failed, status set to INVALID")
                elif test_results["cookie_valid"] is False:
                    # Cookie failed but OAuth passed, downgrade to OAuth only
                    account.auth_type = AuthType.OAUTH_ONLY
                    account.cookie_value = None
                    test_results["success"] = True
                    test_results["error"] = "Cookie invalid, downgraded to OAuth only"
                    logger.info(f"Account {organization_uuid[:8]}... downgraded to OAuth only")
                elif test_results["oauth_valid"] is False:
                    # OAuth failed but Cookie passed, downgrade to Cookie only
                    account.auth_type = AuthType.COOKIE_ONLY
                    account.oauth_token = None
                    test_results["success"] = True
                    test_results["error"] = "OAuth invalid, downgraded to Cookie only"
                    logger.info(f"Account {organization_uuid[:8]}... downgraded to Cookie only")
            else:
                account.status = AccountStatus.INVALID
                logger.warning(f"Account {organization_uuid[:8]}... test failed, status set to INVALID")

        # Save updated account status
        self.save_accounts()

        return test_results

    def get_proxy_for_account(self, organization_uuid: str) -> Optional[str]:
        """Get assigned proxy for an account using modulo-based allocation.

        Uses stable ordering by organization_uuid to ensure consistent proxy assignment.
        Falls back to global proxy_url if no proxy pool is configured.

        Args:
            organization_uuid: The organization UUID of the account

        Returns:
            Proxy URL or None if no proxy configured
        """
        if not settings.proxy_pool:
            return settings.proxy_url  # Fallback to global proxy

        # Get account index (stable ordering by organization_uuid)
        account_list = sorted(self._accounts.keys())
        try:
            account_index = account_list.index(organization_uuid)
        except ValueError:
            logger.warning(
                f"Account {organization_uuid[:8]}... not found in account list, "
                "falling back to global proxy"
            )
            return settings.proxy_url

        # Modulo assignment
        proxy_index = account_index % len(settings.proxy_pool)
        assigned_proxy = settings.proxy_pool[proxy_index]

        logger.debug(
            f"Assigned proxy {proxy_index} to account {organization_uuid[:8]}... "
            f"(account_index={account_index}, pool_size={len(settings.proxy_pool)})"
        )

        return assigned_proxy

    async def release_session(self, session_id: str) -> None:
        """Release a session's account assignment."""
        if session_id in self._session_accounts:
            organization_uuid = self._session_accounts[session_id]
            del self._session_accounts[session_id]

            if organization_uuid in self._account_sessions:
                self._account_sessions[organization_uuid].discard(session_id)

            logger.debug(f"Released account for session {session_id}")

    async def start_task(self) -> None:
        """Start the background task for AccountManager."""
        if self._account_task is None or self._account_task.done():
            self._account_task = asyncio.create_task(self._task_loop())

    async def stop_task(self) -> None:
        """Stop the background task for AccountManager."""
        if self._account_task and not self._account_task.done():
            self._account_task.cancel()
            try:
                await self._account_task
            except asyncio.CancelledError:
                pass

    async def _task_loop(self) -> None:
        """Background loop for AccountManager."""
        while True:
            try:
                await self._check_and_recover_accounts()
                await self._check_and_refresh_accounts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in task loop: {e}")
            finally:
                await asyncio.sleep(self._account_task_interval)

    async def _check_and_recover_accounts(self) -> None:
        """Check and recover rate-limited accounts."""
        current_time = datetime.now(UTC)

        for account in self._accounts.values():
            # Check rate-limited accounts
            if (
                account.status == AccountStatus.RATE_LIMITED
                and account.resets_at
                and current_time >= account.resets_at
            ):
                account.status = AccountStatus.VALID
                account.resets_at = None
                logger.info(
                    f"Recovered rate-limited account: {account.organization_uuid[:8]}..."
                )

    async def _check_and_refresh_accounts(self) -> None:
        """Check and refresh expired/expiring tokens."""
        current_timestamp = datetime.now(UTC).timestamp()

        for account in self._accounts.values():
            if (
                account.auth_type in [AuthType.OAUTH_ONLY, AuthType.BOTH]
                and account.oauth_token
                and account.oauth_token.refresh_token
                and account.oauth_token.expires_at
            ):
                if account.oauth_token.expires_at - current_timestamp < 300:
                    asyncio.create_task(self._refresh_account_token(account))

    async def _refresh_account_token(self, account: Account) -> None:
        """Refresh OAuth token for an account."""
        logger.info(
            f"Refreshing OAuth token for account: {account.organization_uuid[:8]}..."
        )

        success = await oauth_authenticator.refresh_account_token(account)
        if success:
            logger.info(
                f"Successfully refreshed OAuth token for account: {account.organization_uuid[:8]}..."
            )
        else:
            logger.warning(
                f"Failed to refresh OAuth token for account: {account.organization_uuid[:8]}..."
            )
            if account.auth_type == AuthType.BOTH:
                account.auth_type = AuthType.COOKIE_ONLY
                account.oauth_token = None
            else:
                account.status = AccountStatus.INVALID
                logger.error(
                    f"Account {account.organization_uuid[:8]} is now invalid due to OAuth refresh failure"
                )
            self.save_accounts()

    async def _attempt_oauth_authentication(self, account: Account) -> None:
        """Attempt OAuth authentication for an account."""

        logger.info(
            f"Attempting OAuth authentication for account: {account.organization_uuid[:8]}..."
        )

        success = await oauth_authenticator.authenticate_account(account)
        if not success:
            logger.warning(
                f"OAuth authentication failed for account: {account.organization_uuid[:8]}..., keeping as CookieOnly"
            )
        else:
            logger.info(
                f"OAuth authentication successful for account: {account.organization_uuid[:8]}..."
            )

    async def get_status(self) -> Dict:
        """Get the current status of all accounts."""
        status = {
            "total_accounts": len(self._accounts),
            "valid_accounts": sum(
                1 for a in self._accounts.values() if a.status == AccountStatus.VALID
            ),
            "rate_limited_accounts": sum(
                1
                for a in self._accounts.values()
                if a.status == AccountStatus.RATE_LIMITED
            ),
            "invalid_accounts": sum(
                1 for a in self._accounts.values() if a.status == AccountStatus.INVALID
            ),
            "active_sessions": len(self._session_accounts),
            "accounts": [],
        }

        for organization_uuid, account in self._accounts.items():
            account_info = {
                "organization_uuid": organization_uuid[:8] + "...",
                "cookie": account.cookie_value[:20] + "..."
                if account.cookie_value
                else "None",
                "status": account.status.value,
                "auth_type": account.auth_type.value,
                "sessions": len(self._account_sessions[organization_uuid]),
                "last_used": account.last_used.isoformat(),
                "resets_at": account.resets_at.isoformat()
                if account.resets_at
                else None,
                "has_oauth": account.oauth_token is not None,
            }
            status["accounts"].append(account_info)

        return status

    def save_accounts(self) -> None:
        """Save all accounts to JSON file.

        Args:
            data_folder: Optional data folder path. If not provided, uses settings.data_folder
        """
        if settings.no_filesystem_mode:
            logger.debug("No-filesystem mode enabled, skipping account save to disk")
            return

        settings.data_folder.mkdir(parents=True, exist_ok=True)

        accounts_file = settings.data_folder / "accounts.json"

        accounts_data = {
            organization_uuid: account.to_dict()
            for organization_uuid, account in self._accounts.items()
        }

        with open(accounts_file, "w", encoding="utf-8") as f:
            json.dump(accounts_data, f, indent=2)

        logger.info(f"Saved {len(accounts_data)} accounts to {accounts_file}")

    def load_accounts(self) -> None:
        """Load accounts from JSON file.

        Args:
            data_folder: Optional data folder path. If not provided, uses settings.data_folder
        """
        if settings.no_filesystem_mode:
            logger.debug("No-filesystem mode enabled, skipping account load from disk")
            return

        accounts_file = settings.data_folder / "accounts.json"

        if not accounts_file.exists():
            logger.info(f"No accounts file found at {accounts_file}")
            return

        try:
            with open(accounts_file, "r", encoding="utf-8") as f:
                accounts_data = json.load(f)

            for organization_uuid, account_data in accounts_data.items():
                account = Account.from_dict(account_data)
                self._accounts[organization_uuid] = account

                # Rebuild cookie mapping
                if account.cookie_value:
                    self._cookie_to_uuid[account.cookie_value] = organization_uuid

            logger.info(f"Loaded {len(accounts_data)} accounts from {accounts_file}")

        except Exception as e:
            logger.error(f"Failed to load accounts from {accounts_file}: {e}")

    def __repr__(self) -> str:
        """String representation of the AccountManager."""
        return f"<AccountManager accounts={len(self._accounts)} sessions={len(self._session_accounts)}>"


account_manager = AccountManager()

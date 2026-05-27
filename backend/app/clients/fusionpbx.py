"""
FusionPBX API Client
Handles all communication with FusionPBX API endpoints
"""
import os
import logging
import json
import html as html_lib
import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import aiohttp
import asyncio
import base64
from urllib.parse import quote_plus

# Load environment variables from .env file (for non-Docker runs)
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), '.env')
    load_dotenv(env_path)
except ImportError:
    pass

logger = logging.getLogger(__name__)


class FusionPBXClient:
    """Client for FusionPBX API"""
    
    def __init__(self):
        self.host = os.getenv("FUSIONPBX_HOST", "https://pbx.example.com").rstrip('/')
        self.api_key = os.getenv("FUSIONPBX_API_KEY", "")
        self.verify_ssl = os.getenv("FUSIONPBX_VERIFY_SSL", "true").lower() == "true"
        self.wallboard_username = os.getenv("FUSIONPBX_WALLBOARD_USERNAME", "").strip()
        self.wallboard_password = os.getenv("FUSIONPBX_WALLBOARD_PASSWORD", "").strip()
        self.wallboard_cookie = os.getenv("FUSIONPBX_WALLBOARD_COOKIE", "").strip()
        self.wallboard_host = os.getenv("FUSIONPBX_WALLBOARD_HOST", "").strip().rstrip('/')
        self.wallboard_resource_path = os.getenv(
            "FUSIONPBX_WALLBOARD_RESOURCE_PATH",
            "/app/call_center_wallboard/resources/call_center_wallboard.php?queue_name=",
        )
        self.timeout = 30
        self.session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"FusionPBX Host: {self.host}")
        logger.info(f"API Key present: {bool(self.api_key)}")
        logger.info(f"SSL Verification: {self.verify_ssl}")
        
    async def initialize(self):
        """Initialize the HTTP session"""
        if self.session is None:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Basic {self.api_key}"  # API key should already be Base64 encoded
            }
            
            # Configure SSL verification
            connector = None
            if not self.verify_ssl:
                import ssl
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                connector = aiohttp.TCPConnector(ssl=ssl_context)
                logger.warning("SSL certificate verification is DISABLED")
            
            self.session = aiohttp.ClientSession(headers=headers, connector=connector)

    async def get_wallboard_live_snapshot(self) -> Optional[Dict[str, Any]]:
        """Try to fetch the same wallboard payload FusionPBX uses for the live wallboard page."""
        resource_url = self._build_wallboard_resource_url()
        if not resource_url:
            return None

        # Attempt with the existing API-key session first. Some deployments allow this.
        direct_payload = await self._fetch_wallboard_payload_from_session(self.session, resource_url)
        normalized = self._normalize_wallboard_payload(direct_payload)
        if normalized:
            return normalized

        # Cookie fallback: allow reuse of an authenticated Fusion web session.
        cookie_header = self._build_wallboard_cookie_header()
        if cookie_header:
            headers = {
                "Accept": "text/html,application/json,*/*",
                "User-Agent": "FusionPBXReports/1.0",
                "Cookie": cookie_header,
            }
            connector = None
            if not self.verify_ssl:
                import ssl
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                connector = aiohttp.TCPConnector(ssl=ssl_context)

            try:
                async with aiohttp.ClientSession(headers=headers, connector=connector) as cookie_session:
                    cookie_payload = await self._fetch_wallboard_payload_from_session(cookie_session, resource_url)
                    normalized = self._normalize_wallboard_payload(cookie_payload)
                    if normalized:
                        return normalized
                    logger.warning("Fusion wallboard cookie fallback failed: cookie did not return wallboard payload")
            except Exception as exc:
                logger.warning("Fusion wallboard cookie fallback failed: %s", exc)

        # If direct access fails, try a web-session login for true 1:1 wallboard access.
        if not (self.wallboard_username and self.wallboard_password):
            logger.info("Fusion wallboard web credentials are not configured; skipping session login fallback")
            return None

        login_base = self.wallboard_host or self.host
        login_url = f"{login_base}/login.php"
        headers = {
            "Accept": "text/html,application/json,*/*",
            "User-Agent": "FusionPBXReports/1.0",
        }
        connector = None
        if not self.verify_ssl:
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)

        try:
            async with aiohttp.ClientSession(headers=headers, connector=connector) as web_session:
                async with web_session.get(login_url, timeout=self.timeout, ssl=False) as login_page_response:
                    _ = await login_page_response.text()

                login_form = {
                    "username": self.wallboard_username,
                    "password": self.wallboard_password,
                }
                async with web_session.post(
                    login_url,
                    data=login_form,
                    allow_redirects=True,
                    timeout=self.timeout,
                    ssl=False,
                ) as login_response:
                    login_text = await login_response.text()

                if self._looks_like_login_page(login_text):
                    logger.warning("Fusion wallboard login fallback failed: still on login page")
                    return None

                wallboard_payload = await self._fetch_wallboard_payload_from_session(web_session, resource_url)
                normalized = self._normalize_wallboard_payload(wallboard_payload)
                if normalized:
                    return normalized

        except Exception as exc:
            logger.warning("Fusion wallboard session fetch failed: %s", exc)

        return None

    async def _fetch_wallboard_payload_from_session(
        self,
        session: Optional[aiohttp.ClientSession],
        resource_url: str,
    ) -> Optional[Any]:
        if session is None:
            return None
        try:
            async with session.get(resource_url, timeout=self.timeout, ssl=False) as response:
                text = await response.text()
                if response.status != 200 or not text:
                    return None
                return self._decode_wallboard_payload(text)
        except Exception as exc:
            logger.warning("Fusion wallboard payload request failed: %s", exc)
            return None

    def _build_wallboard_resource_url(self) -> Optional[str]:
        path = (self.wallboard_resource_path or "").strip()
        if not path:
            return None
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        base = self.wallboard_host or self.host
        return f"{base}{path}"

    def _build_wallboard_cookie_header(self) -> Optional[str]:
        raw_cookie = (self.wallboard_cookie or "").strip()
        if not raw_cookie:
            return None
        # Accept either full cookie header value (k=v; k2=v2) or bare PHPSESSID token.
        if "=" in raw_cookie:
            return raw_cookie
        return f"PHPSESSID={raw_cookie}"

    def _looks_like_login_page(self, html_text: str) -> bool:
        lowered = (html_text or "").lower()
        return "<title>login</title>" in lowered or "name='username'" in lowered or 'name="username"' in lowered

    def _decode_wallboard_payload(self, payload_text: str) -> Optional[Any]:
        text = (payload_text or "").strip()
        if not text or self._looks_like_login_page(text):
            return None

        # Try direct JSON first.
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Some Fusion pages embed JSON in script tags. Try to extract a likely object/array.
        candidates = re.findall(r"(\{\s*\"(?:queues|agents|rows|data)\"[\s\S]*?\}|\[[\s\S]*\])", text)
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        if "grid-container" in text and "hud_box" in text:
            parsed_html = self._parse_wallboard_html(text)
            if parsed_html:
                return parsed_html

        return None

    def _parse_wallboard_html(self, html_text: str) -> Optional[Dict[str, Any]]:
        queue_items: List[Dict[str, Any]] = []
        agent_items: List[Dict[str, Any]] = []

        card_blocks = re.findall(
            r'<div class="col-md-12 hud_box"[^>]*>(.*?)</div>\s*</div>\s*</div>',
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        for block in card_blocks:
            title_text = self._extract_span_text(block, "hud_title")
            stat_text = self._extract_span_text(block, "hud_stat")
            stat_title_text = self._extract_span_text(block, "hud_stat_title")

            if not title_text:
                continue

            normalized_title = title_text.strip()
            if normalized_title.lower() in {"date and time", "average talk time", "average wait time"}:
                continue

            if "last change" in stat_title_text.lower():
                agent_name = self._first_non_empty_line(stat_text)
                agent_answered = self._first_int(stat_title_text, default=0)
                last_change_text = self._extract_last_change_text(stat_title_text)
                agent_items.append(
                    {
                        "agent_id": self._second_non_empty_line(stat_text) or agent_name,
                        "agent_name": agent_name or "Unknown Agent",
                        "state": normalized_title,
                        "answered": agent_answered,
                        "last_change_seconds": self._duration_to_seconds(last_change_text),
                    }
                )
                continue

            if "answered" in stat_title_text.lower() and "trying" in stat_title_text.lower() and "abandoned" in stat_title_text.lower():
                queue_extension, queue_name = self._parse_queue_title(normalized_title)
                answered = self._extract_labeled_int(stat_title_text, "Answered", default=0)
                trying = self._extract_labeled_int(stat_title_text, "Trying", default=0)
                abandoned = self._extract_labeled_int(stat_title_text, "Abandoned", default=0)
                queue_items.append(
                    {
                        "queue_id": queue_extension or queue_name,
                        "queue_extension": queue_extension,
                        "queue_name": queue_name,
                        "trying": trying,
                        "answered": answered,
                        "abandoned": abandoned,
                        "talk_time_seconds": 0,
                        "wait_time_seconds": 0,
                    }
                )

        if not queue_items and not agent_items:
            return None

        return {"queues": queue_items, "agents": agent_items, "source": "fusion_wallboard_html"}

    def _extract_span_text(self, block: str, class_name: str) -> str:
        match = re.search(rf'<span class="{re.escape(class_name)}"[^>]*>(.*?)</span>', block, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        value = match.group(1)
        value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
        value = re.sub(r"<[^>]+>", "", value)
        value = html_lib.unescape(value)
        value = value.replace("\xa0", " ")
        value = re.sub(r"[ \t]+", " ", value)
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        return "\n".join(lines).strip()

    def _first_non_empty_line(self, text: str) -> str:
        for line in (text or "").splitlines():
            line = line.strip()
            if line:
                return line
        return ""

    def _second_non_empty_line(self, text: str) -> str:
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        return lines[1] if len(lines) > 1 else ""

    def _first_int(self, text: str, default: int = 0) -> int:
        match = re.search(r"(-?\d+)", text or "")
        if not match:
            return default
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return default

    def _extract_labeled_int(self, text: str, label: str, default: int = 0) -> int:
        match = re.search(rf"(\d+)\s+{re.escape(label)}", text or "", flags=re.IGNORECASE)
        if not match:
            return default
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return default

    def _extract_last_change_text(self, text: str) -> str:
        match = re.search(r"([0-9:]+)\s+Last Change", text or "", flags=re.IGNORECASE)
        return match.group(1) if match else ""

    def _duration_to_seconds(self, duration: str) -> Optional[int]:
        value = (duration or "").strip()
        if not value:
            return None
        parts = value.split(":")
        try:
            if len(parts) == 3:
                hours, minutes, seconds = (int(part) for part in parts)
                return hours * 3600 + minutes * 60 + seconds
            if len(parts) == 2:
                minutes, seconds = (int(part) for part in parts)
                return minutes * 60 + seconds
            return int(value)
        except (TypeError, ValueError):
            return None

    def _parse_queue_title(self, title: str) -> tuple[str, str]:
        cleaned = (title or "").replace("\u00a0", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        match = re.match(r"^(\d+)\s+(.*)$", cleaned)
        if match:
            return match.group(1), match.group(2).strip()
        return "", cleaned

    def _normalize_wallboard_payload(self, payload: Optional[Any]) -> Optional[Dict[str, Any]]:
        if payload is None:
            return None

        queue_items = self._extract_list(payload, ["queues", "queue_rows", "rows", "queue_data", "call_center_queues"])
        agent_items = self._extract_list(payload, ["agents", "agent_rows", "members", "agent_data", "call_center_agents"])

        if not queue_items and not agent_items and isinstance(payload, list):
            queue_items = payload

        if not queue_items and not agent_items:
            return None

        normalized_queues: List[Dict[str, Any]] = []
        for queue in queue_items:
            if not isinstance(queue, dict):
                continue
            queue_extension = self._coalesce(queue, ["queue_extension", "extension", "queue", "name"], "")
            queue_name = self._coalesce(queue, ["queue_name", "name", "queue", "queue_label"], "Unknown Queue")
            normalized_queues.append(
                {
                    "queue_id": self._coalesce(queue, ["queue_id", "queue_uuid", "call_center_queue_uuid"], queue_extension or queue_name),
                    "queue_extension": str(queue_extension or ""),
                    "queue_name": str(queue_name or "Unknown Queue"),
                    "trying": self._to_int(self._coalesce(queue, ["trying", "waiting", "members_waiting"], 0)),
                    "answered": self._to_int(self._coalesce(queue, ["answered", "handled", "members_handled"], 0)),
                    "abandoned": self._to_int(self._coalesce(queue, ["abandoned", "abandon", "members_abandoned"], 0)),
                    "talk_time_seconds": self._to_int(self._coalesce(queue, ["talk_time_seconds", "talk_time", "talk_seconds"], 0)),
                    "wait_time_seconds": self._to_int(self._coalesce(queue, ["wait_time_seconds", "wait_time", "wait_seconds"], 0)),
                }
            )

        normalized_agents: List[Dict[str, Any]] = []
        for agent in agent_items:
            if not isinstance(agent, dict):
                continue
            last_change_raw = self._coalesce(agent, ["last_change_seconds", "last_change", "time_in_state_seconds"], None)
            normalized_agents.append(
                {
                    "agent_id": str(self._coalesce(agent, ["agent_id", "agent_uuid", "call_center_agent_uuid"], "")),
                    "agent_name": str(self._coalesce(agent, ["agent_name", "name"], "Unknown Agent")),
                    "state": str(self._coalesce(agent, ["state", "status", "agent_status"], "Waiting")),
                    "answered": self._to_int(self._coalesce(agent, ["answered", "calls_answered", "answered_count"], 0)),
                    "last_change_seconds": self._to_int(last_change_raw) if last_change_raw not in (None, "") else None,
                }
            )

        if not normalized_queues and not normalized_agents:
            return None

        return {
            "queues": normalized_queues,
            "agents": normalized_agents,
            "source": "fusion_wallboard",
        }

    def _extract_list(self, payload: Any, keys: List[str]) -> List[Any]:
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    def _coalesce(self, data: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
        for key in keys:
            value = data.get(key)
            if value not in (None, ""):
                return value
        return default

    def _to_int(self, value: Any, default: int = 0) -> int:
        try:
            if value in (None, ""):
                return default
            return int(float(value))
        except (TypeError, ValueError):
            return default
            
    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def get_queues(self) -> List[Dict[str, Any]]:
        """Fetch all call center queues"""
        try:
            url = f"{self.host}/app/api/7/call_center_queues"
            
            # Don't pass order_by - let the API use its default
            params = {}
            
            query_string = self._build_query_string(params)
            full_url = f"{url}?{query_string}" if params else url
            logger.info(f"Requesting Queues: {full_url}")
            
            async with self.session.get(url, params=params, timeout=self.timeout, ssl=False) as response:
                logger.info(f"Queues Response status: {response.status}")
                
                text = await response.text()
                logger.info(f"Queues response (first 1000 chars): {text[:1000]}")
                
                if response.status != 200:
                    logger.error(f"Error fetching queues: {response.status} - {text[:500]}")
                    return []
                
                if not text:
                    logger.warning("Empty response from Queues API")
                    return []
                
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse queues JSON: {e}")
                    return []
            
            # Check for error response
            if isinstance(data, dict) and ('code' in data or 'message' in data):
                logger.error(f"API Error Response: {data}")
                return []
            
            queues = []
            items = data if isinstance(data, list) else data.get('call_center_queues', [])
            
            for item in items:
                queue = {
                    "queue_uuid": item.get('call_center_queue_uuid'),
                    "queue_name": item.get('queue_name'),
                    "queue_extension": item.get('queue_extension'),
                    "queue_description": item.get('queue_description'),
                    "queue_enabled": True  # FusionPBX doesn't return this field
                }
                queues.append(queue)
            
            logger.info(f"Parsed {len(queues)} queues")
            return queues
                
        except Exception as e:
            logger.error(f"Exception fetching queues: {type(e).__name__}: {e}", exc_info=True)
            return []
    
    async def get_agents(self) -> List[Dict[str, Any]]:
        """Fetch all call center agents"""
        try:
            url = f"{self.host}/app/api/7/call_center_agents"
            
            params = {
                # "order_by": "start_epoch desc"  # Don't pass order_by - let the API use its default
            }
            
            async with self.session.get(url, params=params, timeout=self.timeout, ssl=False) as response:
                logger.info(f"Agents Response status: {response.status}")
                
                text = await response.text()
                logger.info(f"Agents response (first 1000 chars): {text[:1000]}")
                
                if response.status != 200:
                    logger.error(f"Error fetching agents: {response.status} - {text[:500]}")
                    return []
                
                if not text:
                    logger.warning("Empty response from Agents API")
                    return []
                
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse agents JSON: {e}")
                    return []
            
            # Check for error response
            if isinstance(data, dict) and ('code' in data or 'message' in data):
                logger.error(f"API Error Response: {data}")
                return []
            
            agents = []
            items = data if isinstance(data, list) else data.get('call_center_agents', [])
            
            for item in items:
                agent = {
                    "agent_uuid": item.get('call_center_agent_uuid'),
                    "agent_name": item.get('agent_name'),
                    "agent_extension": item.get('agent_id'),  # agent_id is the extension
                    "agent_contact": item.get('agent_contact'),
                    "agent_enabled": True  # FusionPBX doesn't return this field
                }
                agents.append(agent)
            
            logger.info(f"Parsed {len(agents)} agents")
            return agents
                
        except Exception as e:
            logger.error(f"Exception fetching agents: {type(e).__name__}: {e}", exc_info=True)
            return []
    
    async def get_xml_cdr(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Fetch CDR records"""
        try:
            url = f"{self.host}/app/api/7/xml_cdr"
            
            # Build query string manually to avoid encoding square brackets
            query_parts = [
                f"limit={limit}",
                f"offset={offset}"
            ]
            
            # Use start_stamp[] as an array range [start, end]
            if start_date:
                start_value = quote_plus(start_date.strftime('%Y-%m-%d %H:%M:%S'))
                query_parts.append(f"start_stamp[]={start_value}")
            if end_date:
                end_value = quote_plus(end_date.strftime('%Y-%m-%d %H:%M:%S'))
                query_parts.append(f"start_stamp[]={end_value}")
            
            query_string = "&".join(query_parts)
            full_url = f"{url}?{query_string}"
            # print(full_url)
            logger.info(f"Requesting CDR: {full_url}")
            
            async with self.session.get(full_url, timeout=self.timeout, ssl=False) as response:
                logger.info(f"CDR Response status: {response.status}")
                
                text = await response.text()
                logger.info(f"Response text (first 1000 chars): {text[:1000]}")
                
                if response.status != 200:
                    logger.error(f"Error fetching CDR records: {response.status} - {text[:500]}")
                    return []
                
                if not text:
                    logger.warning("Empty response from CDR API")
                    return []
                
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON: {e}")
                    return []
            
            # Check for error response
            if isinstance(data, dict) and ('code' in data or 'message' in data):
                logger.error(f"API Error Response: {data}")
                return []
            
            # Handle both array and object responses
            if isinstance(data, list):
                logger.info(f"Got {len(data)} records from API (list format)")
                return data
            elif isinstance(data, dict) and 'xml_cdr' in data:
                logger.info(f"Got {len(data['xml_cdr'])} records from API (dict format)")
                return data['xml_cdr']
            
            logger.warning(f"Unexpected response format. Keys: {data.keys() if isinstance(data, dict) else type(data)}")
            return []
                
        except Exception as e:
            logger.error(f"Exception fetching CDR records: {type(e).__name__}: {e}", exc_info=True)
            return []
    
    async def get_extensions(self) -> List[Dict[str, Any]]:
        """Fetch all extensions with user mappings"""
        try:
            url = f"{self.host}/app/api/7/extensions"
            
            async with self.session.get(url, timeout=self.timeout, ssl=False) as response:
                logger.info(f"Extensions Response status: {response.status}")
                
                text = await response.text()
                logger.info(f"Extensions response (first 1000 chars): {text[:1000]}")
                
                if response.status != 200:
                    logger.error(f"Error fetching extensions: {response.status} - {text[:500]}")
                    return []
                
                if not text:
                    logger.warning("Empty response from Extensions API")
                    return []
                
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse extensions JSON: {e}")
                    return []
            
            # Check for error response
            if isinstance(data, dict) and ('code' in data or 'message' in data):
                logger.error(f"API Error Response: {data}")
                return []
            
            # Handle both array and object responses
            extensions = []
            items = data if isinstance(data, list) else data.get('extensions', [])
            
            logger.info(f"Parsed {len(items)} extensions")
            return items
                
        except Exception as e:
            logger.error(f"Exception fetching extensions: {type(e).__name__}: {e}", exc_info=True)
            return []

    def _build_query_string(self, params: Dict[str, Any]) -> str:
        """Build query string for logging"""
        from urllib.parse import urlencode
        return urlencode(params)


# Global client instance
_fusion_client: Optional[FusionPBXClient] = None


async def get_fusion_client() -> FusionPBXClient:
    """Get or create the global FusionPBX client instance"""
    global _fusion_client
    
    if _fusion_client is None:
        _fusion_client = FusionPBXClient()
        await _fusion_client.initialize()
    
    return _fusion_client


async def close_fusion_client():
    """Close the global FusionPBX client instance"""
    global _fusion_client
    
    if _fusion_client is not None:
        await _fusion_client.close()
        _fusion_client = None

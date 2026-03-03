"""
FusionPBX API Client
Handles all communication with FusionPBX API endpoints
"""
import os
import logging
import json
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

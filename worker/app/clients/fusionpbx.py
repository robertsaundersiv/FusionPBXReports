"""
FusionPBX API Client
Handles all communication with FusionPBX API endpoints
"""
import os
import logging
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import aiohttp
import asyncio
import base64

logger = logging.getLogger(__name__)


class FusionPBXClient:
    """Client for FusionPBX API"""
    
    def __init__(self):
        self.host = os.getenv("FUSIONPBX_HOST", "https://pbx.example.com")
        self.api_key = os.getenv("FUSIONPBX_API_KEY", "")
        self.timeout = 30
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def initialize(self):
        """Initialize async session"""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
    async def close(self):
        """Close async session"""
        if self.session:
            await self.session.close()
            self.session = None
            
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with Basic Auth"""
        # Try the API key directly first (might already be base64)
        # If that doesn't work, we'll encode it as username:apikey format
        return {
            "Authorization": f"Basic {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    
    async def get_xml_cdr(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Dict]:
        """
        Fetch CDR records from FusionPBX
        
        Returns list of CDR records as dictionaries
        """
        if not self.session:
            await self.initialize()
            
        try:
            url = f"{self.host}/app/api/7/xml_cdr"
            
            params = {
                "limit": limit,
                "offset": offset,
            }
            
            # FusionPBX expects date ranges as array: start_stamp[]=START&start_stamp[]=END
            # Since aiohttp doesn't handle array params easily, we'll build the URL manually
            if start_date and end_date:
                start_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
                end_str = end_date.strftime("%Y-%m-%d %H:%M:%S")
                # Add array params manually to URL
                url = f"{url}?limit={limit}&offset={offset}&start_stamp[]={start_str}&start_stamp[]={end_str}"
                async with self.session.get(
                    url.replace(' ', '+'),  # URL encode spaces
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ssl=False,  # For self-signed certs
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"CDR API error: {resp.status}")
                        text = await resp.text()
                        logger.error(f"Response: {text[:200]}")
                        return []
                        
                    data = await resp.json()
                    # Handle wrapped response: {"xml_cdr": [...]} or direct array
                    if isinstance(data, dict):
                        data = data.get('xml_cdr', [])
                    return data if isinstance(data, list) else []
            else:
                # No date filter, use regular params
                async with self.session.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ssl=False,  # For self-signed certs
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"CDR API error: {resp.status}")
                        text = await resp.text()
                        logger.error(f"Response: {text[:200]}")
                        return []
                        
                    data = await resp.json()
                    # Handle wrapped response: {"xml_cdr": [...]} or direct array
                    if isinstance(data, dict):
                        data = data.get('xml_cdr', [])
                    return data if isinstance(data, list) else []
                
        except Exception as e:
            logger.error(f"Error fetching CDR records: {e}")
            return []

    async def get_xml_cdr_by_uuid(self, uuid: str) -> Optional[Dict]:
        """Fetch a single CDR record by its xml_cdr_uuid."""
        if not self.session:
            await self.initialize()
        try:
            url = f"{self.host}/app/api/7/xml_cdr/{uuid}"
            async with self.session.get(
                url,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                ssl=False,
            ) as resp:
                if resp.status == 404:
                    return None
                if resp.status != 200:
                    logger.error(f"CDR UUID lookup error {resp.status} for {uuid}")
                    return None
                data = await resp.json()
                if isinstance(data, list):
                    return data[0] if data else None
                if isinstance(data, dict):
                    # API may return {"xml_cdr": [{...}]}, {"xml_cdr": {...}}, or the record directly
                    inner = data.get("xml_cdr", data)
                    if isinstance(inner, list):
                        return inner[0] if inner else None
                    return inner
                return None
        except Exception as e:
            logger.error(f"Error fetching CDR by UUID {uuid}: {e}")
            return None


        """Fetch call center queue metadata"""
        if not self.session:
            await self.initialize()
            
        try:
            url = f"{self.host}/app/api/7/call_center_queues"
            
            async with self.session.get(
                url,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Queue API error: {resp.status}")
                    text = await resp.text()
                    logger.error(f"Response: {text[:200]}")
                    return []
                    
                data = await resp.json()
                # Handle wrapped response: {"call_center_queues": [...]} or direct array
                if isinstance(data, dict):
                    data = data.get('call_center_queues', [])
                return data if isinstance(data, list) else []
                
        except Exception as e:
            logger.error(f"Error fetching queues: {e}")
            return []
    
    async def get_call_center_agents(self) -> List[Dict]:
        """Fetch call center agent metadata"""
        if not self.session:
            await self.initialize()
            
        try:
            url = f"{self.host}/app/api/7/call_center_agents"
            
            async with self.session.get(
                url,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Agent API error: {resp.status}")
                    text = await resp.text()
                    logger.error(f"Response: {text[:200]}")
                    return []
                    
                data = await resp.json()
                # Handle wrapped response: {"call_center_agents": [...]} or direct array
                if isinstance(data, dict):
                    data = data.get('call_center_agents', [])
                return data if isinstance(data, list) else []
                
        except Exception as e:
            logger.error(f"Error fetching agents: {e}")
            return []
    
    async def get_call_center_tiers(self) -> List[Dict]:
        """Fetch agent-queue tier mappings"""
        if not self.session:
            await self.initialize()
            
        try:
            url = f"{self.host}/app/api/7/call_center_tiers"
            
            async with self.session.get(
                url,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Tier API error: {resp.status}")
                    text = await resp.text()
                    logger.error(f"Response: {text[:200]}")
                    return []
                    
                data = await resp.json()
                # Handle wrapped response: {"call_center_tiers": [...]} or direct array
                if isinstance(data, dict):
                    data = data.get('call_center_tiers', [])
                return data if isinstance(data, list) else []
                
        except Exception as e:
            logger.error(f"Error fetching tiers: {e}")
            return []
    
    async def get_extensions(self) -> List[Dict]:
        """Fetch extension to user mappings"""
        if not self.session:
            await self.initialize()
            
        try:
            url = f"{self.host}/app/api/7/extensions"
            
            async with self.session.get(
                url,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Extension API error: {resp.status}")
                    text = await resp.text()
                    logger.error(f"Response: {text[:200]}")
                    return []
                    
                data = await resp.json()
                # Handle wrapped response: {"extensions": [...]} or direct array
                if isinstance(data, dict):
                    data = data.get('extensions', [])
                return data if isinstance(data, list) else []
                
        except Exception as e:
            logger.error(f"Error fetching extensions: {e}")
            return []
    
    @staticmethod
    def _parse_xml_response(xml_content: str, row_tag: str = "row") -> List[Dict]:
        """
        Parse XML response and return list of dictionaries
        
        Handles typical FusionPBX XML response format:
        <response>
            <row>
                <field1>value1</field1>
                <field2>value2</field2>
            </row>
        </response>
        """
        results = []
        try:
            root = ET.fromstring(xml_content)
            
            for row in root.findall(row_tag):
                record = {}
                for child in row:
                    key = child.tag
                    value = child.text
                    
                    # Type conversion
                    if value:
                        if value.isdigit():
                            value = int(value)
                        elif value.replace('.', '', 1).isdigit():
                            try:
                                value = float(value)
                            except ValueError:
                                pass
                    
                    record[key] = value
                    
                if record:
                    results.append(record)
                    
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            
        return results


# Global client instance
_fusion_client: Optional[FusionPBXClient] = None


def get_fusion_client() -> FusionPBXClient:
    """Get or create FusionPBX client"""
    global _fusion_client
    if _fusion_client is None:
        _fusion_client = FusionPBXClient()
    return _fusion_client

"""Quick live check for FusionPBX agent list/status endpoints."""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.clients.fusionpbx import FusionPBXClient

TARGET_NAME = "PHI-CS-Darian"


def _match_agent_name(row: dict) -> bool:
    return (
        row.get("agent_name") == TARGET_NAME
        or row.get("name") == TARGET_NAME
        or row.get("call_center_agent_name") == TARGET_NAME
    )


async def main() -> None:
    client = FusionPBXClient()
    await client.initialize()

    try:
        list_url = f"{client.host}/app/api/7/cc_agent_list"
        status_url = f"{client.host}/app/api/7/cc_agent_status"

        async with client.session.get(list_url, timeout=client.timeout, ssl=False) as resp:
            raw_list_text = await resp.text()
            print(f"cc_agent_list_http_status={resp.status}")
            print("cc_agent_list_raw_preview=" + raw_list_text[:300])

        async with client.session.get(status_url, timeout=client.timeout, ssl=False) as resp:
            raw_status_text = await resp.text()
            print(f"cc_agent_status_http_status={resp.status}")
            print("cc_agent_status_raw_preview=" + raw_status_text[:300])

        agent_list = await client.get_cc_agent_list()
        agent_status = await client.get_cc_agent_status()
        call_center_agents = await client.get_agents()

        print(f"cc_agent_list_count={len(agent_list)}")
        print(f"cc_agent_status_count={len(agent_status)}")
        print(f"call_center_agents_count={len(call_center_agents)}")

        if agent_list:
            print("cc_agent_list_sample=" + json.dumps(agent_list[0]))
        if agent_status:
            print("cc_agent_status_sample=" + json.dumps(agent_status[0]))

        darian_in_list = [row for row in agent_list if _match_agent_name(row)]
        darian_in_status = [row for row in agent_status if _match_agent_name(row)]
        darian_in_agents = [row for row in call_center_agents if _match_agent_name(row)]

        print("darian_list_rows=" + json.dumps(darian_in_list))
        print("darian_status_rows=" + json.dumps(darian_in_status))
        print("darian_call_center_agents_rows=" + json.dumps(darian_in_agents))
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())

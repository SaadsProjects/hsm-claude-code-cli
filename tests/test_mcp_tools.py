"""
End-to-end protocol test: launches mcp_server/hsm_tools.py as a real MCP
stdio server (via the official `mcp` SDK's client) and drives it through a
real initialize -> list_tools -> call_tool handshake against the mock HSM
backend. This proves the MCP layer itself works, independent of whether an
LLM is available -- no ANTHROPIC_API_KEY or `claude` CLI invocation needed.

Run with either (both start their own mock server on port 8772):
    python3 -m pytest tests/test_mcp_tools.py -v
    python3 tests/test_mcp_tools.py
"""
import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_PORT = 8772


def _start_mock_server():
    from mock_hsm.server import run as run_server
    t = threading.Thread(target=run_server, kwargs={"port": TEST_PORT}, daemon=True)
    t.start()
    from agents.hsm_client import HsmClient
    from mock_hsm.auth import mint_token
    for _ in range(40):
        try:
            HsmClient(mint_token("user_regional_atl"), base_url=f"http://127.0.0.1:{TEST_PORT}").get_sites()
            return
        except OSError:  # connection refused until the server thread is listening
            time.sleep(0.1)
    raise RuntimeError("mock server did not come up")


async def _run():
    _start_mock_server()

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(PROJECT_ROOT / "mcp_server" / "hsm_tools.py")],
        env={**os.environ, "HSM_BASE_URL": f"http://127.0.0.1:{TEST_PORT}",
             "HSM_ACTIVE_USER": "user_rm_midtown"},
        cwd=str(PROJECT_ROOT),
    )

    async with stdio_client(server_params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        tools = (await session.list_tools()).tools
        names = {t.name for t in tools}
        expected = {"get_forecast", "get_employees", "get_labor_rules", "get_vendors",
                    "get_on_hand", "compute_labor_demand", "validate_schedule",
                    "compute_usage_anomalies", "compute_reorder_needs",
                    "publish_schedule", "submit_purchase_order"}
        missing = expected - names
        assert not missing, f"missing tools: {missing}"
        print(f"OK: all {len(expected)} expected tools registered")

        demand = await session.call_tool("compute_labor_demand", {"site_id": "site_001"})
        demand_data = json.loads(demand.content[0].text)
        assert len(demand_data["demand"]) == 7, "expected 7 days of demand"
        print(f"OK: compute_labor_demand returned {len(demand_data['demand'])} days")

        employees = await session.call_tool("get_employees", {"site_id": "site_001"})
        emp_data = json.loads(employees.content[0].text)
        assert len(emp_data["employees"]) > 0
        print(f"OK: get_employees returned {len(emp_data['employees'])} employees")

        # A deliberately bad shift (23h59m) must trip max_shift_length.
        bad_shifts = [{"employee_id": emp_data["employees"][0]["employee_id"],
                       "date": "2026-01-05", "role": emp_data["employees"][0]["job_code"],
                       "start_time": "00:00", "end_time": "23:59"}]
        validation = await session.call_tool("validate_schedule",
                                              {"jurisdiction": "GA", "shifts": bad_shifts})
        val_data = json.loads(validation.content[0].text)
        assert any(v["rule"] == "max_shift_length" for v in val_data["violations"])
        print("OK: validate_schedule correctly flags an oversized shift")

        anomalies = await session.call_tool("compute_usage_anomalies", {"site_id": "site_001"})
        anomaly_data = json.loads(anomalies.content[0].text)
        assert any(a["raw_material_id"] == "rm_ground_beef" for a in anomaly_data["anomalies"])
        print("OK: compute_usage_anomalies flags the seeded ground-beef drift")

        # Recipes are fetched through HsmClient, not read from the mock DB.
        reorder = await session.call_tool("compute_reorder_needs", {"site_id": "site_001"})
        assert not reorder.isError, reorder.content[0].text
        reorder_data = json.loads(reorder.content[0].text)
        assert isinstance(reorder_data["reorder_needs"], list)
        print(f"OK: compute_reorder_needs returned {len(reorder_data['reorder_needs'])} needs")

        # Scope enforcement flows through the MCP layer too, via the token
        # minted from HSM_ACTIVE_USER inside the tool implementation.
        other_site = await session.call_tool("get_employees", {"site_id": "site_002"})
        assert other_site.isError, "Restaurant Manager token must not read another site"
        print("OK: persona scope enforcement holds through the MCP layer (403 on site_002)")

    print("\nAll MCP protocol checks passed.")


def test_mcp_protocol():
    asyncio.run(_run())


if __name__ == "__main__":
    asyncio.run(_run())

"""HTTP clients for Al Dente mock APIs. All list helpers exhaust pagination."""

import os

import httpx

_BASE = os.environ.get("MOCK_API_BASE_URL", "https://aldente.yellowtest.it")
_TOKEN = os.environ.get("MOCK_API_TOKEN", "")


def _headers() -> dict:
    return {"Authorization": f"Bearer {_TOKEN}"}


def _get_all(path: str, params: dict | None = None) -> list:
    """Fetch every page from a paginated list endpoint (data key)."""
    params = dict(params or {})
    params["limit"] = 200
    results: list = []
    offset = 0
    with httpx.Client(base_url=_BASE, headers=_headers(), timeout=25) as c:
        while True:
            params["offset"] = offset
            r = c.get(path, params=params)
            r.raise_for_status()
            j = r.json()
            batch: list = j["data"]
            results.extend(batch)
            total: int = j["pagination"]["total"]
            offset += len(batch)
            if offset >= total or not batch:
                break
    return results


def _get_one(path: str) -> dict | None:
    with httpx.Client(base_url=_BASE, headers=_headers(), timeout=15) as c:
        r = c.get(path)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


# ── CRM ──────────────────────────────────────────────────────────────────────

def get_customers(search: str | None = None, channel: str | None = None,
                  status: str | None = None) -> list:
    p: dict = {}
    if search:
        p["search"] = search
    if channel:
        p["channel"] = channel
    if status:
        p["status"] = status
    return _get_all("/crm/customers", p)


def get_customer(customer_id: str) -> dict | None:
    return _get_one(f"/crm/customers/{customer_id}")


def get_opportunities(customer_id: str | None = None,
                      stage: str | None = None) -> list:
    p: dict = {}
    if customer_id:
        p["customer_id"] = customer_id
    if stage:
        p["stage"] = stage
    return _get_all("/crm/opportunities", p)


def get_orders(customer_id: str | None = None,
               status: str | None = None) -> list:
    p: dict = {}
    if customer_id:
        p["customer_id"] = customer_id
    if status:
        p["status"] = status
    return _get_all("/crm/orders", p)


def get_invoices(customer_id: str | None = None,
                 status: str | None = None,
                 order_id: str | None = None) -> list:
    p: dict = {}
    if customer_id:
        p["customer_id"] = customer_id
    if status:
        p["status"] = status
    if order_id:
        p["order_id"] = order_id
    return _get_all("/crm/invoices", p)


# ── Calls ─────────────────────────────────────────────────────────────────────

def get_calls(customer_id: str | None = None, type_: str | None = None,
              outcome: str | None = None) -> list:
    p: dict = {}
    if customer_id:
        p["customer_id"] = customer_id
    if type_:
        p["type"] = type_
    if outcome:
        p["outcome"] = outcome
    return _get_all("/calls", p)


def get_call(call_id: str) -> dict | None:
    return _get_one(f"/calls/{call_id}")


def get_transcript(call_id: str, search: str | None = None,
                   limit: int = 30) -> dict:
    p: dict = {"limit": limit, "offset": 0}
    if search:
        p["search"] = search
    with httpx.Client(base_url=_BASE, headers=_headers(), timeout=15) as c:
        r = c.get(f"/calls/{call_id}/transcript", params=p)
        r.raise_for_status()
        return r.json()


# ── ERP ───────────────────────────────────────────────────────────────────────

def get_inventory(type_: str | None = None, below_min: bool | None = None,
                  search: str | None = None) -> list:
    p: dict = {}
    if type_:
        p["type"] = type_
    if below_min is not None:
        p["below_min"] = "true" if below_min else "false"
    if search:
        p["search"] = search
    return _get_all("/erp/inventory", p)


def get_bom(sku: str) -> list:
    return _get_all("/erp/bom", {"sku": sku})


def get_suppliers(search: str | None = None,
                  category: str | None = None) -> list:
    p: dict = {}
    if search:
        p["search"] = search
    if category:
        p["category"] = category
    return _get_all("/erp/suppliers", p)


def get_production_orders(customer_id: str | None = None,
                          status: str | None = None,
                          sku: str | None = None) -> list:
    p: dict = {}
    if customer_id:
        p["customer_id"] = customer_id
    if status:
        p["status"] = status
    if sku:
        p["sku"] = sku
    return _get_all("/erp/production-orders", p)


def get_shipments(customer_id: str | None = None, order_id: str | None = None,
                  status: str | None = None) -> list:
    p: dict = {}
    if customer_id:
        p["customer_id"] = customer_id
    if order_id:
        p["order_id"] = order_id
    if status:
        p["status"] = status
    return _get_all("/erp/shipments", p)

"""Tool schemas (OpenAI function-calling format) and their executors."""

import concurrent.futures as _futures
import json
from . import clients, kb as kb_module

# Shared pool for fanning out the per-call transcript fetches in
# count_transcript_matches (otherwise ~80 sequential HTTP calls blow the budget).
_FETCH_POOL = _futures.ThreadPoolExecutor(max_workers=16)

# ── Schema definitions ────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": (
                "Search the knowledge base (35 documents): product spec sheets "
                "(shelf life, allergens, nutritional values, SKU codes), quality "
                "and returns policy, wholesale price list, customer supply specs "
                "(capitolati). Use for: product specs, allergens, shelf life, "
                "prices, return/quality policy, labelling requirements."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "top_k": {
                        "type": "integer",
                        "description": "Number of documents to return (default 3, max 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_customers",
            "description": (
                "Search CRM customers by name, channel, or status. Use to find "
                "a customer_id before other CRM queries, or to list all customers "
                "in a channel. channel values: GDO, distributor, horeca. "
                "status values: active, inactive, prospect."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Name search"},
                    "channel": {
                        "type": "string",
                        "enum": ["GDO", "distributor", "horeca"],
                    },
                    "status": {
                        "type": "string",
                        "enum": ["active", "inactive", "prospect"],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer",
            "description": "Get full profile of one customer by ID (e.g. CUST-0132).",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                },
                "required": ["customer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_opportunities",
            "description": (
                "Get CRM opportunities (deals). Returns ALL pages with Python-computed "
                "aggregates: count, total_value, open_count (qualification+negotiation), "
                "open_value, by_stage breakdown, by_channel breakdown. "
                "Filter by customer_id and/or stage (qualification/negotiation/won/lost). "
                "Use for: deal counts, total deal value, pipeline by stage or channel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "stage": {
                        "type": "string",
                        "enum": ["qualification", "negotiation", "won", "lost"],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_orders",
            "description": (
                "Get CRM orders. Filter by customer_id and/or status "
                "(open/in_production/shipped/delivered/cancelled)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calls",
            "description": (
                "Get call log entries (metadata only, no transcript). Sorted by date "
                "descending so first entry is the most recent call. "
                "Filter by customer_id, type (sales/support), or outcome "
                "(complaint_open/follow_up/order_placed/resolved). "
                "Use get_call_transcript to read what was said."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "type": {"type": "string", "enum": ["sales", "support"]},
                    "outcome": {
                        "type": "string",
                        "enum": [
                            "complaint_open",
                            "follow_up",
                            "order_placed",
                            "resolved",
                        ],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_call_transcript",
            "description": (
                "Get transcript segments for a specific call. Always use the "
                "search parameter to pull only relevant segments — do NOT fetch "
                "without search unless you need the full conversation. "
                "search filters to segments containing that term."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "call_id": {"type": "string", "description": "e.g. CALL-58020"},
                    "search": {
                        "type": "string",
                        "description": "Filter segments to those containing this term",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max segments to return (default 30)",
                    },
                },
                "required": ["call_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_transcript_matches",
            "description": (
                "Count calls related to a term across the ENTIRE call log. "
                "Returns TWO counts: (1) about_count / about_calls — calls whose "
                "structured topic or summary is ABOUT the term (e.g. the reported "
                "defect). Use this for 'how many complaints/calls about X' aggregate "
                "questions — it excludes passing mentions, policy lists, and negations. "
                "(2) transcript_match_count / transcript_match_calls — every call whose "
                "transcript merely mentions the term (broader, includes incidental "
                "mentions). For complaint/defect counts prefer about_count."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "Term to search in transcripts",
                    },
                    "customer_id": {
                        "type": "string",
                        "description": "Optional: limit search to one customer",
                    },
                },
                "required": ["search_term"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventory",
            "description": (
                "Get ERP inventory items. type: finished_good or raw_material. "
                "below_min=true returns only items below minimum stock level. "
                "search filters by SKU or product name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["finished_good", "raw_material"],
                    },
                    "below_min": {"type": "boolean"},
                    "search": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bom",
            "description": (
                "Get bill of materials for a finished product SKU (e.g. PAS-SPA-500). "
                "Returns raw material components with quantities and supplier info."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "Finished product SKU"},
                },
                "required": ["sku"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_suppliers",
            "description": (
                "Get ERP suppliers. Filter by search (name) or category "
                "(semolina/wheat/packaging/labels/ink/logistics)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "semolina",
                            "wheat",
                            "packaging",
                            "labels",
                            "ink",
                            "logistics",
                        ],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_shipments",
            "description": "Get ERP shipments for a customer or order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "order_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["in_transit", "delivered", "delayed"],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_production_orders",
            "description": (
                "Get ERP production orders (a.k.a. production LOTS — id format "
                "LOT-2026-####). To look up ONE specific lot, pass its id as lot_id. "
                "Otherwise filter by customer_id, status, or SKU. Each record has "
                "status/progress_pct/quality_status/linked_order_id (no cost/price/margin)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lot_id": {
                        "type": "string",
                        "description": "Specific production lot id, e.g. LOT-2026-0405",
                    },
                    "customer_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["planned", "in_progress", "done", "blocked"],
                    },
                    "sku": {"type": "string"},
                },
            },
        },
    },
]


# ── Executors ─────────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> tuple[object, list[str]]:
    """Execute a tool by name. Returns (result, sources_used)."""
    try:
        return _dispatch(name, args)
    except Exception as exc:
        return {"error": str(exc)}, []


def _dispatch(name: str, args: dict) -> tuple[object, list[str]]:  # noqa: C901
    if name == "search_kb":
        top_k = min(int(args.get("top_k", 3)), 5)
        results = kb_module.search(args["query"], top_k=top_k)
        sources = [r["id"] for r in results]
        return results, sources

    if name == "search_customers":
        data = clients.get_customers(
            search=args.get("search"),
            channel=args.get("channel"),
            status=args.get("status"),
        )
        return {"customers": data, "count": len(data)}, ["crm/customers"]

    if name == "get_customer":
        cid = args["customer_id"]
        data = clients.get_customer(cid)
        if data is None:
            return {"not_found": True, "customer_id": cid}, [f"crm/customers/{cid}"]
        return data, [f"crm/customers/{cid}"]

    if name == "get_opportunities":
        customer_id = args.get("customer_id")
        stage = args.get("stage")
        opps = clients.get_opportunities(customer_id=customer_id, stage=stage)

        # Build customer→channel lookup
        if customer_id:
            cust = clients.get_customer(customer_id)
            cust_map = {customer_id: cust} if cust else {}
        else:
            all_custs = clients.get_customers()
            cust_map = {c["id"]: c for c in all_custs}

        open_stages = {"qualification", "negotiation"}
        total_value = 0
        open_value = 0
        by_stage: dict = {}
        by_channel: dict = {}

        for o in opps:
            val = o.get("value_eur", 0) or 0
            total_value += val
            s = o.get("stage", "unknown")
            if s in open_stages:
                open_value += val

            by_stage.setdefault(s, {"count": 0, "value": 0})
            by_stage[s]["count"] += 1
            by_stage[s]["value"] += val

            cid = o.get("customer_id", "")
            ch = (cust_map.get(cid) or {}).get("channel", "unknown")
            o["channel"] = ch
            by_channel.setdefault(ch, {"count": 0, "value": 0})
            by_channel[ch]["count"] += 1
            by_channel[ch]["value"] += val

        open_opps = [o for o in opps if o.get("stage") in open_stages]
        sources = ["crm/opportunities"]
        if not customer_id:
            sources.append("crm/customers")
        return {
            "opportunities": opps,
            "count": len(opps),
            "total_value": total_value,
            "open_count": len(open_opps),
            "open_value": open_value,
            "by_stage": by_stage,
            "by_channel": by_channel,
        }, sources

    if name == "get_orders":
        data = clients.get_orders(
            customer_id=args.get("customer_id"),
            status=args.get("status"),
        )
        return {"orders": data, "count": len(data)}, ["crm/orders"]

    if name == "get_calls":
        data = clients.get_calls(
            customer_id=args.get("customer_id"),
            type_=args.get("type"),
            outcome=args.get("outcome"),
        )
        data_sorted = sorted(data, key=lambda c: c.get("date", ""), reverse=True)
        return {"calls": data_sorted, "count": len(data_sorted)}, ["calls"]

    if name == "get_call_transcript":
        call_id = args["call_id"]
        search = args.get("search")
        limit = args.get("limit", 30)
        result = clients.get_transcript(call_id, search=search, limit=limit)
        # If the search term matched nothing, fall back to the opening segments
        # so the agent still gets context instead of concluding "nothing found".
        if search and not result.get("segments"):
            result = clients.get_transcript(call_id, search=None, limit=limit)
            result["search_fallback"] = True
            result["note"] = (
                f"No segments matched '{search}'. Showing the opening segments "
                "instead — read them or retry with a different search term."
            )
        return result, [f"calls/{call_id}/transcript"]

    if name == "count_transcript_matches":
        search_term = args["search_term"]
        customer_id = args.get("customer_id")
        all_calls = clients.get_calls(customer_id=customer_id)
        term_l = search_term.lower()
        transcript_matches: list[dict] = []
        about_matches: list[dict] = []

        # Build entries + about_count from call metadata only (no network).
        entries: list[dict] = []
        for call in all_calls:
            call_id = call.get("id") or call.get("call_id")
            if not call_id:
                continue
            topic = call.get("topic") or ""
            summary = call.get("summary") or ""
            is_about = term_l in topic.lower() or term_l in summary.lower()
            entry = {
                "call_id": call_id,
                "date": call.get("date"),
                "customer_id": call.get("customer_id"),
                "topic": topic,
                "summary": summary,
                "_is_about": is_about,
            }
            entries.append(entry)
            if is_about:
                about_matches.append({k: v for k, v in entry.items() if k != "_is_about"})

        # Fan out the per-call transcript fetches in parallel (~80 calls would be
        # ~25s sequential — that blows the 30s budget on the broad-match count).
        def _has_match(entry: dict) -> tuple[dict, bool]:
            try:
                t = clients.get_transcript(entry["call_id"], search=search_term, limit=5)
                return entry, bool(t.get("segments"))
            except Exception:
                return entry, False

        for entry, matched in _FETCH_POOL.map(_has_match, entries):
            if matched:
                transcript_matches.append({
                    "call_id": entry["call_id"],
                    "date": entry["date"],
                    "customer_id": entry["customer_id"],
                    "topic": entry["topic"],
                    "summary": entry["summary"],
                    "in_summary": entry["_is_about"],
                })
        return {
            "search_term": search_term,
            "total_calls_searched": len(all_calls),
            "about_count": len(about_matches),
            "about_calls": about_matches,
            "transcript_match_count": len(transcript_matches),
            "transcript_match_calls": transcript_matches,
        }, ["calls", "calls/*/transcript"]

    if name == "get_inventory":
        data = clients.get_inventory(
            type_=args.get("type"),
            below_min=args.get("below_min"),
            search=args.get("search"),
        )
        # Enrich with supplier names so LLM doesn't need a separate lookup
        if any(item.get("supplier_id") for item in data):
            try:
                all_sups = clients.get_suppliers()
                sup_name_map = {s["id"]: s["name"] for s in all_sups if "id" in s}
                for item in data:
                    sid = item.get("supplier_id")
                    if sid and sid in sup_name_map:
                        item["supplier_name"] = sup_name_map[sid]
            except Exception:
                pass
        sources = ["erp/inventory"]
        if any(item.get("supplier_name") for item in data):
            sources.append("erp/suppliers")
        return {"inventory": data, "count": len(data)}, sources

    if name == "get_bom":
        sku = args["sku"]
        data = clients.get_bom(sku)
        # API returns list of items each with nested "components" list
        components: list = []
        for item in data:
            components.extend(item.get("components", []))
        # Enrich each component with inventory/supplier data (stock + supplier name)
        raw_skus = [c.get("raw_sku") for c in components if c.get("raw_sku")]
        sources = ["erp/bom"]
        if raw_skus:
            try:
                all_sups = clients.get_suppliers()
                sup_name_map = {s["id"]: s["name"] for s in all_sups if "id" in s}
                inventory = clients.get_inventory(type_="raw_material")
                inv_map = {i["sku"]: i for i in inventory if "sku" in i}
                for comp in components:
                    rsku = comp.get("raw_sku")
                    if rsku and rsku in inv_map:
                        inv_item = inv_map[rsku]
                        comp["on_hand"] = inv_item.get("on_hand")
                        comp["min_stock"] = inv_item.get("min_stock")
                        comp["below_min"] = inv_item.get("below_min")
                        comp["unit"] = inv_item.get("unit", comp.get("unit"))
                        sid = inv_item.get("supplier_id")
                        if sid and sid in sup_name_map:
                            comp["supplier_id"] = sid
                            comp["supplier_name"] = sup_name_map[sid]
                sources += ["erp/inventory", "erp/suppliers"]
            except Exception:
                pass
        return {"sku": sku, "components": components}, sources

    if name == "get_suppliers":
        data = clients.get_suppliers(
            search=args.get("search"),
            category=args.get("category"),
        )
        return {"suppliers": data, "count": len(data)}, ["erp/suppliers"]

    if name == "get_shipments":
        data = clients.get_shipments(
            customer_id=args.get("customer_id"),
            order_id=args.get("order_id"),
            status=args.get("status"),
        )
        return {"shipments": data, "count": len(data)}, ["erp/shipments"]

    if name == "get_production_orders":
        data = clients.get_production_orders(
            customer_id=args.get("customer_id"),
            status=args.get("status"),
            sku=args.get("sku"),
        )
        # The API has no id filter; resolve a specific lot client-side.
        lot_id = args.get("lot_id")
        if lot_id:
            match = [p for p in data if p.get("id") == lot_id]
            if not match:
                return {
                    "lot_id": lot_id,
                    "found": False,
                    "production_orders": [],
                    "count": 0,
                }, ["erp/production-orders"]
            return {"production_orders": match, "count": len(match)}, [
                "erp/production-orders"
            ]
        return {"production_orders": data, "count": len(data)}, ["erp/production-orders"]

    return {"error": f"Unknown tool: {name}"}, []

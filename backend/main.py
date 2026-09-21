"""Al Dente Company Brain - backend entry point."""

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

app = FastAPI(title="Al Dente Company Brain")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATIC = Path(__file__).resolve().parent / "static"
_FILES = _STATIC / "files"
_FILES.mkdir(parents=True, exist_ok=True)

app.mount("/files", StaticFiles(directory=_FILES), name="files")

_assets = _STATIC / "assets"
if _assets.is_dir():
    app.mount("/assets", StaticFiles(directory=_assets), name="assets")


@app.get("/", include_in_schema=False)
def ui() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)


class AskResponse(BaseModel):
    answer: str
    sources: list[str]
    verticale: str
    artifact_url: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    from agent.loop import ask as agent_ask
    result = agent_ask(request.question)
    return AskResponse(
        answer=result["answer"],
        sources=result["sources"],
        verticale=result["verticale"],
        artifact_url=result.get("artifact_url"),
    )


# ── Knowledge graph ───────────────────────────────────────────────────────────

_graph_cache: dict | None = None


@app.get("/api/graph")
def get_graph() -> dict:
    global _graph_cache
    if _graph_cache is not None:
        return _graph_cache
    _graph_cache = _build_graph()
    return _graph_cache


def _build_graph() -> dict:
    from agent import clients, kb as kb_module

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(id_: str, label: str, group: str, title: str = "") -> None:
        if id_ not in seen_nodes:
            seen_nodes.add(id_)
            nodes.append({"id": id_, "label": label, "group": group, "title": title or label})

    def link(from_id: str, to_id: str, label: str) -> None:
        if not from_id or not to_id or from_id == to_id:
            return
        key = (from_id, to_id, label)
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append({"from": from_id, "to": to_id, "label": label})

    sku_pattern = re.compile(r"\bPAS-[A-Z]{3}-\d+\b")
    product_skus: set[str] = set()

    kb_docs = kb_module.get_all()
    for doc in kb_docs:
        for sku in sku_pattern.findall(doc["content"]):
            product_skus.add(sku)

    try:
        suppliers = clients.get_suppliers()
        for s in suppliers:
            sid = s.get("id", "")
            name = s.get("name", sid)
            add_node(sid, name[:30], "supplier", f"Supplier: {name}")
    except Exception:
        pass

    for sku in sorted(product_skus):
        label = sku
        for doc in kb_docs:
            if sku in doc["content"]:
                m = re.search(r"\*\*Commercial name\*\*.*?\|(.*?)\|", doc["content"])
                if not m:
                    m = re.search(r"# Product Specification Sheet - (.+)", doc["content"])
                if m:
                    label = m.group(1).strip()[:40]
                    break
        add_node(sku, label, "product", f"SKU: {sku}")

        try:
            bom_items = clients.get_bom(sku)
            for item in bom_items:
                for row in item.get("components", []):
                    raw_id = row.get("raw_sku") or row.get("raw_material_id") or ""
                    raw_name = row.get("description") or row.get("name") or raw_id
                    if raw_id:
                        add_node(raw_id, str(raw_name)[:30], "material", f"Raw material: {raw_name}")
                        link(sku, raw_id, "uses")
        except Exception:
            pass

    # KB documents → products (wiki-style spec links)
    for doc in kb_docs:
        doc_id = doc["id"]
        title_m = re.search(r"# (.+)", doc["content"])
        title = title_m.group(1).strip()[:35] if title_m else doc_id
        add_node(doc_id, title, "document", title)
        for sku in sku_pattern.findall(doc["content"]):
            if sku in seen_nodes:
                link(doc_id, sku, "specifies")

    # Raw materials → suppliers via inventory
    try:
        for item in clients.get_inventory(type_="raw_material"):
            raw_id = item.get("sku") or ""
            sid = item.get("supplier_id") or ""
            if raw_id and sid:
                link(raw_id, sid, "sourced from")
    except Exception:
        pass

    # Customers → products via orders
    try:
        for order in clients.get_orders():
            cid = order.get("customer_id") or ""
            items = (
                order.get("line_items")
                or order.get("items")
                or order.get("lines")
                or []
            )
            for row in items:
                sku = row.get("sku") or row.get("product_sku") or ""
                if cid and sku and sku in seen_nodes:
                    link(cid, sku, "orders")
    except Exception:
        pass

    # Customers → products via production orders (fallback linkage)
    try:
        for po in clients.get_production_orders():
            cid = po.get("customer_id") or ""
            sku = po.get("sku") or ""
            if cid and sku and sku in seen_nodes:
                link(cid, sku, "produces for")
    except Exception:
        pass

    try:
        customers = clients.get_customers()
        for c in customers[:200]:
            cid = c.get("id", "")
            name = c.get("name", cid)
            channel = c.get("channel", "")
            add_node(cid, name[:30], "customer", f"{name} ({channel})")
    except Exception:
        pass

    return {"nodes": nodes, "edges": edges}

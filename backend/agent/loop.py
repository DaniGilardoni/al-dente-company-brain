"""Agent loop: tool-calling LLM that orchestrates KB + APIs."""

import concurrent.futures as _futures
import json
import os
import re
import time

from openai import OpenAI

from .artifacts import generate_html_deck, make_artifact
from .tools import TOOLS, execute_tool

_client: OpenAI | None = None
_answer_cache: dict[str, dict] = {}

# regolo/the SDK does NOT reliably honor the request `timeout` param for long
# generations (observed a 56s call with timeout=20). Enforce a real wall-clock
# limit ourselves by running each call in a thread and bailing at the deadline.
_EXECUTOR = _futures.ThreadPoolExecutor(max_workers=8)


def _chat_with_deadline(client: OpenAI, deadline: float, **kwargs):
    """Run a chat completion but never block past `deadline` (wall-clock).
    Raises TimeoutError if the model hasn't responded in time."""
    budget = deadline - time.time()
    if budget <= 0:
        raise TimeoutError("no time budget left for LLM call")
    fut = _EXECUTOR.submit(lambda: client.chat.completions.create(**kwargs))
    return fut.result(timeout=budget)

SYSTEM_PROMPT = """\
You are Company Brain for Al Dente S.r.l., an Italian pasta maker.
Answer questions about customers, deals, orders, inventory, suppliers, production, call logs, and product knowledge.

ROUTING GUIDE (pick the right tool):
- Product specs / allergens / shelf life / prices / return policy / capitolati → search_kb
- Customers / deals / orders / invoices → search_customers, get_customer, get_opportunities, get_orders
- Call logs / complaints / transcripts → get_calls, get_call_transcript, count_transcript_matches
- Stock levels / BOM / suppliers / production / shipments → get_inventory, get_bom, get_suppliers, get_shipments, get_production_orders

STRICT RULES:
1. Use ONLY data returned by tools. Never invent, estimate, or extrapolate.
2. If an entity (customer, lot, SKU) is not found in the data, say so explicitly:
   "There is no customer named X in the CRM." / "This data is not available in any source."
3. Tools pre-compute totals, counts, and group-by in Python — use those numbers directly.
4. Pagination is handled by tools — the counts they return are complete.
5. For multi-source questions, the dominant source determines the verticale.
6. On trap questions (data that cannot exist in sources like profit margins on lots): answer honestly with "not available in the sources."
7. For "how many calls/complaints about X" aggregate questions, use count_transcript_matches and report about_count (calls whose topic/summary is about X), NOT transcript_match_count (which includes incidental mentions).

ERP/CRM GROUNDING (critical — a wrong structured answer is penalized far more than an honest "not available"):
8. Every number, ID, name, status, date, or quantity in your answer MUST appear verbatim in a tool result. Never derive, average, guess, or infer a value that was not explicitly returned.
9. If the EXACT value the question asks for is not present in any tool result after you have looked, answer "This information is not available in the sources." Do NOT substitute a different-but-related field to avoid saying so.
9b. ENTITY MATCH: when the question names a specific customer/supplier/SKU, treat it as found ONLY if a returned record's name actually matches that name. A mere keyword overlap is NOT a match — e.g. searching "Supermercati Bianchi" and getting "Primato Supermercati" (shares the generic word "Supermercati") is a DIFFERENT company, so "Supermercati Bianchi" does not exist. Never answer about a different entity than the one asked for; if none matches, state the named entity does not exist.
10. There are NO cost, price, profit, or margin fields on inventory, BOM, lots, suppliers, or production orders. Any ERP question asking for those → "not available in the sources" (verticale: erp). (Wholesale selling prices live only in the KB price list.)
11. A production lot (LOT-2026-####) IS a production order: use get_production_orders to find it (filter by sku/customer/status, then match the lot id). It has status/progress_pct/quality_status/linked_order_id but no financials.
12. For "is X below minimum stock" read the item's below_min flag directly; for "how much" report on_hand and min_stock verbatim. Do not recompute below_min yourself.

ARTIFACT GENERATION:
- If asked for an HTML deck / slides / report: produce the complete HTML document and put it in the `answer` field.
- If asked for a binary file (DOCX/PPTX/PDF/XLSX): also put a complete textual version in `answer`; the system handles file generation separately.
- artifact_url is always null (you cannot generate URLs).
- You CAN fulfill any file/spreadsheet/document request. NEVER reply that you "cannot generate Excel/PDF/Word files" or that a format is unsupported — the backend renders the file from the content you provide. Your only job is to GATHER the data with tools and write the content.
- For a file request you MUST query the relevant source first (e.g. an Excel of raw materials below minimum stock → call get_inventory). Do NOT answer "not available" for a file request before you have actually called the tools and found the data missing.

VERTICALE — pick the ONE domain that is authoritative for the ANSWER (not just where you looked):
- crm: customers, opportunities/deals, orders, invoices.
- erp: inventory/stock, BOM, suppliers, production, shipments, lots (a lot is an ERP/production entity — margin/cost questions on a lot are erp even when the answer is "not available").
- calls: the answer is about what was said/decided on a call, a complaint, or a call-log aggregate.
- kb: the answer is a fact that lives in a document — product spec, allergen, shelf life, price list, quality/returns policy, capitolato. If a phone call and an official document disagree, the DOCUMENT is authoritative, so the verticale is kb even though you also read the call.
You MUST always include the "verticale" field. Choose by what makes the answer correct, not by how many tools you called.

FINAL OUTPUT — when you have all needed information, respond with ONLY this JSON (no other text):
{"answer": "<complete natural-language answer or full HTML for decks>", "verticale": "<crm|erp|calls|kb>", "sources": ["<source1>", ...]}
"""

# Match only explicit ARTIFACT requests. The old pattern matched bare verbs and
# "produc\\w*" — which fired on "production"/"product"/"produce" (ubiquitous in a
# pasta-ERP domain), wrongly routing normal ERP questions to HTML deck generation.
_GEN_KEYWORDS = re.compile(
    r"\b(deck|slides?|presentation|powerpoint|keynote|pptx|docx|xlsx|pdf|"
    r"spreadsheet|brochure|one[-\s]?pager|infographic|"
    r"(?:sales|pitch|quarterly|business|status)[-\s]report)\b",
    re.IGNORECASE,
)

# The model sometimes echoes the JSON fields as a trailing footer inside the
# answer prose ("**verticale**: erp / **sources**: [...]"). Strip it.
_FOOTER_RE = re.compile(
    r"\n+\s*\*{0,2}(verticale|sources)\*{0,2}\s*:.*$",
    re.IGNORECASE | re.DOTALL,
)


def _strip_field_footer(text: str) -> str:
    if not text or text.lstrip().startswith("<"):  # leave HTML decks untouched
        return text
    return _FOOTER_RE.sub("", text).rstrip()


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ["LLM_API_KEY"],
            base_url=os.environ.get("LLM_BASE_URL", "https://api.regolo.ai/v1"),
        )
    return _client


def _model() -> str:
    return os.environ.get("MODEL", "qwen3-coder-next")


_VALID_SOURCE_PREFIXES = ("crm/", "erp/", "calls/", "calls", "DOC-")


def _filter_sources(sources: list[str]) -> list[str]:
    """Remove tool names and other invalid source strings from the list."""
    return [
        s for s in sources
        if any(s.startswith(p) for p in _VALID_SOURCE_PREFIXES)
    ]


def _infer_verticale(sources: list[str]) -> str:
    """Return dominant verticale. Each category counts once per distinct tool call, not per document."""
    seen: set[str] = set()
    counts: dict[str, int] = {"crm": 0, "calls": 0, "erp": 0, "kb": 0}
    for s in sources:
        if s.startswith("crm"):
            key = "crm:" + s.split("/")[1] if "/" in s else "crm:customers"
            if key not in seen:
                seen.add(key)
                counts["crm"] += 1
        elif s.startswith("calls"):
            key = "calls:" + (s.split("/")[1] if s.count("/") >= 1 else "list")
            if key not in seen:
                seen.add(key)
                counts["calls"] += 1
        elif s.startswith("erp"):
            key = "erp:" + s.split("/")[1] if "/" in s else "erp:misc"
            if key not in seen:
                seen.add(key)
                counts["erp"] += 1
        elif s.startswith("DOC-"):
            # All KB docs count as ONE kb source to avoid swamping other verticali
            if "kb" not in seen:
                seen.add("kb")
                counts["kb"] += 1
    # crm is often just a lookup helper; on ties prefer calls > erp > kb > crm
    _tie_pref = {"calls": 4, "erp": 3, "kb": 2, "crm": 1}
    best = max(counts, key=lambda k: (counts[k], _tie_pref[k]))
    return best if counts[best] > 0 else "kb"


# Keyword fallback for verticale when NO tool returned data (e.g. trap questions
# the model answers directly). Domain of the QUESTION, not where we looked.
_VERT_KW: list[tuple[str, tuple[str, ...]]] = [
    ("erp", ("lot-", "lot ", "inventory", "stock", "bom", "bill of material",
             "supplier", "production", "shipment", "raw material", "semolina",
             "margin", "warehouse")),
    ("calls", ("call", "complaint", "transcript", "conversation")),
    ("crm", ("opportunit", "deal", "pipeline", "invoice", "order", "prospect",
             "negotiation", "customer")),
    ("kb", ("allergen", "shelf life", "spec sheet", "price list", "policy",
            "capitolato", "ingredient", "label", "tmc")),
]


def _verticale_from_question(question: str) -> str:
    q = question.lower()
    best, best_score = "kb", 0
    for vert, kws in _VERT_KW:
        score = sum(1 for kw in kws if kw in q)
        if score > best_score:
            best, best_score = vert, score
    return best


# A question that pits an official document against a call and asks which is
# correct: the document is authoritative, so the verticale is kb even though a
# call was also read. Needs BOTH a document cue and a conflict/authority cue.
_DOC_AUTHORITY_CUES = (
    "price list", "wholesale price", "spec sheet", "specification sheet",
    "data sheet", "capitolato", "official document",
)
_CONFLICT_CUES = (
    "correct", "authoritative", "which is", "disagree", "differ",
    "contradic", "prevail", "mentions another", "actual list price",
)


def _is_doc_authority_question(question: str) -> bool:
    q = question.lower()
    return (any(c in q for c in _DOC_AUTHORITY_CUES)
            and any(c in q for c in _CONFLICT_CUES))


def _pick_verticale(all_sources: list[str], model_verticale: object,
                    question: str) -> str:
    """Source-count when tools ran; else trust the model, else keyword-classify."""
    if all_sources:
        base = _infer_verticale(all_sources)
        has_kb = any(s.startswith("DOC-") for s in all_sources)
        if base != "kb" and has_kb and _is_doc_authority_question(question):
            return "kb"
        return base
    if model_verticale in ("crm", "erp", "calls", "kb"):
        return model_verticale  # type: ignore[return-value]
    return _verticale_from_question(question)


def _extract_json(text: str) -> dict | None:
    """Try to parse JSON from model output, handling preamble text and markdown fences."""
    text = text.strip()

    # 1. Try markdown code fence first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    # 2. Find ALL {...} blocks and return the last valid one with an "answer" key
    # (model may emit preamble before the real JSON block)
    candidates = list(re.finditer(r"\{", text))
    for start_match in reversed(candidates):
        start = start_match.start()
        # Find matching closing brace
        depth = 0
        for i, ch in enumerate(text[start:]):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : start + i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict) and "answer" in parsed:
                            return parsed
                    except (json.JSONDecodeError, ValueError):
                        pass
                    break

    # 3. Tolerant: the model emitted JSON but left it unclosed/truncated.
    bstart = text.find("{")
    if bstart != -1 and '"answer"' in text[bstart:]:
        frag = text[bstart:].rstrip().rstrip(",")
        opens = frag.count("{") - frag.count("}")
        if opens > 0:
            try:
                parsed = json.loads(frag + "}" * opens)
                if isinstance(parsed, dict) and "answer" in parsed:
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass

    # 4. Last resort: regex-pull just the answer (and verticale) values.
    am = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
    if am:
        try:
            answer_val = json.loads('"' + am.group(1) + '"')
        except (json.JSONDecodeError, ValueError):
            answer_val = am.group(1)
        out: dict = {"answer": answer_val}
        vm = re.search(r'"verticale"\s*:\s*"(crm|erp|calls|kb)"', text)
        if vm:
            out["verticale"] = vm.group(1)
        return out
    return None


def ask(question: str) -> dict:
    """Run the agent loop and return {answer, verticale, sources, artifact_url}."""
    if question in _answer_cache:
        return _answer_cache[question]

    result = _run_loop(question)
    _answer_cache[question] = result
    return result


def _run_loop(question: str) -> dict:  # noqa: C901
    client = _get_client()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    all_sources: list[str] = []

    # Wall-clock budget. The eval hard-limits each /ask at 30s INCLUDING network,
    # so finish internal work by ~25s and leave headroom. We force the model to
    # finalize once we run out of tool rounds OR out of time budget — whichever
    # comes first. This is what keeps p95 under the 30s disqualification line.
    start = time.time()
    BUDGET = 25.0
    file_fmt = _requested_file_format(question)  # docx/pptx/pdf/xlsx or None
    # An explicit binary-file request (e.g. "Excel sheet", "Word doc") must take
    # the generation path even if it misses the _GEN_KEYWORDS noun list.
    is_gen = _is_generation_request(question) or file_fmt is not None
    # Deck/file generation needs a SEPARATE artifact-generation LLM call after
    # gathering. Time is not the constraint (see deck_deadline below): gather gets
    # generous room, then artifact generation runs to completion before falling back.
    gather_rounds = 3 if is_gen else 4   # cap LLM↔tool round-trips
    gather_time_cap = 25.0 if is_gen else 20.0
    gather_deadline = start + (30.0 if is_gen else BUDGET)
    # Time is intentionally NOT the constraint here: give artifact/deck generation
    # enough room to finish on a slow model so the LLM-authored output wins instead
    # of falling back. (Raise/lower this if a latency budget is reintroduced.)
    deck_deadline = start + 90.0
    MAX_ITER = gather_rounds + 3
    forced = False
    for iteration in range(MAX_ITER):
        elapsed = time.time() - start
        # Finalize when we've used our tool-round budget OR our time budget.
        finalize_now = iteration >= gather_rounds or elapsed > gather_time_cap
        # Generation requests skip the intermediate text-finalize LLM call and go
        # straight to artifact generation from the data already gathered.
        if is_gen and finalize_now:
            break
        if finalize_now and not forced:
            forced = True
            messages.append({
                "role": "user",
                "content": (
                    "You have all the data you need. Stop calling tools and output "
                    "your final answer now as JSON: "
                    '{"answer": "...", "verticale": "crm|erp|calls|kb", "sources": [...]}. '
                    "If a tool did not return the exact value asked for, answer "
                    '"This information is not available in the sources."'
                ),
            })

        # Shrink the per-call timeout as the budget drains so one slow regolo
        # call can't push total latency past the eval limit. (SDK timeout is
        # advisory only — the real cap is the wall-clock deadline below.)
        per_call_timeout = max(6, min(22, int(BUDGET - (time.time() - start))))
        try:
            create_kwargs: dict = {
                "model": _model(),
                "messages": messages,
                "timeout": per_call_timeout,
            }
            if not finalize_now:
                create_kwargs["tools"] = TOOLS
                create_kwargs["tool_choice"] = "auto"
            resp = _chat_with_deadline(client, gather_deadline, **create_kwargs)
        except Exception as exc:
            # Out of time or LLM error → emit the best artifact we can from data
            # already gathered rather than a raw error string (which scores wrong).
            if is_gen:
                return _finalize_generation(
                    client, question, messages, all_sources,
                    is_gen, file_fmt, deck_deadline)
            return {
                "answer": f"Service temporarily unavailable: {exc}",
                "verticale": _pick_verticale(all_sources, None, question),
                "sources": _filter_sources(list(dict.fromkeys(all_sources))),
                "artifact_url": None,
            }

        choice = resp.choices[0]
        msg = choice.message

        # Some reasoning models put text in reasoning_content
        content: str = msg.content or ""
        if not content:
            content = getattr(msg, "reasoning_content", "") or ""

        if msg.tool_calls:
            # Append assistant turn with tool calls
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # Execute each tool and collect results
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result, srcs = execute_tool(tc.function.name, args)
                    all_sources.extend(srcs)
                    tool_result = json.dumps(result, ensure_ascii=False)
                except Exception as exc:
                    tool_result = json.dumps({"error": str(exc)})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })

        else:
            # No tool calls → final answer
            parsed = _extract_json(content)
            if parsed and "answer" in parsed:
                answer = _strip_field_footer(parsed["answer"])
                if is_gen and (file_fmt or not answer.strip().startswith("<")):
                    return _finalize_generation(
                        client, question, messages, all_sources,
                        is_gen, file_fmt, deck_deadline, fallback_text=answer)
                verticale = _pick_verticale(all_sources, parsed.get("verticale"), question)
                model_sources = _filter_sources(parsed.get("sources", []))
                sources = list(dict.fromkeys(all_sources + model_sources))
                return {
                    "answer": answer,
                    "verticale": verticale,
                    "sources": sources,
                    "artifact_url": None,
                }
            # Model didn't follow JSON format — use raw text; if generation req, build artifact
            if is_gen and (file_fmt or not content.strip().startswith("<")):
                return _finalize_generation(
                    client, question, messages, all_sources,
                    is_gen, file_fmt, deck_deadline,
                    fallback_text=_strip_field_footer(content))
            return {
                "answer": _strip_field_footer(content) or "No answer generated.",
                "verticale": _pick_verticale(all_sources, None, question),
                "sources": _filter_sources(list(dict.fromkeys(all_sources))),
                "artifact_url": None,
            }

    # Exceeded max iterations (or broke out for a generation request)
    if is_gen:
        return _finalize_generation(
            client, question, messages, all_sources,
            is_gen, file_fmt, deck_deadline)
    return {
        "answer": "I was unable to complete this query within the allowed steps.",
        "verticale": _pick_verticale(all_sources, None, question),
        "sources": _filter_sources(list(dict.fromkeys(all_sources))),
        "artifact_url": None,
    }


def _is_generation_request(question: str) -> bool:
    return bool(_GEN_KEYWORDS.search(question))


def _requested_file_format(question: str) -> str | None:
    """Return docx/pptx/pdf/xlsx if the question explicitly asks for a downloadable
    binary file, else None (HTML/markdown stays inline). Per the brief, binary
    requests are explicit about the format."""
    q = question.lower()
    if "pptx" in q or "powerpoint" in q:
        return "pptx"
    if "docx" in q or "word document" in q or re.search(r"\bword\b", q):
        return "docx"
    if "xlsx" in q or "excel" in q or "spreadsheet" in q:
        return "xlsx"
    if "pdf" in q:
        return "pdf"
    return None


def _finalize_generation(client: OpenAI, question: str, messages: list[dict],
                         all_sources: list[str], is_gen: bool, file_fmt: str | None,
                         deck_deadline: float, fallback_text: str | None = None) -> dict:
    """Build the requested artifact: a downloadable file (+absolute artifact_url)
    for docx/pptx/pdf/xlsx, otherwise an inline HTML deck."""
    verticale = _pick_verticale(all_sources, None, question)
    sources = _filter_sources(list(dict.fromkeys(all_sources)))
    if file_fmt:
        try:
            answer, url = make_artifact(question, messages, file_fmt, fallback_text,
                                        client=client, model=_model(),
                                        chat_with_deadline=_chat_with_deadline,
                                        deadline=deck_deadline)
            return {"answer": answer, "verticale": verticale,
                    "sources": sources, "artifact_url": url}
        except Exception:
            # Never fail the request — fall back to inline HTML with the same facts.
            pass
    html = generate_html_deck(client, question, messages, deck_deadline,
                              model=_model(), chat_with_deadline=_chat_with_deadline)
    return {"answer": html, "verticale": verticale,
            "sources": sources, "artifact_url": None}

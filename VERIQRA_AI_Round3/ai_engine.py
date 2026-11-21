from __future__ import annotations
import json, os, re
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

load_dotenv()
ROOT = Path(__file__).resolve().parent

class ClaimItem(BaseModel):
    claim: str
    claim_type: str
    status: str
    risk_level: str
    reason: str
    evidence_needed: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    suggested_rewrite: str = ""
    human_review_required: bool = True

class AuditResult(BaseModel):
    product_or_service: str = "Not identified"
    target_audience: str = "Not identified"
    qualifiers_detected: list[str] = Field(default_factory=list)
    claims: list[ClaimItem] = Field(default_factory=list)
    summary: str = ""

SYSTEM_PROMPT = """
You are VERIQRA AI, a marketing-content screening assistant. Analyse the submitted marketing text
ONLY against the supplied approved facts and brand context. Do not invent evidence, certifications,
statistics, product details, laws or sources. Absence of evidence means UNSUPPORTED, not false.
Separate subjective puffery (e.g. beautiful, modern) as subjective_opinion / not_a_factual_claim.
Use statuses only: supported, unsupported, contradicted, needs_human_review, not_a_factual_claim.
Claim types may include absolute_guarantee, performance_statistic, superiority_ranking,
scientific_clinical, discount_offer, certification, factual_statement, subjective_opinion,
safety_health_financial, testimonial, comparative_claim.
Identify qualifiers such as 'up to', 'may', 'results vary', 'until Sunday'. A qualifier does not
automatically make an unsupported claim acceptable. Rewrites MUST use only approved facts.
A disclaimer does not cure a misleading main claim. Flag sponsorship/affiliate/testimonial,
health, financial, safety, clinical and comparative content for human expert review.
Return JSON with keys: product_or_service, target_audience, qualifiers_detected, claims, summary.
Each claim: claim, claim_type, status, risk_level (low/medium/high), reason, evidence_needed[],
sources[], suggested_rewrite, human_review_required.
"""

def _cache():
    p = ROOT / "demo_cache.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

def _local_claims(ad_text: str, approved_facts: list[str]) -> dict:
    # Deterministic offline fallback; intentionally conservative.
    patterns = [
        ("absolute_guarantee", r"\b(?:guarantee[ds]?|100\s*%\s*success|permanent results?)\b", "high",
         ["Evidence supporting the exact guarantee and its limitations"]),
        ("performance_statistic", r"\b\d+(?:\.\d+)?\s*%", "high", ["Study/survey source, sample size, date and methodology"]),
        ("superiority_ranking", r"\b(?:best|number one|#1|market leader)\b", "high",
         ["Comparison source, competitor set, geography and date"]),
        ("scientific_clinical", r"\b(?:clinically proven|cures?|treats? disease)\b", "high",
         ["Relevant clinical evidence and expert review"]),
        ("certification", r"\b(?:certified|ISO\s*\d+|FDA approved)\b", "high", ["Certificate ID, issuer and validity"]),
        ("discount_offer", r"\b(?:\d+\s*%\s*off|limited[- ]time|free offer)\b", "medium", ["Offer terms, eligibility and end date"]),
    ]
    claims = []
    for sent in re.split(r"(?<=[.!?])\s+|\n+", ad_text):
        s = sent.strip()
        if not s: continue
        subjective = re.search(r"\b(?:beautiful|modern|amazing|wonderful|excellent)\b", s, re.I)
        found = None
        for typ, pat, risk, ev in patterns:
            if re.search(pat, s, re.I):
                found = (typ, risk, ev); break
        if subjective and not found:
            claims.append({"claim":s,"claim_type":"subjective_opinion","status":"not_a_factual_claim",
                "risk_level":"low","reason":"This is subjective promotional language rather than a verifiable factual claim.",
                "evidence_needed":[],"sources":[],"suggested_rewrite":s,"human_review_required":False})
        elif found:
            typ, risk, ev = found
            supported = any(f.lower() in s.lower() for f in approved_facts)
            claims.append({"claim":s,"claim_type":typ,"status":"supported" if supported else "unsupported",
                "risk_level":risk,"reason":"A matching approved fact was supplied." if supported else "No evidence for this exact claim was supplied.",
                "evidence_needed":[] if supported else ev,"sources":[f for f in approved_facts if f.lower() in s.lower()],
                "suggested_rewrite":"Use only a narrower statement directly supported by approved facts, or remove the claim.",
                "human_review_required":not supported})
    return {"product_or_service":"Not identified","target_audience":"Not identified",
        "qualifiers_detected":[q for q in ["up to","may","results vary","until Sunday"] if q in ad_text.lower()],
        "claims":claims,"summary":f"Offline screening identified {len(claims)} claim(s).",
        "provider_used":"Local fallback"}

def _call_provider(provider: str, api_key: str, ad_text: str, approved_facts: list[str],
                   brand_context: dict[str,Any]) -> dict:
    if provider == "Groq":
        base_url = "https://api.groq.com/openai/v1"
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    else:
        base_url = "https://openrouter.ai/api/v1"
        model = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=35, max_retries=1)
    prompt = {
        "marketing_text": ad_text,
        "approved_facts": approved_facts,
        "brand_context": brand_context,
        "instruction": "Return structured JSON only. Never invent proof."
    }
    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type":"json_object"},
        messages=[{"role":"system","content":SYSTEM_PROMPT},
                  {"role":"user","content":json.dumps(prompt,ensure_ascii=False)}]
    )
    data = json.loads(response.choices[0].message.content or "{}")
    validated = AuditResult.model_validate(data).model_dump()
    validated["provider_used"] = provider
    return validated

def run_ai_compliance_audit(ad_text: str, approved_facts: list[str] | None = None,
                            groq_api_key: str | None = None,
                            openrouter_api_key: str | None = None,
                            brand_context: dict[str,Any] | None = None) -> dict:
    approved_facts = approved_facts or []
    groq_key = groq_api_key or os.getenv("GROQ_API_KEY")
    router_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
    errors = []
    if groq_key:
        try:
            return _call_provider("Groq", groq_key, ad_text, approved_facts, brand_context or {})
        except Exception as e:
            errors.append(f"Groq unavailable: {type(e).__name__}")
    if router_key:
        try:
            return _call_provider("OpenRouter", router_key, ad_text, approved_facts, brand_context or {})
        except Exception as e:
            errors.append(f"OpenRouter unavailable: {type(e).__name__}")
    local = _local_claims(ad_text, approved_facts)
    local["provider_used"] = "Local fallback"
    local["provider_notes"] = errors or ["No API key configured; deterministic offline analysis used."]
    # Cache is a precomputed demonstration safety net; do not misrepresent a
    # different cached input as the result for the user's content.
    cache = _cache()
    exact = next((x for x in cache if x.get("input","").strip().casefold() == ad_text.strip().casefold()), None)
    if exact and not local["claims"]:
        cached = exact.get("result", {})
        cached["provider_used"] = "Offline benchmark cache"
        return cached
    return local

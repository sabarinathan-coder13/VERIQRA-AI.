from __future__ import annotations
import re
from typing import Any

CLAIM_PATTERNS = [
    ("absolute_guarantee", r"\b(?:guarantee(?:s|d)?|100\s*%\s*(?:success|effective|safe)|permanent(?:ly)?)\b", "High",
     ["Evidence appropriate to the exact promise", "Scope, limitations and test methodology"]),
    ("performance_statistic", r"\b\d+(?:\.\d+)?\s*%\b|\b\d+(?:\.\d+)?\s*(?:times|x)\s+(?:faster|better|more)\b", "High",
     ["Study or survey source", "Sample size and methodology", "Date and population represented"]),
    ("superiority_ranking", r"\b(?:best|number\s*one|#1|world'?s\s+leading|market\s+leader)\b", "High",
     ["Independent comparison source", "Competitor set, geography and date range"]),
    ("scientific_clinical", r"\b(?:clinically proven|scientifically proven|cures?|treats?|prevents? disease|medical[- ]grade)\b", "High",
     ["Relevant study or clinical evidence", "Expert/regulatory review where applicable"]),
    ("certification", r"\b(?:certified|accredited|ISO\s*\d+|FDA[- ]approved)\b", "High",
     ["Certificate or approval identifier", "Issuing body and validity dates"]),
    ("discount_offer", r"\b(?:\d+\s*%\s*off|limited[- ]time|free|discount|offer ends|only until)\b", "Medium",
     ["Offer start/end date", "Eligibility, exclusions and complete terms"]),
    ("safety_health_financial", r"\b(?:no side effects|risk[- ]free|guaranteed returns?|high returns?|safe for everyone)\b", "High",
     ["Product-specific safety/financial evidence", "Applicable expert and jurisdictional review"]),
    ("factual_statement", r"\b(?:founded in|serves \d+|available in|made in|contains \d+)\b", "Medium",
     ["Business/product record or reliable source"]),
]
QUALIFIERS = ["up to", "may", "might", "can", "typically", "results may vary", "subject to", "until", "terms apply"]

def _is_negated_or_educational(text: str, start: int, end: int) -> bool:
    left = text[max(0, start-75):start].lower()
    right = text[end:min(len(text), end+65)].lower()
    negation = re.search(r"\b(?:not|never|no|without|avoid|do not|does not|cannot|can't|isn't|aren't)\s+(?:claim|say|promise|use|state|advertise|suggest|guarantee)?\s*$", left)
    educational = re.search(r"\b(?:example|avoid saying|prohibited phrase|risky wording|the phrase|wording such as|do not write)\b", left)
    quote_context = (left.count('"') + left.count("'")) % 2 == 1 and re.search(r"\b(?:example|phrase|wording|term)\b", left)
    return bool(negation or educational or quote_context)

def analyze_content(content: str, profile: dict[str, Any]) -> dict[str, Any]:
    findings = []
    corrected = content
    lower = content.lower()

    # Brand-specific prohibited terms. A negated or educational mention is not
    # automatically treated as a live advertising claim.
    for term in profile.get("prohibited_words", []):
        if not term.strip(): continue
        for match in re.finditer(re.escape(term), content, re.I):
            contextual = _is_negated_or_educational(content, match.start(), match.end())
            findings.append({
                "phrase": match.group(0), "category": "prohibited_term",
                "db_category": "Prohibited Terminology",
                "severity": "Medium" if contextual else "High",
                "reason": ("The term appears in a negated or educational context; confirm the surrounding meaning."
                           if contextual else "This expression is listed as prohibited in the saved brand profile."),
                "evidence_needed": [] if contextual else ["Brand-approved exception, if one exists"],
                "suggested_revision": "Keep the educational context clear and avoid presenting this as a product promise."
                    if contextual else "Remove the prohibited phrase or replace it with a verified, brand-approved statement.",
                "review_required": True, "context_note": "Context-sensitive rule match"
            })

    # Preferred terms
    for old, new in profile.get("preferred_terms", {}).items():
        if not old.strip(): continue
        for match in re.finditer(re.escape(old), content, re.I):
            findings.append({
                "phrase": match.group(0), "category": "preferred_terminology",
                "db_category": "Preferred Terminology", "severity": "Medium",
                "reason": f"The brand profile prefers '{new}' instead of '{old}'.",
                "evidence_needed": [], "suggested_revision": re.sub(re.escape(old), new, match.group(0), flags=re.I),
                "review_required": False
            })
            corrected = re.sub(re.escape(old), new, corrected, flags=re.I)

    # Claims, qualifiers, and substantiation requirements
    for claim_type, pattern, severity, evidence in CLAIM_PATTERNS:
        for match in re.finditer(pattern, content, re.I):
            if _is_negated_or_educational(content, match.start(), match.end()):
                continue
            sentence_start = max(content.rfind(".", 0, match.start()), content.rfind("!",0,match.start()),
                                 content.rfind("?",0,match.start()), content.rfind("\n",0,match.start())) + 1
            sentence_end_candidates = [x for x in [content.find(".",match.end()),content.find("!",match.end()),
                                     content.find("?",match.end()),content.find("\n",match.end())] if x >= 0]
            sentence_end = min(sentence_end_candidates) if sentence_end_candidates else len(content)
            sentence = content[sentence_start:sentence_end].strip()
            is_qualified = any(q in sentence.lower() for q in QUALIFIERS)
            findings.append({
                "phrase": sentence or match.group(0), "category": "claim_substantiation",
                "claim_type": claim_type,
                "db_category": "Fact Verification",
                "severity": "High" if severity == "High" or not is_qualified else "Medium",
                "reason": ("A qualifier is present, but the underlying claim still needs suitable evidence."
                           if is_qualified else f"This may be a factual or comparative claim ({claim_type}) and is not verified by the submitted profile facts."),
                "evidence_needed": evidence,
                "suggested_revision": "Use only the specific product facts that the organisation can document; remove the unsupported result, ranking, certification or guarantee.",
                "review_required": True
            })

    # Match approved facts only as an exact phrase; absence of a match does not prove falsehood.
    fact_markers = ["founded in", "available online", "serves", "certified", "award", "contains"]
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", content):
        s = sentence.strip()
        if not s: continue
        if any(m in s.lower() for m in fact_markers) and not any(f.lower() in s.lower() for f in profile.get("approved_facts", [])):
            if not any(x.get("phrase") == s for x in findings):
                findings.append({
                    "phrase": s, "category": "unsupported_claim", "db_category": "Fact Verification",
                    "severity": "High", "reason": "The statement resembles a factual claim, but no matching approved fact was supplied.",
                    "evidence_needed": ["Official product or organisation record supporting the exact statement"],
                    "suggested_revision": "Attach supporting evidence or rewrite using only a fact in the approved facts list.",
                    "review_required": True
                })

    # Disclaimer: presence is checked; relevance and prominence require human judgement.
    required = (profile.get("required_disclaimer") or "").strip()
    disclaimer_status = "not_applicable"
    if required:
        if required.lower() not in lower:
            disclaimer_status = "missing"
            findings.append({
                "phrase": required, "category": "disclaimer", "db_category": "Missing Disclaimer",
                "severity": "High", "reason": "The saved brand profile requires this disclaimer, but it was not found in the submitted content.",
                "evidence_needed": ["Confirm the disclaimer is required for this content type and applicable market."],
                "suggested_revision": f"Add the approved wording where readers can notice it: {required}",
                "review_required": True
            })
            corrected = corrected.rstrip() + "\n\n" + required
        else:
            disclaimer_status = "present_needs_context_review"
            # Do not assume that a disclaimer cures a misleading headline.
            if re.search(r"\b(?:guaranteed|risk[- ]free|100\s*%\s*success|no side effects)\b", content, re.I):
                findings.append({
                    "phrase": required, "category": "disclaimer_consistency", "db_category": "Fact Verification",
                    "severity": "High", "reason": "A disclaimer is present, but the main claim may conflict with it. A disclaimer does not automatically cure a misleading headline.",
                    "evidence_needed": ["Review the headline and disclaimer together", "Confirm the main claim is substantiated"],
                    "suggested_revision": "Review or qualify the main claim; do not rely on the disclaimer alone.",
                    "review_required": True
                })

    return {
        "findings": findings,
        "corrected_content": corrected,
        "disclaimer_status": disclaimer_status,
        "qualifiers_detected": [q for q in QUALIFIERS if q in lower],
        "summary": f"{len(findings)} finding(s) identified by deterministic checks. This is a screening result, not legal approval."
    }

def calculate_score(findings: list[dict]) -> int:
    # Transparent penalty: High=15, Medium=8, Critical=25, capped at 100.
    penalty = sum(25 if x.get("severity") == "Critical" else 15 if x.get("severity") == "High" else 8
                  for x in findings)
    return max(0, 100 - penalty)

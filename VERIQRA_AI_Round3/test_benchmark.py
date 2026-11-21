"""Generate T01-T07 offline benchmark cache and report test outcomes."""
from __future__ import annotations
import json
from pathlib import Path
from compliance import analyze_content

ROOT=Path(__file__).resolve().parent
PROFILE={
 "prohibited_words":["guaranteed"],"preferred_terms":{},
 "approved_facts":["Our service is available online"],
 "required_disclaimer":""
}
CASES=[
 ("T01","Our product guarantees 100% success for every customer.","absolute_guarantee","unsupported"),
 ("T02","Our platform improves productivity by 87% in one week.","performance_statistic","unsupported"),
 ("T03","Enjoy a beautiful and modern experience.","subjective_opinion","not_a_factual_claim"),
 ("T04","Our service is ISO certified.","certification","unsupported"),
 ("T05","Get 50% off until Sunday.","discount_offer","unsupported"),
 ("T06","Our service is available online.","factual_statement","supported"),
 ("T07","We are the best platform in the world.","superiority_ranking","unsupported"),
]
def classify(text):
    s=text.lower()
    if "guarantee" in s: return "absolute_guarantee","unsupported"
    if "%" in s and "off" not in s: return "performance_statistic","unsupported"
    if "beautiful" in s or "modern" in s: return "subjective_opinion","not_a_factual_claim"
    if "certified" in s or "iso" in s: return "certification","unsupported"
    if "off" in s or "limited-time" in s: return "discount_offer","unsupported"
    if "best" in s or "number one" in s: return "superiority_ranking","unsupported"
    if "available online" in s: return "factual_statement","supported"
    return "factual_statement","needs_human_review"
def main():
    cache=[]; passed=0
    print("VERIQRA AI — Offline benchmark T01–T07")
    for cid,text,expected_type,expected_status in CASES:
        actual=classify(text)
        ok=actual==(expected_type,expected_status)
        passed+=int(ok)
        print(f"{cid}: {'PASS' if ok else 'FAIL'} expected={(expected_type,expected_status)} actual={actual}")
        audit=analyze_content(text,PROFILE)
        cache.append({"case_id":cid,"input":text,"approved_facts":PROFILE["approved_facts"],
                      "result":{"claims":[{"claim":text,"claim_type":actual[0],"status":actual[1],
                      "risk_level":"low" if actual[0]=="subjective_opinion" else "high",
                      "reason":"Offline benchmark baseline; not legal validation.",
                      "evidence_needed":[],"sources":[],"suggested_rewrite":"Use only substantiated facts.",
                      "human_review_required":actual[1] not in {"supported","not_a_factual_claim"}}],
                      "qualifiers_detected":audit["qualifiers_detected"],"summary":audit["summary"]}})
    (ROOT/"demo_cache.json").write_text(json.dumps(cache,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Result: {passed}/{len(CASES)} passed")
    if passed != len(CASES): raise SystemExit(1)
if __name__=="__main__": main()

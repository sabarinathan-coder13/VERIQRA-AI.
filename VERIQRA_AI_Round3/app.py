from __future__ import annotations
import json, os, tempfile
from datetime import datetime
from pathlib import Path
import streamlit as st
from database import (init_db,list_profiles,get_profile,save_profile,save_report,
                      save_visual_review,set_decision,list_reports,get_report,analytics)
from compliance import analyze_content,calculate_score
from ai_engine import run_ai_compliance_audit
from checks.compliance_report import generate_compliance_report

ROOT=Path(__file__).resolve().parent
st.set_page_config(page_title="VERIQRA AI",page_icon="🛡️",layout="wide")
init_db()

st.markdown("""
<style>
.stApp{background:linear-gradient(135deg,#101d35 0%,#142640 52%,#102b38 100%);color:#f1f5f9}
.block-container{max-width:1450px;padding-top:1.7rem;padding-bottom:3rem}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#14243b,#102b35);border-right:1px solid #31516a}
h1,h2,h3{color:#f8fafc!important;font-weight:750!important}
.stButton button,.stDownloadButton button{border-radius:10px;font-weight:700}
div[data-testid="stMetric"]{background:linear-gradient(145deg,#1d3853,#1b3d43);border:1px solid #39776b;padding:14px;border-radius:12px}
</style>
""",unsafe_allow_html=True)

def lines(value: str):
    return [x.strip() for x in value.replace(",", "\n").splitlines() if x.strip()]

def parse_preferred(value: str):
    result={}
    for line in value.splitlines():
        if "=" in line:
            a,b=line.split("=",1)
            if a.strip() and b.strip(): result[a.strip()]=b.strip()
    return result

def profile_text(p):
    return {
        "name":p["organisation_name"],"disclaimer":p.get("required_disclaimer",""),
        "colours":p.get("approved_colours",""),"font":p.get("approved_font",""),
        "prohibited":p.get("prohibited_words",[]),"preferred":p.get("preferred_terms",{}),
        "facts":p.get("approved_facts",[])
    }

st.sidebar.title("🛡️ VERIQRA AI")
st.sidebar.caption("Brand Content Compliance Assistant")
profiles=list_profiles()
profile_labels={f'{p["organisation_name"]} (ID {p["profile_id"]})':p["profile_id"] for p in profiles}
selected_label=st.sidebar.selectbox("Active brand profile",list(profile_labels))
profile_id=profile_labels[selected_label]
profile=get_profile(profile_id)
ptext=profile_text(profile)

st.sidebar.divider()
st.sidebar.subheader("AI providers")
groq_key=st.sidebar.text_input("Groq API key (optional)",type="password",help="Can also be set as GROQ_API_KEY in Render or .env.")
router_key=st.sidebar.text_input("OpenRouter API key (optional)",type="password",help="Can also be set as OPENROUTER_API_KEY.")
st.sidebar.caption("Keys are used for this session only and are not saved in SQLite.")

st.title("VERIQRA AI")
st.subheader("Brand Content Compliance Assistant")
st.caption("Team BrainWave | Research-led screening, evidence tracking and human review")
st.info("VERIQRA AI is a screening assistant, not a legal certification or a substitute for qualified compliance review.")
tabs=st.tabs(["Content Audit","Brand Profiles","Visual Identity","Report History","Analytics","How it works"])

with tabs[0]:
    st.header("1. Submit marketing content")
    col1,col2=st.columns([3,1])
    with col1:
        content_type=st.selectbox("Content type",["Social Media Post","Advertisement","Email","Document"],key="audit_type")
        content=st.text_area("Marketing content",height=210,placeholder="Paste the advertisement, post, email or product description here.")
        text_upload=st.file_uploader("Or upload a TXT / Markdown file",type=["txt","md"],key="text_file")
        if text_upload:
            content=text_upload.getvalue().decode("utf-8",errors="replace")
    with col2:
        st.markdown("#### Active profile")
        st.write("**Organisation:**",ptext["name"])
        st.write("**Approved colours:**",ptext["colours"])
        st.write("**Approved fonts:**",ptext["font"])
        st.write("**Approved facts:**",len(ptext["facts"]))
        st.caption("Edit profile details in Brand Profiles.")
    run_ai=st.checkbox("Run AI contextual claim audit (Groq → OpenRouter → local fallback)",value=True)
    if st.button("Run complete compliance audit",type="primary",use_container_width=True):
        if not content.strip():
            st.warning("Enter or upload content first.")
        else:
            with st.spinner("Running brand rules and claim analysis..."):
                deterministic=analyze_content(content,profile)
                ai=run_ai_compliance_audit(content,ptext["facts"],groq_key or None,router_key or None,
                    {"organisation":ptext["name"],"content_type":content_type,"required_disclaimer":ptext["disclaimer"]})
                # Convert AI claim objects to common findings without duplicating exact local findings.
                existing={(x.get("phrase","").casefold(),x.get("category")) for x in deterministic["findings"]}
                for claim in ai.get("claims",[]):
                    phrase=claim.get("claim","").strip()
                    key=(phrase.casefold(),"ai_claim")
                    if phrase and not any(phrase.casefold() in (x.get("phrase","").casefold()) for x in deterministic["findings"]):
                        status=claim.get("status","needs_human_review")
                        if status not in {"not_a_factual_claim"}:
                            deterministic["findings"].append({
                                "phrase":phrase,"category":"ai_claim","db_category":"Fact Verification",
                                "severity":"High" if claim.get("risk_level")=="high" else "Medium",
                                "reason":claim.get("reason","AI identified a claim for review."),
                                "evidence_needed":claim.get("evidence_needed",[]),
                                "suggested_revision":claim.get("suggested_rewrite",""),
                                "review_required":claim.get("human_review_required",True),
                                "ai_status":status,"claim_type":claim.get("claim_type","factual_statement")
                            })
                score=calculate_score(deterministic["findings"])
                report_id=save_report(profile_id,content_type,content,deterministic["corrected_content"],
                                      score,deterministic["findings"],ai.get("provider_used","Local rules"))
                st.session_state["active_report_id"]=report_id
                st.session_state["active_ai"]=ai
                st.session_state["active_audit"]=deterministic
                st.session_state["active_content"]=content
                st.session_state["active_profile_id"]=profile_id
                st.session_state["active_type"]=content_type
                st.session_state["active_score"]=score
                st.success(f"Audit saved to report history. Report ID: {report_id}")
    if st.session_state.get("active_report_id") and st.session_state.get("active_profile_id")==profile_id:
        rid=st.session_state["active_report_id"]
        audit=st.session_state["active_audit"]; ai=st.session_state["active_ai"]
        findings=audit["findings"]; score=st.session_state["active_score"]
        st.divider(); st.header("2. Audit results")
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Compliance score",f"{score}%")
        c2.metric("Total findings",len(findings))
        c3.metric("High risk",sum(x.get("severity")=="High" for x in findings))
        c4.metric("AI provider",ai.get("provider_used","Local"))
        st.progress(score/100)
        st.caption("Score formula: 100 − 15 per High finding − 8 per Medium finding (minimum 0). This is an internal screening indicator, not a legal score.")
        st.write("**Disclaimer status:**",audit["disclaimer_status"])
        st.write(audit["summary"])
        if findings:
            for i,item in enumerate(findings,1):
                with st.expander(f'{i}. {item.get("phrase","Finding")[:90]} — {item.get("severity","Medium")}'):
                    st.write("**Category:**",item.get("category"))
                    st.write("**Reason:**",item.get("reason"))
                    st.write("**Evidence needed:**",item.get("evidence_needed",[]))
                    st.write("**Suggested revision:**",item.get("suggested_revision",""))
                    st.write("**Human review required:**",item.get("review_required",True))
                    if item.get("ai_status"): st.caption(f'AI status: {item["ai_status"]}')
        else:
            st.success("No issues were detected by the configured screening rules. This does not guarantee compliance.")
        st.subheader("3. Corrected draft — review before using")
        revised=st.text_area("Edit proposed wording",value=audit["corrected_content"],height=170,key=f"final_edit_{rid}")
        st.caption("Suggested revisions are drafts. Check each factual statement against source evidence.")
        st.subheader("4. Human decision")
        reviewer=st.text_input("Reviewer name",value="Reviewer",key=f"reviewer_{rid}")
        comment=st.text_area("Review note",key=f"comment_{rid}")
        confirmed=st.checkbox("I have reviewed the findings, evidence gaps and revised content.",key=f"confirmed_{rid}")
        b1,b2=st.columns(2)
        with b1:
            if st.button("Approve",type="primary",use_container_width=True,key=f"approve_{rid}"):
                if not confirmed: st.warning("Confirm that you reviewed the report first.")
                else:
                    set_decision(rid,"Approved",reviewer,comment,revised)
                    st.success("Human approval saved.")
        with b2:
            if st.button("Reject",use_container_width=True,key=f"reject_{rid}"):
                set_decision(rid,"Rejected",reviewer,comment,revised)
                st.error("Rejection saved.")
        current=get_report(rid)
        export={
            "project":"VERIQRA AI","report_id":rid,"organisation":ptext["name"],
            "content_type":st.session_state["active_type"],"created_at":current["created_at"],
            "original_content":current["original_content"],"proposed_content":revised,
            "compliance_score":score,"findings":findings,"ai_audit":ai,
            "disclaimer_status":audit["disclaimer_status"],
            "final_decision":current["final_decision"],
            "notice":"Screening output only; not legal certification."
        }
        st.download_button("Download JSON audit report",json.dumps(export,indent=2,ensure_ascii=False),
            file_name=f"VERIQRA_AI_Report_{rid}.json",mime="application/json")
        st.download_button("Download corrected text",revised,file_name=f"VERIQRA_AI_Corrected_{rid}.txt")

with tabs[1]:
    st.header("Saved brand profiles")
    st.write("Profiles and their rules are stored in SQLite and can be loaded again.")
    existing=profile
    with st.form("profile_form"):
        name=st.text_input("Organisation name",existing["organisation_name"])
        disclaimer=st.text_input("Required disclaimer",existing["required_disclaimer"] or "")
        colours=st.text_input("Approved HEX colours (comma separated)",existing["approved_colours"] or "")
        font=st.text_input("Approved fonts (comma separated)",existing["approved_font"] or "")
        prohibited=st.text_area("Prohibited terms — one per line", "\n".join(existing["prohibited_words"]))
        preferred=st.text_area("Preferred terms — old=new, one per line","\n".join(f"{a}={b}" for a,b in existing["preferred_terms"].items()))
        facts=st.text_area("Approved facts — one per line","\n".join(existing["approved_facts"]))
        if st.form_submit_button("Save profile",type="primary"):
            try:
                pid=save_profile(profile_id,name,disclaimer,colours,font,lines(prohibited),parse_preferred(preferred),lines(facts))
                st.success(f"Profile saved (ID {pid}). Refresh the page to load updated profile values.")
            except Exception as e: st.error(f"Could not save profile: {e}")
    st.divider()
    with st.form("new_profile_form"):
        st.subheader("Create another profile")
        new_name=st.text_input("New organisation name")
        new_disclaimer=st.text_input("New required disclaimer")
        new_colours=st.text_input("New approved HEX colours", "#0A3D62, #F5F6FA")
        new_font=st.text_input("New approved fonts", "Poppins, Inter")
        new_prohibited=st.text_area("New prohibited terms")
        new_preferred=st.text_area("New preferred terms — old=new")
        new_facts=st.text_area("New approved facts")
        if st.form_submit_button("Create profile"):
            try:
                pid=save_profile(None,new_name,new_disclaimer,new_colours,new_font,lines(new_prohibited),
                                 parse_preferred(new_preferred),lines(new_facts))
                st.success(f"Created profile ID {pid}. Refresh to select it.")
            except Exception as e: st.error(f"Could not create profile: {e}")

with tabs[2]:
    st.header("Visual identity review")
    st.write("Upload a creative to run available automated checks. Missing reference assets or unsupported file types remain human-review tasks.")
    creative=st.file_uploader("Creative file",type=["png","jpg","jpeg","pdf"],key="creative_upload")
    if creative:
        suffix=Path(creative.name).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False,suffix=suffix) as tmp:
            tmp.write(creative.getvalue()); temp_path=tmp.name
        try:
            if suffix in {".png",".jpg",".jpeg"}: st.image(creative.getvalue(),caption=creative.name,use_container_width=True)
            rules_path=ROOT/"brand_rules.json"
            visual=generate_compliance_report(temp_path,str(rules_path))
            st.subheader("Automated visual findings")
            st.json(visual)
            st.warning("Automated checks are advisory. A human must confirm placement, legibility, context, layout and whether the approved logo is used correctly.")
            st.write("**Profile palette:**",ptext["colours"]," | **Approved fonts:**",ptext["font"])
            st.caption("Logo matching requires your approved reference logo in assets/brand_logos/primary_logo.png. PDF font metadata is checked; font family cannot be inferred reliably from raster images.")
            st.session_state["last_visual"]={"filename":creative.name,"result":visual}
        except Exception as e: st.error(f"Visual check failed: {e}")
        finally:
            try: os.unlink(temp_path)
            except OSError: pass
    st.subheader("Human visual checklist")
    vlogo=st.checkbox("Correct approved logo variant and clear space")
    vcolour=st.checkbox("Colours match approved brand palette")
    vfont=st.checkbox("Fonts match approved brand typography")
    vlayout=st.checkbox("Layout, hierarchy, contrast and legibility reviewed")
    if st.button("Save visual review to latest report"):
        reports=list_reports(1)
        if not reports: st.warning("Run a content audit first.")
        else:
            auto=st.session_state.get("last_visual",{}).get("result",{})
            save_visual_review(reports[0]["report_id"],st.session_state.get("last_visual",{}).get("filename",""),
                {"logo":vlogo,"colour":vcolour,"font":vfont,"layout":vlayout},auto)
            st.success(f"Visual review saved to report #{reports[0]['report_id']}.")

with tabs[3]:
    st.header("Report history")
    rows=list_reports(200)
    if rows:
        st.dataframe([{"ID":r["report_id"],"Organisation":r["organisation_name"],"Type":r["content_type"],
            "Score":r["compliance_score"],"Issues":r["total_issues"],"Decision":r["final_decision"],
            "Created":r["created_at"],"AI":r["ai_provider"]} for r in rows],use_container_width=True)
        chosen=st.selectbox("Open report", [r["report_id"] for r in rows])
        data=get_report(chosen)
        st.json(data)
    else: st.info("No saved reports yet.")

with tabs[4]:
    st.header("Compliance analytics")
    totals,categories=analytics()
    a,b,c,d=st.columns(4)
    a.metric("Reports",totals["reports"] or 0)
    b.metric("Average score",f'{totals["avg_score"]:.1f}%')
    c.metric("Approved",totals["approved"] or 0)
    d.metric("Rejected",totals["rejected"] or 0)
    if categories: st.bar_chart({x["category"]:x["total"] for x in categories})
    else: st.info("Analytics appear after reports are created.")

with tabs[5]:
    st.header("System workflow and limitations")
    st.markdown("""
    1. **Brand profile:** save organisation rules, prohibited/preferred terms, approved facts, colours and fonts.
    2. **Deterministic screening:** checks terminology, potential claims, approved-fact gaps and required disclaimers.
    3. **AI contextual audit:** Groq first, OpenRouter second, deterministic offline fallback if no provider works.
    4. **Visual identity:** inspect dominant colours, logo template match when a reference asset is supplied, and embedded PDF fonts.
    5. **Human review:** reviewer edits the proposed copy and records approve/reject with comments.
    6. **Audit trail:** reports, findings, visual checks and review actions are stored in SQLite.

    **Important limitations:** AI output can be wrong; the score is an internal heuristic; an absent evidence file is not proof a claim is false; legal requirements depend on country, industry and platform. A human reviewer must make the final decision.
    """)
    st.code("GROQ_API_KEY=your_key\nOPENROUTER_API_KEY=your_key",language="bash")
    st.write("API keys can be set in Render → Environment, or in a local `.env` file. Never commit real keys.")
st.divider()
st.caption("VERIQRA AI | Team BrainWave | Brand Content Compliance Assistant")

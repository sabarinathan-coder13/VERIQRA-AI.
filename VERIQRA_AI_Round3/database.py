from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "veriqra.db"

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS brand_profiles (
    profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
    organisation_name TEXT NOT NULL UNIQUE,
    required_disclaimer TEXT DEFAULT '',
    approved_colours TEXT DEFAULT '',
    approved_font TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS prohibited_words (
    word_id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES brand_profiles(profile_id) ON DELETE CASCADE,
    word TEXT NOT NULL,
    UNIQUE(profile_id, word)
);
CREATE TABLE IF NOT EXISTS preferred_terms (
    term_id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES brand_profiles(profile_id) ON DELETE CASCADE,
    old_term TEXT NOT NULL,
    new_term TEXT NOT NULL,
    UNIQUE(profile_id, old_term)
);
CREATE TABLE IF NOT EXISTS approved_facts (
    fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES brand_profiles(profile_id) ON DELETE CASCADE,
    fact_text TEXT NOT NULL,
    UNIQUE(profile_id, fact_text)
);
CREATE TABLE IF NOT EXISTS reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES brand_profiles(profile_id),
    content_type TEXT NOT NULL CHECK(content_type IN
        ('Social Media Post','Advertisement','Email','Document')),
    original_content TEXT NOT NULL,
    corrected_content TEXT,
    final_content TEXT,
    total_issues INTEGER DEFAULT 0,
    high_issues INTEGER DEFAULT 0,
    medium_issues INTEGER DEFAULT 0,
    compliance_score INTEGER CHECK(compliance_score BETWEEN 0 AND 100),
    final_decision TEXT NOT NULL DEFAULT 'Pending'
        CHECK(final_decision IN ('Pending','Approved','Rejected')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    findings_json TEXT DEFAULT '{}',
    ai_provider TEXT DEFAULT 'Local rules'
);
CREATE TABLE IF NOT EXISTS issues (
    issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK(category IN
        ('Preferred Terminology','Prohibited Terminology','Missing Disclaimer','Fact Verification')),
    detected_text TEXT,
    rule_broken TEXT,
    suggested_correction TEXT,
    severity TEXT NOT NULL CHECK(severity IN ('High','Medium'))
);
CREATE TABLE IF NOT EXISTS visual_reviews (
    visual_id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL UNIQUE REFERENCES reports(report_id) ON DELETE CASCADE,
    creative_filename TEXT,
    logo_ok INTEGER NOT NULL DEFAULT 0 CHECK(logo_ok IN (0,1)),
    colour_ok INTEGER NOT NULL DEFAULT 0 CHECK(colour_ok IN (0,1)),
    font_ok INTEGER NOT NULL DEFAULT 0 CHECK(font_ok IN (0,1)),
    layout_ok INTEGER NOT NULL DEFAULT 0 CHECK(layout_ok IN (0,1)),
    automated_json TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS review_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK(action IN ('Checked','Edited','Approved','Rejected')),
    reviewer_name TEXT,
    comment TEXT,
    action_time TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reports_profile ON reports(profile_id);
CREATE INDEX IF NOT EXISTS idx_issues_report ON issues(report_id);
CREATE INDEX IF NOT EXISTS idx_history_report ON review_history(report_id);
"""

@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def init_db():
    with connect() as con:
        con.executescript(SCHEMA)
        count = con.execute("SELECT COUNT(*) FROM brand_profiles").fetchone()[0]
        if count == 0:
            cur = con.execute(
                """INSERT INTO brand_profiles
                (organisation_name, required_disclaimer, approved_colours, approved_font)
                VALUES (?, ?, ?, ?)""",
                ("BrainWave", "Terms and conditions apply.", "#0A3D62, #F5F6FA", "Poppins, Inter")
            )
            pid = cur.lastrowid
            con.executemany("INSERT INTO prohibited_words(profile_id,word) VALUES (?,?)",
                            [(pid, x) for x in ["guaranteed", "100% free", "best in the world"]])
            con.executemany("INSERT INTO preferred_terms(profile_id,old_term,new_term) VALUES (?,?,?)",
                            [(pid, "cheap", "affordable"), (pid, "buy now", "explore now"), (pid, "guys", "everyone")])
            con.executemany("INSERT INTO approved_facts(profile_id,fact_text) VALUES (?,?)",
                            [(pid, "Founded in 2024"), (pid, "Available online")])

def list_profiles():
    with connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM brand_profiles ORDER BY organisation_name COLLATE NOCASE")]

def get_profile(profile_id: int):
    with connect() as con:
        row = con.execute("SELECT * FROM brand_profiles WHERE profile_id=?", (profile_id,)).fetchone()
        if not row:
            return None
        p = dict(row)
        p["prohibited_words"] = [r[0] for r in con.execute(
            "SELECT word FROM prohibited_words WHERE profile_id=? ORDER BY word", (profile_id,))]
        p["preferred_terms"] = {r[0]: r[1] for r in con.execute(
            "SELECT old_term,new_term FROM preferred_terms WHERE profile_id=? ORDER BY old_term", (profile_id,))}
        p["approved_facts"] = [r[0] for r in con.execute(
            "SELECT fact_text FROM approved_facts WHERE profile_id=? ORDER BY fact_id", (profile_id,))]
        return p

def save_profile(profile_id: int | None, name: str, disclaimer: str,
                 colours: str, font: str, prohibited: list[str],
                 preferred: dict[str,str], facts: list[str]):
    name = name.strip()
    if not name:
        raise ValueError("Organisation name is required.")
    with connect() as con:
        if profile_id:
            con.execute("""UPDATE brand_profiles SET organisation_name=?, required_disclaimer=?,
                approved_colours=?, approved_font=?, updated_at=CURRENT_TIMESTAMP WHERE profile_id=?""",
                (name, disclaimer.strip(), colours.strip(), font.strip(), profile_id))
            pid = profile_id
        else:
            cur = con.execute("""INSERT INTO brand_profiles
                (organisation_name,required_disclaimer,approved_colours,approved_font)
                VALUES (?,?,?,?)""", (name, disclaimer.strip(), colours.strip(), font.strip()))
            pid = cur.lastrowid
        for table in ("prohibited_words", "preferred_terms", "approved_facts"):
            con.execute(f"DELETE FROM {table} WHERE profile_id=?", (pid,))
        con.executemany("INSERT INTO prohibited_words(profile_id,word) VALUES (?,?)",
                        [(pid, x.strip()) for x in prohibited if x.strip()])
        con.executemany("INSERT INTO preferred_terms(profile_id,old_term,new_term) VALUES (?,?,?)",
                        [(pid, a.strip(), b.strip()) for a,b in preferred.items() if a.strip() and b.strip()])
        con.executemany("INSERT INTO approved_facts(profile_id,fact_text) VALUES (?,?)",
                        [(pid, x.strip()) for x in facts if x.strip()])
    return pid

def save_report(profile_id: int, content_type: str, original: str, corrected: str,
                score: int, findings: list[dict], provider: str = "Local rules"):
    high = sum(1 for x in findings if x.get("severity") == "High")
    medium = sum(1 for x in findings if x.get("severity") == "Medium")
    with connect() as con:
        cur = con.execute("""INSERT INTO reports
            (profile_id,content_type,original_content,corrected_content,total_issues,
             high_issues,medium_issues,compliance_score,findings_json,ai_provider)
             VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (profile_id, content_type, original, corrected, len(findings), high, medium,
             max(0,min(100,int(score))), json.dumps(findings, ensure_ascii=False), provider))
        report_id = cur.lastrowid
        for item in findings:
            category = item.get("db_category", "Fact Verification")
            if category not in {"Preferred Terminology","Prohibited Terminology","Missing Disclaimer","Fact Verification"}:
                category = "Fact Verification"
            severity = "High" if item.get("severity") in {"High","Critical"} else "Medium"
            con.execute("""INSERT INTO issues(report_id,category,detected_text,rule_broken,
                suggested_correction,severity) VALUES (?,?,?,?,?,?)""",
                (report_id, category, item.get("phrase") or item.get("detected") or "",
                 item.get("reason") or item.get("rule") or "",
                 item.get("suggested_revision") or item.get("correction") or "", severity))
        con.execute("INSERT INTO review_history(report_id,action,reviewer_name,comment) VALUES (?,?,?,?)",
                    (report_id, "Checked", "System", f"Automated review found {len(findings)} finding(s)."))
    return report_id

def save_visual_review(report_id: int, filename: str, checks: dict, automated: dict):
    with connect() as con:
        con.execute("""INSERT OR REPLACE INTO visual_reviews
            (report_id,creative_filename,logo_ok,colour_ok,font_ok,layout_ok,automated_json)
            VALUES (?,?,?,?,?,?,?)""",
            (report_id, filename, int(checks.get("logo",False)), int(checks.get("colour",False)),
             int(checks.get("font",False)), int(checks.get("layout",False)),
             json.dumps(automated, ensure_ascii=False)))

def set_decision(report_id: int, decision: str, reviewer: str, comment: str, final_content: str):
    if decision not in {"Approved","Rejected"}:
        raise ValueError("Invalid decision.")
    with connect() as con:
        con.execute("UPDATE reports SET final_decision=?,final_content=? WHERE report_id=?",
                    (decision, final_content, report_id))
        con.execute("INSERT INTO review_history(report_id,action,reviewer_name,comment) VALUES (?,?,?,?)",
                    (report_id, decision, reviewer.strip() or "Reviewer", comment.strip()))

def list_reports(limit: int = 100):
    with connect() as con:
        return [dict(r) for r in con.execute("""SELECT r.*,b.organisation_name
            FROM reports r JOIN brand_profiles b USING(profile_id)
            ORDER BY r.report_id DESC LIMIT ?""", (limit,))]

def get_report(report_id: int):
    with connect() as con:
        r = con.execute("SELECT * FROM reports WHERE report_id=?", (report_id,)).fetchone()
        if not r: return None
        data = dict(r)
        data["findings"] = json.loads(data.pop("findings_json") or "[]")
        data["issues"] = [dict(x) for x in con.execute("SELECT * FROM issues WHERE report_id=?", (report_id,))]
        data["history"] = [dict(x) for x in con.execute(
            "SELECT * FROM review_history WHERE report_id=? ORDER BY history_id", (report_id,))]
        v = con.execute("SELECT * FROM visual_reviews WHERE report_id=?", (report_id,)).fetchone()
        data["visual_review"] = dict(v) if v else None
        return data

def analytics():
    with connect() as con:
        totals = con.execute("""SELECT COUNT(*) reports, COALESCE(AVG(compliance_score),0) avg_score,
            SUM(CASE WHEN final_decision='Approved' THEN 1 ELSE 0 END) approved,
            SUM(CASE WHEN final_decision='Rejected' THEN 1 ELSE 0 END) rejected
            FROM reports""").fetchone()
        cats = [dict(r) for r in con.execute(
            "SELECT category, COUNT(*) total FROM issues GROUP BY category ORDER BY total DESC")]
        return dict(totals), cats

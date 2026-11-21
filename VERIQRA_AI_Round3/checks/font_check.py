from __future__ import annotations
from pathlib import Path

def run_font_check(file_path: str, rules: dict) -> dict:
    approved=[x.lower() for x in rules.get("fonts",[]) if x.strip()]
    ext=Path(file_path).suffix.lower()
    issues=[]; found=[]
    if ext==".pdf":
        try:
            import fitz
            doc=fitz.open(file_path)
            for page_num,page in enumerate(doc,1):
                for font in page.get_fonts(full=True):
                    name=(font[3] or "Unknown").replace("+","")
                    found.append({"page":page_num,"font":name})
                    if approved and not any(a in name.lower() for a in approved):
                        issues.append({"rule":"approved_font","status":"fail","location":f"Page {page_num}",
                            "message":f"Unapproved embedded font '{name}' found in PDF."})
            return {"passed":not issues,"automated":True,"fonts":found,"issues":issues,
                    "note":"PDF embedded font metadata checked; rasterised text and outlined glyphs cannot be reliably identified."}
        except Exception as e:
            return {"passed":False,"automated":False,"issues":[{"rule":"approved_font","message":f"PDF font inspection unavailable: {e}"}]}
    return {"passed":False,"automated":False,"fonts":[],
            "issues":[{"rule":"approved_font","message":"For PNG/JPG, OCR can read text but cannot reliably identify the exact font family. Use the human font checklist."}],
            "note":"Image font identity requires human review or a separately validated font-recognition model."}

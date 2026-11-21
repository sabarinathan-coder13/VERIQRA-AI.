from __future__ import annotations
import json
from pathlib import Path
from .logo_check import run_logo_check
from .color_check import run_color_check
from .font_check import run_font_check

def generate_compliance_report(file_path: str, rules_path: str = "brand_rules.json") -> dict:
    rules=json.loads(Path(rules_path).read_text(encoding="utf-8"))
    ext=Path(file_path).suffix.lower()
    if ext==".pdf":
        # Rasterise first page for colour/logo screening; all pages are inspected for fonts.
        try:
            import fitz
            from PIL import Image
            doc=fitz.open(file_path)
            pix=doc[0].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
            image_path=str(Path(file_path).with_suffix(".preview.png"))
            pix.save(image_path)
            visual_path=image_path
        except Exception:
            visual_path=file_path
    else:
        visual_path=file_path
    color=run_color_check(visual_path,rules)
    logo=run_logo_check(visual_path,rules)
    font=run_font_check(file_path,rules)
    return {"logo_check":logo,"color_check":color,"font_check":font,
            "issues":logo.get("issues",[])+color.get("issues",[])+font.get("issues",[]),
            "human_review_required":not (logo.get("automated") and color.get("passed") and font.get("automated"))}

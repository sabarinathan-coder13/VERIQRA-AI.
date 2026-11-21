from __future__ import annotations
from pathlib import Path

def run_logo_check(image_path: str, rules: dict) -> dict:
    logo=rules.get("logo",{})
    ref=Path(logo.get("reference_path",""))
    if not ref.is_file():
        return {"passed":False,"automated":False,"issues":[{"rule":"logo_presence",
            "message":"Approved reference logo is not installed. Add the approved logo file to assets/brand_logos and update brand_rules.json; complete the logo checklist manually meanwhile."}]}
    try:
        import cv2
        image=cv2.imread(image_path)
        template=cv2.imread(str(ref))
        if image is None or template is None:
            raise ValueError("Image or logo could not be opened.")
        ih,iw=image.shape[:2]; th,tw=template.shape[:2]
        if th>ih or tw>iw:
            return {"passed":False,"automated":True,"issues":[{"rule":"logo_presence","message":"Reference logo is larger than the creative; resize or inspect manually."}]}
        result=cv2.matchTemplate(image,template,cv2.TM_CCOEFF_NORMED)
        _,score,_,loc=cv2.minMaxLoc(result)
        x,y=loc; bbox=[x,y,x+tw,y+th]; issues=[]
        if score < float(logo.get("match_threshold",0.60)):
            issues.append({"rule":"logo_presence","status":"fail","message":"Approved logo template was not confidently detected."})
        if tw < int(logo.get("min_width_px",80)):
            issues.append({"rule":"logo_min_width","status":"fail","location":bbox,"message":"Detected logo width is below the configured minimum."})
        cs=int(logo.get("clear_space_px",40))
        if x<cs or y<cs or iw-(x+tw)<cs or ih-(y+th)<cs:
            issues.append({"rule":"logo_clear_space","status":"fail","location":bbox,"message":"Logo may not have the required clear space."})
        return {"passed":not issues,"automated":True,"match_score":round(float(score),3),"bbox":bbox,"issues":issues}
    except ImportError:
        return {"passed":False,"automated":False,"issues":[{"rule":"logo_check","message":"OpenCV is unavailable; use the human logo checklist."}]}
    except Exception as e:
        return {"passed":False,"automated":False,"issues":[{"rule":"logo_check","message":str(e)}]}

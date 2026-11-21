from __future__ import annotations
from collections import Counter
from pathlib import Path
from PIL import Image
import re

def parse_hex_colours(value: str) -> list[str]:
    found = re.findall(r"#[0-9a-fA-F]{6}", value or "")
    return [x.upper() for x in found]

def _hex_rgb(value: str):
    return tuple(int(value[i:i+2],16) for i in (1,3,5))

def _delta_e(rgb1, rgb2):
    try:
        import numpy as np
        from skimage.color import rgb2lab, deltaE_ciede2000
        a=np.array([[rgb1]],dtype=float)/255
        b=np.array([[rgb2]],dtype=float)/255
        return float(deltaE_ciede2000(rgb2lab(a),rgb2lab(b))[0,0])
    except Exception:
        # RGB Euclidean fallback; explicitly reported as approximate.
        return sum((a-b)**2 for a,b in zip(rgb1,rgb2))**0.5

def run_color_check(image_path: str, rules: dict) -> dict:
    approved = parse_hex_colours(", ".join(rules.get("colors",[])))
    if not approved:
        return {"passed":False,"issues":[{"rule":"brand_color","message":"No valid approved HEX colours configured."}]}
    try:
        image=Image.open(image_path).convert("RGB")
        image.thumbnail((600,600))
        quant=image.quantize(colors=8)
        palette=quant.getpalette() or []
        counts=Counter(quant.getdata())
        issues=[]; detected=[]
        for idx,count in counts.most_common(8):
            rgb=tuple(palette[idx*3:idx*3+3])
            if len(rgb)!=3: continue
            distances=[_delta_e(rgb,_hex_rgb(h)) for h in approved]
            best=min(distances)
            hexval="#%02X%02X%02X"%rgb
            detected.append({"hex":hexval,"pixels":count,"delta_e":round(best,2)})
            if best > float(rules.get("delta_e_max",5)):
                issues.append({"rule":"brand_color","status":"fail","detected_color":hexval,
                    "delta_e":round(best,2),"message":f"Potential off-brand dominant colour {hexval}; Delta E={best:.2f}."})
        return {"passed":not issues,"issues":issues,"detected_colors":detected,
                "method":"CIEDE2000" if "skimage" in __import__("sys").modules else "RGB approximation"}
    except Exception as e:
        return {"passed":False,"issues":[{"rule":"brand_color","message":f"Could not inspect image: {e}"}]}

import os
import shutil
import base64
import json
import csv
import re
from pathlib import Path
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring

from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image
import imagehash


load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

BASE_FOLDER = r"C:\Users\user\foolder\杏子"
INPUT_FOLDER = r"C:\Users\user\OneDrive\hhh"

MASTER_PROJECT = os.path.join(BASE_FOLDER, "master_project.csv")
MASTER_COMMON = os.path.join(BASE_FOLDER, "master_common.csv")
SYNONYM_MASTER = os.path.join(BASE_FOLDER, "synonym_master.csv")
KEYWORD_RULES = os.path.join(BASE_FOLDER, "keyword_rules.csv")

PHOTO_ROOT = os.path.join(BASE_FOLDER, "selected_photos", "PHOTO")
PHOTO_XML_PATH = os.path.join(PHOTO_ROOT, "PHOTO.XML")

PIC_FOLDER = os.path.join(PHOTO_ROOT, "PIC")
CHECK_FOLDER = os.path.join(PHOTO_ROOT, "CHECK")
EXCLUDE_FOLDER = os.path.join(PHOTO_ROOT, "EXCLUDE")

CHECK_CSV_PATH = os.path.join(PHOTO_ROOT, "CHECK一覧.csv")
RESULT_CSV_PATH = os.path.join(PHOTO_ROOT, "処理結果一覧.csv")
ADD_CANDIDATE_CSV_PATH = os.path.join(PHOTO_ROOT, "master追加候補.csv")

SOURCE_DTD = os.path.join(BASE_FOLDER, "PHOTO05.DTD")

os.makedirs(PHOTO_ROOT, exist_ok=True)
os.makedirs(PIC_FOLDER, exist_ok=True)
os.makedirs(CHECK_FOLDER, exist_ok=True)
os.makedirs(EXCLUDE_FOLDER, exist_ok=True)

if os.path.exists(SOURCE_DTD):
    shutil.copy2(SOURCE_DTD, os.path.join(PHOTO_ROOT, "PHOTO05.DTD"))
    print("PHOTO05.DTD コピーOK")
else:
    print("PHOTO05.DTD がありません")
    print(SOURCE_DTD)


def safe_text(v):
    if v is None:
        return ""
    return str(v).strip()


def normalize_text(text):
    text = safe_text(text)

    replace_map = {
        " ": "",
        "　": "",
        "\n": "",
        "\r": "",
        "施工": "",
        "状況": "",
        "写真": "",
        "工事": "",
        "測定": "",
        "敷均しし": "敷均し",
        "敷敷均しし": "敷均し",
        "敷き均し": "敷均し",
        "敷均": "敷均し",
        "据付け": "据付",
        "接合け": "据付",
        "布設": "据付",
        "設置": "据付",
        "床掘り": "床掘",
        "床堀": "床掘",
        "底付": "底付け",
        "堀削": "掘削",
        "平均平度": "均平度",
        "平坦度": "均平度",
        "基盤整地": "整地仕上げ",
        "甘船整地丁": "基盤整地",
        "甘縄整地丁": "基盤整地",
    }

    for old, new in replace_map.items():
        text = text.replace(old, new)

    return text


def load_csv(path):
    rows = []

    if not os.path.exists(path):
        return rows

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    return rows


project_master = load_csv(MASTER_PROJECT)
common_master = load_csv(MASTER_COMMON)
synonym_master = load_csv(SYNONYM_MASTER)
keyword_rules = load_csv(KEYWORD_RULES)

print("master_project.csv 読込:", len(project_master))
print("master_common.csv 読込:", len(common_master))
print("synonym_master.csv 読込:", len(synonym_master))
print("keyword_rules.csv 読込:", len(keyword_rules))


VALID_PHOTO_TYPES = [
    "着手前及び完成写真",
    "施工状況写真",
    "安全管理写真",
    "使用材料写真",
    "品質管理写真",
    "出来形管理写真",
    "災害写真",
    "事故写真",
    "その他",
]


def apply_synonym(text):
    text = safe_text(text)

    for row in synonym_master:
        src = safe_text(row.get("現場語"))
        dst = safe_text(row.get("正式語"))

        if src and dst:
            text = text.replace(src, dst)

    return text


def normalize_photo_type(photo_type, blackboard_text="", scene_description=""):
    raw = safe_text(photo_type)
    text = normalize_text(raw + blackboard_text + scene_description)

    if "熱中症" in text or "安全" in text:
        return "安全管理写真"

    if "均平度" in text or "出来形" in text or "Xmax" in blackboard_text or "Xmin" in blackboard_text:
        return "出来形管理写真"

    if "品質" in text:
        return "品質管理写真"

    if "材料" in text:
        return "使用材料写真"

    if "完成" in text or "着手前" in text:
        return "着手前及び完成写真"

    if (
        "掘削" in text
        or "床掘" in text
        or "敷均" in text
        or "転圧" in text
        or "据付" in text
        or "整地" in text
        or "作業" in text
    ):
        return "施工状況写真"

    if raw in VALID_PHOTO_TYPES:
        return raw

    return "その他"


def normalize_work_name(work, blackboard_text=""):
    source = apply_synonym(safe_text(work) + "\n" + safe_text(blackboard_text))
    text = normalize_text(source)

    if "熱中症" in text or "安全" in text:
        return "安全管理"

    if "土工" in text or "土方" in text:
        return "土工"

    if "小用水路" in text or "用水路" in text or "水路" in text or "BF" in source:
        return "水路工"

    if "排水管" in text or "排水路" in text:
        return "水路工"

    if "均平度" in text or "整地" in text or "ほ場整備" in text:
        return "整地工"

    if "路盤" in text:
        return "路盤工"

    return safe_text(work)


def normalize_type_name(type_name, detail_name="", blackboard_text=""):
    source = apply_synonym(
        safe_text(type_name)
        + "\n"
        + safe_text(detail_name)
        + "\n"
        + safe_text(blackboard_text)
    )
    text = normalize_text(source)

    if "熱中症" in text:
        return "安全管理"

    if "均平度" in text or "整地仕上げ" in text or "基盤整地" in text:
        return "整地仕上げ"

    if "据付" in text:
        return "据付工"

    if "敷均し" in text or "転圧" in text or "均し" in text:
        return "均し工"

    if "掘削" in text or "床掘" in text or "根切" in text:
        return "掘削"

    return safe_text(type_name)


def normalize_detail_name(detail_name, blackboard_text=""):
    source = apply_synonym(safe_text(detail_name) + "\n" + safe_text(blackboard_text))
    text = normalize_text(source)

    if "熱中症" in text:
        return "熱中症対策"

    if "均平度" in text:
        return "均平度"

    if "据付" in text:
        return "据付状況"

    if "敷均し" in text or "転圧" in text:
        return "敷均・転圧状況"

    if "基盤整地" in text or "整地仕上げ" in text or "整地" in text:
        return "基盤整地"

    if "掘削" in text or "床掘" in text or "根切" in text:
        return "床掘・底付け状況"

    return safe_text(detail_name)


def apply_keyword_rules(photo_type, work, type_name, detail_name, title, blackboard_text, scene_description):
    if not keyword_rules:
        return photo_type, work, type_name, detail_name, title

    source = normalize_text(apply_synonym(blackboard_text + "\n" + scene_description))

    best = None
    best_score = 0

    for row in keyword_rules:
        keywords = safe_text(row.get("keyword") or row.get("キーワード"))

        if not keywords:
            continue

        score = 0

        for kw in re.split(r"[,\n、/／]+", keywords):
            kw = normalize_text(kw)

            if kw and kw in source:
                score += 1

        if score > best_score:
            best_score = score
            best = row

    if best and best_score > 0:
        photo_type = safe_text(best.get("写真区分")) or photo_type
        work = safe_text(best.get("工種")) or work
        type_name = safe_text(best.get("種別")) or type_name
        detail_name = safe_text(best.get("細別")) or detail_name
        title = safe_text(best.get("写真タイトル")) or title

    return photo_type, work, type_name, detail_name, title


def final_rule_fix(photo_type, work, type_name, detail_name, title, blackboard_text, scene_description):
    source_text = normalize_text(apply_synonym(blackboard_text))

    if "熱中症" in source_text:
        return "安全管理写真", "安全管理", "安全管理", "熱中症対策", "熱中症対策"

    if "均平度" in source_text or "Xmax" in blackboard_text or "Xmin" in blackboard_text:
        return "出来形管理写真", "整地工", "整地仕上げ", "均平度", "均平度"

    if "据付" in source_text or "布設" in source_text or "設置" in source_text:
        return "施工状況写真", "水路工", "据付工", "据付状況", "小用水路 据付状況"

    if "敷均し" in source_text or "転圧" in source_text:
        work = normalize_work_name(work, blackboard_text)

        if work == "土工":
            title = "土工 敷均・転圧状況"
        else:
            work = "水路工"
            title = "小用水路 敷均・転圧状況"

        return "施工状況写真", work, "均し工", "敷均・転圧状況", title

    if "基盤整地" in source_text or "整地仕上げ" in source_text:
        return "施工状況写真", "整地工", "整地仕上げ", "基盤整地", "基盤整地施工状況写真"

    if "掘削" in source_text or "床掘" in source_text:
        if not ("敷均し" in source_text or "転圧" in source_text):
            if not ("据付" in source_text or "布設" in source_text or "設置" in source_text):
                work = normalize_work_name(work, blackboard_text)

                if work == "土工":
                    title = "土工 掘削床掘状況"
                else:
                    work = "水路工"
                    title = "小用水路 掘削床掘状況"

                return "施工状況写真", work, "掘削", "床掘・底付け状況", title

    photo_type = normalize_photo_type(photo_type, blackboard_text, scene_description)
    work = normalize_work_name(work, blackboard_text)
    type_name = normalize_type_name(type_name, detail_name, blackboard_text)
    detail_name = normalize_detail_name(detail_name, blackboard_text)

    return photo_type, work, type_name, detail_name, title


def fix_location(location, blackboard_text):
    text = safe_text(location) + "\n" + safe_text(blackboard_text)

    patterns = [
        r"測点\s*田番\s*([0-9０-９]+)",
        r"位置\s*田番\s*([0-9０-９]+)",
        r"田番\s*([0-9０-９]+)",
        r"\b([0-9]{1,2})\s*\(A\s*=",
    ]

    for p in patterns:
        m = re.search(p, text)

        if m:
            num = m.group(1)
            num = num.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            return f"田番{num}"

    if location and location not in ["不明", ""]:
        return location

    return ""


def is_indoor_office(result):
    scene = (
        safe_text(result.get("reason"))
        + safe_text(result.get("location"))
        + safe_text(result.get("photo_type"))
        + safe_text(result.get("work"))
        + safe_text(result.get("type_name"))
        + safe_text(result.get("detail_name"))
        + safe_text(result.get("title"))
        + safe_text(result.get("scene_description"))
    )

    keywords = [
        "室内",
        "会議室",
        "事務所内",
        "オフィス内",
        "机",
        "デスク",
        "椅子",
        "パソコン",
        "PC",
        "書類",
        "棚",
        "ホワイトボード",
        "蛍光灯",
        "天井",
        "事務用品",
        "打合せ",
    ]

    return any(k in scene for k in keywords)


def analyze_image(image_path):
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """
工事写真を解析してください。

黒板文字を最優先してください。
ただし写真全体も見てください。

JSONのみ返してください。

{
  "usable": true,
  "reason": "",
  "scene_description": "",
  "blackboard_text": "",
  "location": "",
  "photo_type": "",
  "work": "",
  "type_name": "",
  "detail_name": "",
  "title": "",
  "unrelated": false,
  "indoor_office": false,
  "confidence": 90
}

photo_type は必ず以下から選択:
- 着手前及び完成写真
- 施工状況写真
- 安全管理写真
- 使用材料写真
- 品質管理写真
- 出来形管理写真
- 災害写真
- 事故写真
- その他

黒板が読めない場合は usable=false。
黒板が読めなくても scene_description は詳しく書いてください。

重要:
黒板に「均平度」があれば photo_type は 出来形管理写真。
黒板に「熱中症対策」があれば 安全管理写真。
黒板に「敷均し」「転圧」があれば 種別は 均し工、細別は 敷均・転圧状況。
黒板に「据付」「据付け」「布設」「設置」があれば 種別は 据付工、細別は 据付状況。
黒板に「掘削」「床掘」があり、敷均し・転圧・据付が無ければ 種別は 掘削、細別は 床掘・底付け状況。
小用水路、用水路、水路、BF350 があれば 工種は 水路工。
土工、土方 が明記されていれば 工種は 土工。
"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}"
                            },
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"},
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print("AIエラー:", e)

        return {
            "usable": False,
            "reason": "AI失敗",
            "scene_description": "",
            "blackboard_text": "",
            "location": "",
            "photo_type": "その他",
            "work": "",
            "type_name": "",
            "detail_name": "",
            "title": "",
            "unrelated": True,
            "indoor_office": False,
            "confidence": 0,
        }


hash_db = {}


def is_duplicate(image_path):
    try:
        img = Image.open(image_path)
        h = str(imagehash.phash(img))

        if h in hash_db:
            return True

        hash_db[h] = image_path
        return False

    except Exception:
        return False


def score_master_row(row, photo_type, work, type_name, detail_name, title, blackboard_text):
    score = 0

    r_photo_type = normalize_text(row.get("写真区分"))
    r_work = normalize_text(row.get("工種"))
    r_type = normalize_text(row.get("種別"))
    r_detail = normalize_text(row.get("細別"))
    r_title = normalize_text(row.get("写真タイトル"))

    n_photo_type = normalize_text(photo_type)
    n_work = normalize_text(work)
    n_type = normalize_text(type_name)
    n_detail = normalize_text(detail_name)
    n_title = normalize_text(title)

    source = normalize_text(blackboard_text)

    if r_photo_type and r_photo_type == n_photo_type:
        score += 30

    if r_work and r_work == n_work:
        score += 120

    if r_type and r_type == n_type:
        score += 120

    if r_detail and r_detail == n_detail:
        score += 180

    if r_title and r_title == n_title:
        score += 80

    if ("敷均し" in source or "転圧" in source) and ("敷均し" in r_detail or "転圧" in r_detail):
        score += 300

    if ("敷均し" in source or "転圧" in source) and ("掘削" in r_type or "床掘" in r_detail):
        score -= 250

    if "据付" in source and ("据付" in r_type or "据付" in r_detail):
        score += 300

    if "据付" in source and ("掘削" in r_type or "床掘" in r_detail):
        score -= 250

    if "均平度" in source and "均平度" in r_detail:
        score += 300

    if "均平度" in source and "基盤整地" in r_detail:
        score -= 200

    return score


def match_master(photo_type, work, type_name, detail_name, title, blackboard_text):
    best = None
    best_score = 0
    best_source = ""

    for row in project_master:
        score = score_master_row(
            row,
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            blackboard_text,
        )

        if score > best_score:
            best_score = score
            best = row
            best_source = "project"

    if best_score < 100:
        for row in common_master:
            score = score_master_row(
                row,
                photo_type,
                work,
                type_name,
                detail_name,
                title,
                blackboard_text,
            )

            score = int(score * 0.5)

            if score > best_score:
                best_score = score
                best = row
                best_source = "common"

    return best, best_score, best_source


def master_conflict(matched, blackboard_text):
    if not matched:
        return False

    source = normalize_text(blackboard_text)
    m_type = normalize_text(matched.get("種別"))
    m_detail = normalize_text(matched.get("細別"))

    if ("敷均し" in source or "転圧" in source) and ("掘削" in m_type or "床掘" in m_detail):
        return True

    if "据付" in source and ("掘削" in m_type or "床掘" in m_detail):
        return True

    if "均平度" in source and "基盤整地" in m_detail:
        return True

    return False


def add_check_row(rows, filename, reason, result, photo_type, work, type_name, detail_name, title, score, source):
    rows.append({
        "ファイル名": filename,
        "確認理由": reason,
        "AI理由": safe_text(result.get("reason")),
        "写真内容": safe_text(result.get("scene_description")),
        "黒板文字": safe_text(result.get("blackboard_text")),
        "写真区分": photo_type,
        "工種": work,
        "種別": type_name,
        "細別": detail_name,
        "写真タイトル": title,
        "master一致": score,
        "master種別": source,
        "信頼度": result.get("confidence", ""),
    })


def add_result_row(rows, filename, status, reason, photo_type, work, type_name, detail_name, title, score, source, saved_name=""):
    rows.append({
        "ファイル名": filename,
        "判定": status,
        "理由": reason,
        "保存名": saved_name,
        "写真区分": photo_type,
        "工種": work,
        "種別": type_name,
        "細別": detail_name,
        "写真タイトル": title,
        "master一致": score,
        "master種別": source,
    })


def add_candidate_row(rows, filename, reason, result, photo_type, work, type_name, detail_name, title, score, source):
    rows.append({
        "ファイル名": filename,
        "追加理由": reason,
        "写真区分": photo_type,
        "工種": work,
        "種別": type_name,
        "細別": detail_name,
        "写真タイトル": title,
        "master一致": score,
        "master種別": source,
        "信頼度": result.get("confidence", ""),
        "黒板文字": safe_text(result.get("blackboard_text")),
        "写真内容": safe_text(result.get("scene_description")),
    })


root = Element("photodata")
root.set("DTD_version", "05")

base_info = SubElement(root, "基礎情報")
SubElement(base_info, "写真フォルダ名").text = "PHOTO/PIC"
SubElement(base_info, "参考図フォルダ名").text = "PHOTO/DRA"
SubElement(base_info, "適用要領基準").text = "土木202303-01"


image_files_dict = {}

for ext in ["*.jpg", "*.jpeg", "*.png"]:
    for p in Path(INPUT_FOLDER).rglob(ext):
        image_files_dict[str(p.resolve()).lower()] = p

    for p in Path(INPUT_FOLDER).rglob(ext.upper()):
        image_files_dict[str(p.resolve()).lower()] = p

image_files = sorted(image_files_dict.values(), key=lambda x: str(x).lower())

print("================================")
print("工事写真解析開始")
print("対象枚数:", len(image_files))
print("================================")


check_rows = []
result_rows = []
candidate_rows = []
serial_no = 1


for img_path in image_files:
    print()
    print("================================")
    print(img_path.name)

    if is_duplicate(str(img_path)):
        print("重複検出 → EXCLUDE")
        shutil.copy2(img_path, os.path.join(EXCLUDE_FOLDER, img_path.name))
        add_result_row(result_rows, img_path.name, "EXCLUDE", "重複検出", "", "", "", "", "", 0, "")
        continue

    result = analyze_image(str(img_path))

    usable = result.get("usable", False)
    unrelated = result.get("unrelated", False)

    blackboard_text = apply_synonym(safe_text(result.get("blackboard_text")))
    scene_description = safe_text(result.get("scene_description"))
    location = safe_text(result.get("location"))

    photo_type = safe_text(result.get("photo_type"))
    work = safe_text(result.get("work"))
    type_name = safe_text(result.get("type_name"))
    detail_name = safe_text(result.get("detail_name"))
    title = safe_text(result.get("title"))
    confidence = result.get("confidence", 0)

    photo_type, work, type_name, detail_name, title = apply_keyword_rules(
        photo_type,
        work,
        type_name,
        detail_name,
        title,
        blackboard_text,
        scene_description,
    )

    photo_type, work, type_name, detail_name, title = final_rule_fix(
        photo_type,
        work,
        type_name,
        detail_name,
        title,
        blackboard_text,
        scene_description,
    )

    location = fix_location(location, blackboard_text)

    print("採用:", usable)
    print("黒板:")
    print(blackboard_text)
    print("写真区分:", photo_type)
    print("工種:", work)
    print("種別:", type_name)
    print("細別:", detail_name)
    print("写真タイトル:", title)
    print("撮影箇所:", location)
    print("信頼度:", confidence)

    if blackboard_text.strip() == "":
        print("黒板なし → CHECK")
        shutil.copy2(img_path, os.path.join(CHECK_FOLDER, img_path.name))
        add_check_row(check_rows, img_path.name, "黒板なし", result, photo_type, work, type_name, detail_name, title, 0, "")
        add_result_row(result_rows, img_path.name, "CHECK", "黒板なし", photo_type, work, type_name, detail_name, title, 0, "")
        continue

    if is_indoor_office(result):
        print("室内・事務所写真 → CHECK")
        shutil.copy2(img_path, os.path.join(CHECK_FOLDER, img_path.name))
        add_check_row(check_rows, img_path.name, "室内・事務所写真", result, photo_type, work, type_name, detail_name, title, 0, "")
        add_result_row(result_rows, img_path.name, "CHECK", "室内・事務所写真", photo_type, work, type_name, detail_name, title, 0, "")
        continue

    matched, score, source = match_master(
        photo_type,
        work,
        type_name,
        detail_name,
        title,
        blackboard_text,
    )

    print("master一致:", score)
    print("master種別:", source)

    if matched and not master_conflict(matched, blackboard_text):
        photo_type = matched.get("写真区分") or photo_type
        work = matched.get("工種") or work
        type_name = matched.get("種別") or type_name
        detail_name = matched.get("細別") or detail_name
        title = matched.get("写真タイトル") or title

        photo_type, work, type_name, detail_name, title = final_rule_fix(
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            blackboard_text,
            scene_description,
        )

        print("master最終補正後:", photo_type, work, type_name, detail_name, title)

    elif matched and master_conflict(matched, blackboard_text):
        print("master衝突 → AI補正分類を優先")
        add_candidate_row(candidate_rows, img_path.name, "master衝突候補", result, photo_type, work, type_name, detail_name, title, score, source)

    else:
        add_candidate_row(candidate_rows, img_path.name, "master未登録候補", result, photo_type, work, type_name, detail_name, title, score, source)

    if unrelated:
        print("別現場または無関係 → EXCLUDE")
        shutil.copy2(img_path, os.path.join(EXCLUDE_FOLDER, img_path.name))
        add_result_row(result_rows, img_path.name, "EXCLUDE", "別現場または無関係", photo_type, work, type_name, detail_name, title, score, source)
        continue

    if not usable:
        print("usable false → CHECK")
        shutil.copy2(img_path, os.path.join(CHECK_FOLDER, img_path.name))
        add_check_row(check_rows, img_path.name, "usable false", result, photo_type, work, type_name, detail_name, title, score, source)
        add_result_row(result_rows, img_path.name, "CHECK", "usable false", photo_type, work, type_name, detail_name, title, score, source)
        continue

    if not work or not type_name or not detail_name:
        print("分類不足 → CHECK")
        shutil.copy2(img_path, os.path.join(CHECK_FOLDER, img_path.name))
        add_check_row(check_rows, img_path.name, "分類不足", result, photo_type, work, type_name, detail_name, title, score, source)
        add_result_row(result_rows, img_path.name, "CHECK", "分類不足", photo_type, work, type_name, detail_name, title, score, source)
        add_candidate_row(candidate_rows, img_path.name, "分類不足", result, photo_type, work, type_name, detail_name, title, score, source)
        continue

    new_name = f"P{serial_no:07}.JPG"
    shutil.copy2(img_path, os.path.join(PIC_FOLDER, new_name))

    print("採用保存:", new_name)

    photo_info = SubElement(root, "写真情報")

    file_info = SubElement(photo_info, "写真ファイル情報")
    SubElement(file_info, "シリアル番号").text = str(serial_no)
    SubElement(file_info, "写真ファイル名").text = new_name
    SubElement(file_info, "メディア番号").text = "1"

    category = SubElement(photo_info, "撮影工種区分")
    SubElement(category, "写真-大分類").text = "工事"
    SubElement(category, "写真区分").text = photo_type
    SubElement(category, "工種").text = work
    SubElement(category, "種別").text = type_name
    SubElement(category, "細別").text = detail_name
    SubElement(category, "写真タイトル").text = title

    shoot = SubElement(photo_info, "撮影情報")
    SubElement(shoot, "撮影年月日").text = datetime.now().strftime("%Y-%m-%d")
    SubElement(shoot, "撮影箇所").text = location

    SubElement(photo_info, "代表写真").text = "0"
    SubElement(photo_info, "提出頻度写真").text = "0"

    add_result_row(result_rows, img_path.name, "採用", "OK", photo_type, work, type_name, detail_name, title, score, source, new_name)

    serial_no += 1


if check_rows:
    with open(CHECK_CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(check_rows[0].keys()))
        writer.writeheader()
        writer.writerows(check_rows)
else:
    with open(CHECK_CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["CHECKなし"])

print("CHECK一覧.csv 出力:", CHECK_CSV_PATH)

if result_rows:
    with open(RESULT_CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(result_rows[0].keys()))
        writer.writeheader()
        writer.writerows(result_rows)

print("処理結果一覧.csv 出力:", RESULT_CSV_PATH)

if candidate_rows:
    with open(ADD_CANDIDATE_CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(candidate_rows[0].keys()))
        writer.writeheader()
        writer.writerows(candidate_rows)
else:
    with open(ADD_CANDIDATE_CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["追加候補なし"])

print("master追加候補.csv 出力:", ADD_CANDIDATE_CSV_PATH)

if serial_no == 1:
    print()
    print("================================")
    print("採用写真なし")
    print("PHOTO.XML 作成スキップ")
    print("================================")
else:
    xml_body = tostring(root, encoding="shift_jis", xml_declaration=False)

    with open(PHOTO_XML_PATH, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="Shift_JIS"?>\r\n')
        f.write(b'<!DOCTYPE photodata SYSTEM "PHOTO05.DTD">\r\n')
        f.write(xml_body)

    print()
    print("================================")
    print("PHOTO.XML 完成")
    print(PHOTO_XML_PATH)
    print("================================")
    
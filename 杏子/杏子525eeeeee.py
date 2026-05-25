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

PHOTO_XML_ROOT = os.path.join(BASE_FOLDER, "selected_photos", "PHOTO_XML")
PHOTO_XML_PATH = os.path.join(PHOTO_XML_ROOT, "PHOTO.XML")

PIC_FOLDER = os.path.join(PHOTO_XML_ROOT, "PIC")
EXCLUDE_FOLDER = os.path.join(PHOTO_XML_ROOT, "EXCLUDE")
CHECK_FOLDER = os.path.join(PHOTO_XML_ROOT, "CHECK")

SOURCE_DTD = os.path.join(BASE_FOLDER, "PHOTO05.DTD")

os.makedirs(PHOTO_XML_ROOT, exist_ok=True)
os.makedirs(PIC_FOLDER, exist_ok=True)
os.makedirs(EXCLUDE_FOLDER, exist_ok=True)
os.makedirs(CHECK_FOLDER, exist_ok=True)

if os.path.exists(SOURCE_DTD):
    shutil.copy2(SOURCE_DTD, os.path.join(PHOTO_XML_ROOT, "PHOTO05.DTD"))
    print("PHOTO05.DTD コピーOK")
else:
    print("PHOTO05.DTD がありません")
    print(SOURCE_DTD)


def load_master(csv_path):
    rows = []

    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        print(os.path.basename(csv_path), "読込:", len(rows))
    else:
        print(os.path.basename(csv_path), "なし")

    return rows


project_master = load_master(MASTER_PROJECT)
common_master = load_master(MASTER_COMMON)


def safe_text(v):
    if v is None:
        return ""
    return str(v)


def normalize_text(text):
    text = safe_text(text)

    replace_map = {
        " ": "",
        "　": "",
        "\n": "",
        "\r": "",
        "工事": "",
        "測定": "",
        "写真": "",
        "状況": "",
        "平均平度": "均平度",
        "平均地上げ": "均平度",
        "平坦度": "均平度",
        "基盤整地": "整地仕上げ",
        "整地整備": "整地",
        "整地場整備": "整地",
        "整地ほ場整備": "整地",
        "整地仕上": "整地仕上げ",
        "農地中間管理機構関連": "",
        "農地中間管理機関連": "",
        "床掘り": "床掘",
        "床堀": "床掘",
        "堀削": "掘削",
        "敷き均し": "敷均し",
        "敷均": "敷均し",
        "転圧状況": "転圧",
    }

    for old, new in replace_map.items():
        text = text.replace(old, new)

    return text


def normalize_work_name(work):
    w = normalize_text(work)

    if "安全" in w or "熱中症" in w:
        return "安全管理"

    if "小用水路" in w or "用水路" in w or "水路" in w:
        return "水路工"

    if "土工" in w:
        return "土工"

    if "路盤" in w:
        return "路盤工"

    if "整地" in w or "均平度" in w:
        return "整地工"

    if "準備" in w:
        return "準備工"

    return safe_text(work)


def normalize_type_name(type_name, detail_name="", blackboard_text=""):
    text = (
        normalize_text(type_name)
        + normalize_text(detail_name)
        + normalize_text(blackboard_text)
    )

    if "熱中症" in text:
        return "安全管理"

    if "均平度" in text or "整地仕上げ" in text or "基盤整地" in text:
        return "整地仕上げ"

    # 敷均し・転圧を掘削より優先
    if "敷均し" in text or "転圧" in text or "均し" in text:
        return "均し工"

    if "床掘" in text or "掘削" in text or "根切" in text:
        return "掘削"

    return safe_text(type_name)


def normalize_detail_name(detail_name, blackboard_text=""):
    text = normalize_text(detail_name) + normalize_text(blackboard_text)

    if "熱中症" in text:
        return "熱中症対策"

    if "均平度" in text:
        return "均平度"

    if "基盤整地" in text or "整地仕上げ" in text:
        return "基盤整地"

    # 敷均し・転圧を掘削より優先
    if "敷均し" in text and "転圧" in text:
        return "敷均・転圧状況"

    if "転圧" in text:
        return "転圧状況"

    if "床掘" in text or "掘削" in text or "根切" in text:
        return "床掘・底付け状況"

    return safe_text(detail_name)


def clean_master_detail(detail):
    d = safe_text(detail)

    if "、" in d:
        parts = [p.strip() for p in d.split("、") if p.strip()]
        if parts:
            return parts[-1]

    if "," in d:
        parts = [p.strip() for p in d.split(",") if p.strip()]
        if parts:
            return parts[-1]

    return d


def work_conflict(ai_work, master_work):
    ai = normalize_work_name(ai_work)
    ma = normalize_work_name(master_work)

    if not ai or not ma:
        return False

    if ai == ma:
        return False

    strong_works = [
        "土工",
        "水路工",
        "路盤工",
        "整地工",
        "安全管理",
        "準備工",
    ]

    if ai in strong_works and ma in strong_works:
        return True

    return False


def type_conflict(ai_type, ai_detail, master_type, master_detail, blackboard_text):
    ai_group = normalize_type_name(ai_type, ai_detail, blackboard_text)
    ma_group = normalize_type_name(master_type, master_detail, "")

    if not ai_group or not ma_group:
        return False

    if ai_group == ma_group:
        return False

    strong_types = [
        "掘削",
        "均し工",
        "整地仕上げ",
        "安全管理",
    ]

    if ai_group in strong_types and ma_group in strong_types:
        return True

    return False


def apply_blackboard_priority(photo_type, work, type_name, detail_name, title, blackboard_text):
    text = normalize_text(blackboard_text)

    if "熱中症" in text:
        photo_type = "安全管理写真"
        work = "安全管理"
        detail_name = "熱中症対策"
        if not title:
            title = "熱中症対策"

    elif "小用水路" in text or "用水路" in text or "水路" in text:
        work = "水路工"

        # 敷均し・転圧を掘削より優先
        if "敷均し" in text or "転圧" in text or "均し" in text:
            photo_type = "施工状況写真"
            type_name = "均し工"
            detail_name = "敷均・転圧状況"
            title = "小用水路 敷均・転圧状況"

        elif "床掘" in text or "掘削" in text or "根切" in text:
            photo_type = "施工状況写真"
            type_name = "掘削"
            detail_name = "床掘・底付け状況"
            title = "小用水路 掘削床掘状況"

    elif "土工" in text:
        work = "土工"

        # 敷均し・転圧を掘削より優先
        if "敷均し" in text or "転圧" in text or "均し" in text:
            photo_type = "施工状況写真"
            type_name = "均し工"
            detail_name = "敷均・転圧状況"
            title = "土工 敷均・転圧状況"

        elif "床掘" in text or "掘削" in text or "根切" in text:
            photo_type = "施工状況写真"
            type_name = "掘削"
            detail_name = "床掘・底付け状況"
            title = "土工 掘削床掘状況"

    elif "均平度" in text:
        work = "整地工"
        type_name = "整地仕上げ"
        detail_name = "均平度"
        if not photo_type:
            photo_type = "品質管理写真"
        if not title:
            title = "均平度"

    elif "基盤整地" in text or "整地仕上げ" in text:
        work = "整地工"
        photo_type = "施工状況写真"
        type_name = "整地仕上げ"
        detail_name = "基盤整地"
        if not title:
            title = "基盤整地施工状況写真"

    work = normalize_work_name(work)

    return photo_type, work, type_name, detail_name, title


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
            num = num.translate(
                str.maketrans("０１２３４５６７８９", "0123456789")
            )
            return f"田番{num}"

    if location and location not in ["不明", ""]:
        return location

    return ""


def is_indoor_office(result):
    scene = (
        safe_text(result.get("reason"))
        + safe_text(result.get("blackboard_text"))
        + safe_text(result.get("location"))
        + safe_text(result.get("photo_type"))
        + safe_text(result.get("work"))
        + safe_text(result.get("type_name"))
        + safe_text(result.get("detail_name"))
        + safe_text(result.get("title"))
        + safe_text(result.get("scene_description"))
    )

    indoor_keywords = [
        "室内",
        "事務所",
        "会議室",
        "机",
        "デスク",
        "椅子",
        "イス",
        "パソコン",
        "PC",
        "モニター",
        "書類",
        "棚",
        "ホワイトボード",
        "蛍光灯",
        "天井",
        "事務用品",
        "打合せ",
        "事務室",
    ]

    return any(k in scene for k in indoor_keywords)


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

photo_type は以下から選択:
- 着手前及び完成写真
- 施工状況写真
- 安全管理写真
- 使用材料写真
- 品質管理写真
- 出来形管理写真
- 災害写真
- 事故写真
- その他

除外または要確認:
- 室内
- 書類写真
- 打合せ
- 会議室
- 別工事
- スナップ
- 黒板読めない
- ブレ
- ピンぼけ

分類の注意:

黒板に「熱中症対策」がある場合は、
photo_type は 安全管理写真
work は 安全管理
detail_name は 熱中症対策 にしてください。

黒板に「整地仕上げ」「均平度」「基盤整地」がある場合は、
work は 整地工
type_name は 整地仕上げ
detail_name は 均平度 または 基盤整地 にしてください。

黒板に「小用水路」「用水路」「水路」がある場合は、
work は 水路工 にしてください。

小用水路や水路で「敷均し」「転圧」「均し」がある場合は、
type_name は 均し工
detail_name は 敷均・転圧状況 にしてください。

小用水路や水路で「掘削」「床掘」があり、
敷均し・転圧が無い場合は、
type_name は 掘削
detail_name は 床掘・底付け状況 にしてください。

黒板に「土工」がある場合は、
work は 土工 にしてください。
"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}"
                            }
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"}
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
            "title": "写真",
            "unrelated": True,
            "indoor_office": False,
            "confidence": 0
        }


def score_master_row(row, source_all, ai_photo_type, ai_work, ai_type, ai_detail, ai_title):
    score = 0

    m_photo_type_raw = safe_text(row.get("写真区分", ""))
    m_work_raw = safe_text(row.get("工種", ""))
    m_type_raw = safe_text(row.get("種別", ""))
    m_detail_raw = safe_text(row.get("細別", ""))
    m_title_raw = safe_text(row.get("写真タイトル", ""))

    m_photo_type = normalize_text(m_photo_type_raw)
    m_work = normalize_text(m_work_raw)
    m_type = normalize_text(m_type_raw)
    m_detail = normalize_text(m_detail_raw)
    m_title = normalize_text(m_title_raw)

    ai_photo_type_n = normalize_text(ai_photo_type)
    ai_type_n = normalize_text(ai_type)
    ai_detail_n = normalize_text(ai_detail)
    ai_title_n = normalize_text(ai_title)

    if m_photo_type and m_photo_type == ai_photo_type_n:
        score += 30
    elif m_photo_type and m_photo_type in source_all:
        score += 10

    if m_work_raw and normalize_work_name(m_work_raw) == normalize_work_name(ai_work):
        score += 120
    elif m_work and m_work in source_all:
        score += 20

    if m_type and m_type == ai_type_n:
        score += 80
    elif m_type and m_type in source_all:
        score += 15

    if m_detail and m_detail == ai_detail_n:
        score += 70
    elif m_detail and m_detail in source_all:
        score += 10

    if m_title and m_title == ai_title_n:
        score += 40
    elif m_title and m_title in source_all:
        score += 10

    return score


def match_master(photo_type, work, type_name, detail_name, title, blackboard_text):
    best = None
    best_score = 0
    best_source = ""

    source_all = (
        normalize_text(photo_type)
        + normalize_text(work)
        + normalize_text(type_name)
        + normalize_text(detail_name)
        + normalize_text(title)
        + normalize_text(blackboard_text)
    )

    for row in project_master:
        m_work = row.get("工種", "")
        m_type = row.get("種別", "")
        m_detail = row.get("細別", "")

        if work_conflict(work, m_work):
            continue

        if type_conflict(type_name, detail_name, m_type, m_detail, blackboard_text):
            continue

        score = score_master_row(
            row,
            source_all,
            photo_type,
            work,
            type_name,
            detail_name,
            title
        )

        if score > best_score:
            best_score = score
            best = row
            best_source = "project"

    if best_score < 80:
        for row in common_master:
            m_work = row.get("工種", "")
            m_type = row.get("種別", "")
            m_detail = row.get("細別", "")

            if work_conflict(work, m_work):
                continue

            if type_conflict(type_name, detail_name, m_type, m_detail, blackboard_text):
                continue

            score = score_master_row(
                row,
                source_all,
                photo_type,
                work,
                type_name,
                detail_name,
                title
            )

            score = int(score * 0.6)

            if score > best_score:
                best_score = score
                best = row
                best_source = "common"

    if best_source == "common" and best_score < 50:
        return None, 0, ""

    return best, best_score, best_source


def apply_master_safely(
    matched,
    photo_type,
    work,
    type_name,
    detail_name,
    title,
    blackboard_text
):
    if not matched:
        return photo_type, work, type_name, detail_name, title

    matched_photo_type = matched.get("写真区分", "") or photo_type
    matched_work = matched.get("工種", "") or work
    matched_type = matched.get("種別", "") or type_name
    matched_detail = matched.get("細別", "") or detail_name
    matched_title = matched.get("写真タイトル", "") or title

    matched_detail = clean_master_detail(matched_detail)

    if work_conflict(work, matched_work):
        print("master工種衝突 → AI分類を優先")
        return photo_type, work, type_name, detail_name, title

    if type_conflict(type_name, detail_name, matched_type, matched_detail, blackboard_text):
        print("master種別・細別衝突 → AI分類を優先")
        return photo_type, work, type_name, detail_name, title

    return (
        matched_photo_type,
        matched_work,
        matched_type,
        matched_detail,
        matched_title
    )


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


serial_no = 1

for img_path in image_files:
    print()
    print("================================")
    print(img_path.name)

    if is_duplicate(str(img_path)):
        print("重複検出 → EXCLUDE")
        shutil.copy2(img_path, os.path.join(EXCLUDE_FOLDER, img_path.name))
        continue

    result = analyze_image(str(img_path))

    usable = result.get("usable", False)
    unrelated = result.get("unrelated", False)
    indoor_office = result.get("indoor_office", False)

    reason = safe_text(result.get("reason"))
    scene_description = safe_text(result.get("scene_description"))
    blackboard_text = safe_text(result.get("blackboard_text"))
    location = safe_text(result.get("location"))
    photo_type = safe_text(result.get("photo_type"))
    work = safe_text(result.get("work"))
    type_name = safe_text(result.get("type_name"))
    detail_name = safe_text(result.get("detail_name"))
    title = safe_text(result.get("title"))
    confidence = result.get("confidence", 0)

    work = normalize_work_name(work)

    photo_type, work, type_name, detail_name, title = apply_blackboard_priority(
        photo_type,
        work,
        type_name,
        detail_name,
        title,
        blackboard_text
    )

    type_name = normalize_type_name(type_name, detail_name, blackboard_text)
    detail_name = normalize_detail_name(detail_name, blackboard_text)

    location = fix_location(location, blackboard_text)

    print("採用:", usable)
    print("理由:", reason)
    print("写真内容:", scene_description)
    print("黒板:")
    print(blackboard_text)
    print("撮影箇所:", location)
    print("写真区分:", photo_type)
    print("工種:", work)
    print("種別:", type_name)
    print("細別:", detail_name)
    print("写真タイトル:", title)
    print("室内事務所:", indoor_office)
    print("信頼度:", confidence)

    if indoor_office or is_indoor_office(result):
        print("室内・事務所写真 → CHECK")
        shutil.copy2(img_path, os.path.join(CHECK_FOLDER, img_path.name))
        continue

    if blackboard_text.strip() == "":
        print("黒板なし → master照合スキップ")

        if not usable:
            print("採用価値低 → CHECK")
            shutil.copy2(img_path, os.path.join(CHECK_FOLDER, img_path.name))
            continue

        print("黒板なしだが採用判定 → CHECK")
        shutil.copy2(img_path, os.path.join(CHECK_FOLDER, img_path.name))
        continue

    matched, score, source = match_master(
        photo_type,
        work,
        type_name,
        detail_name,
        title,
        blackboard_text
    )

    print("master一致:", score)
    print("master種別:", source)

    if matched:
        (
            photo_type,
            work,
            type_name,
            detail_name,
            title
        ) = apply_master_safely(
            matched,
            photo_type,
            work,
            type_name,
            detail_name,
            title,
            blackboard_text
        )

        print("採用後 写真区分:", photo_type)
        print("採用後 工種:", work)
        print("採用後 種別:", type_name)
        print("採用後 細別:", detail_name)
        print("採用後 写真タイトル:", title)

    if unrelated:
        print("別現場または無関係 → EXCLUDE")
        shutil.copy2(img_path, os.path.join(EXCLUDE_FOLDER, img_path.name))
        continue

    if not usable:
        print("採用価値低 → CHECK")
        shutil.copy2(img_path, os.path.join(CHECK_FOLDER, img_path.name))
        continue

    if project_master:
        if source != "project" or score < 80:
            print("現場master一致低 → CHECK")
            shutil.copy2(img_path, os.path.join(CHECK_FOLDER, img_path.name))
            continue
    else:
        if score < 50:
            print("master一致低 → CHECK")
            shutil.copy2(img_path, os.path.join(CHECK_FOLDER, img_path.name))
            continue

    new_name = f"P{serial_no:07}.JPG"
    dst_path = os.path.join(PIC_FOLDER, new_name)

    shutil.copy2(img_path, dst_path)

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

    serial_no += 1


if serial_no == 1:
    print()
    print("================================")
    print("採用写真なし")
    print("PHOTO.XML 作成スキップ")
    print("================================")
else:
    xml_body = tostring(
        root,
        encoding="shift_jis",
        xml_declaration=False
    )

    with open(PHOTO_XML_PATH, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="Shift_JIS"?>\r\n')
        f.write(b'<!DOCTYPE photodata SYSTEM "PHOTO05.DTD">\r\n')
        f.write(xml_body)

    print()
    print("================================")
    print("PHOTO.XML 完成")
    print(PHOTO_XML_PATH)
    print("================================")


















    
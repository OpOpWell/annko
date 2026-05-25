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

PHOTO_ROOT = os.path.join(BASE_FOLDER, "selected_photos", "PHOTO")

PHOTO_XML_PATH = os.path.join(PHOTO_ROOT, "PHOTO.XML")

PIC_FOLDER = os.path.join(PHOTO_ROOT, "PIC")
EXCLUDE_FOLDER = os.path.join(PHOTO_ROOT, "EXCLUDE")
CHECK_FOLDER = os.path.join(PHOTO_ROOT, "CHECK")

SOURCE_DTD = os.path.join(BASE_FOLDER, "PHOTO05.DTD")

os.makedirs(PHOTO_ROOT, exist_ok=True)
os.makedirs(PIC_FOLDER, exist_ok=True)
os.makedirs(EXCLUDE_FOLDER, exist_ok=True)
os.makedirs(CHECK_FOLDER, exist_ok=True)

if os.path.exists(SOURCE_DTD):
    shutil.copy2(
        SOURCE_DTD,
        os.path.join(PHOTO_ROOT, "PHOTO05.DTD")
    )
    print("PHOTO05.DTD コピーOK")
else:
    print("PHOTO05.DTD がありません")


def safe_text(v):
    if v is None:
        return ""
    return str(v)


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
synonym_master = load_master(SYNONYM_MASTER)


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
    }

    for old, new in replace_map.items():
        text = text.replace(old, new)

    return text


def apply_synonym(text, category=None):
    text = safe_text(text)

    for row in synonym_master:
        src = safe_text(row.get("現場語"))
        dst = safe_text(row.get("正式語"))
        cat = safe_text(row.get("分類"))

        if not src or not dst:
            continue

        if category and cat != category:
            continue

        text = text.replace(src, dst)

    return text


def normalize_work_name(work):
    w = apply_synonym(work, "工種")
    w = normalize_text(w)

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

    return safe_text(work)


def normalize_type_name(type_name, detail_name="", blackboard_text=""):
    text = (
        apply_synonym(type_name, "種別")
        + apply_synonym(detail_name, "細別")
        + blackboard_text
    )

    text = normalize_text(text)

    if "熱中症" in text:
        return "安全管理"

    if "均平度" in text or "整地仕上げ" in text:
        return "整地仕上げ"

    if "敷均し" in text or "転圧" in text:
        return "均し工"

    if "床掘" in text or "掘削" in text:
        return "掘削"

    if "据付" in text or "布設" in text:
        return "据付工"

    return safe_text(type_name)


def normalize_detail_name(detail_name, blackboard_text=""):
    text = (
        apply_synonym(detail_name, "細別")
        + blackboard_text
    )

    text = normalize_text(text)

    if "熱中症" in text:
        return "熱中症対策"

    if "均平度" in text:
        return "均平度"

    if "基盤整地" in text:
        return "基盤整地"

    if "敷均し" in text and "転圧" in text:
        return "敷均・転圧状況"

    if "転圧" in text:
        return "転圧状況"

    if "床掘" in text or "掘削" in text:
        return "床掘・底付け状況"

    if "据付" in text or "布設" in text:
        return "据付状況"

    return safe_text(detail_name)


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
  "confidence": 90
}
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

        return json.loads(
            response.choices[0].message.content
        )

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
            "confidence": 0
        }


def score_master_row(
    row,
    source_all,
    ai_photo_type,
    ai_work,
    ai_type,
    ai_detail,
    ai_title
):
    score = 0

    m_photo_type = normalize_text(
        row.get("写真区分", "")
    )

    m_work = normalize_text(
        row.get("工種", "")
    )

    m_type = normalize_text(
        row.get("種別", "")
    )

    m_detail = normalize_text(
        row.get("細別", "")
    )

    m_title = normalize_text(
        row.get("写真タイトル", "")
    )

    if m_photo_type == normalize_text(ai_photo_type):
        score += 30

    if m_work == normalize_text(ai_work):
        score += 120

    if m_type == normalize_text(ai_type):
        score += 80

    if m_detail == normalize_text(ai_detail):
        score += 70

    if m_title == normalize_text(ai_title):
        score += 40

    return score


def match_master(
    photo_type,
    work,
    type_name,
    detail_name,
    title,
    blackboard_text
):
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

    return best, best_score, best_source


hash_db = {}


def is_duplicate(image_path):
    try:
        img = Image.open(image_path)
        h = str(imagehash.phash(img))

        if h in hash_db:
            return True

        hash_db[h] = image_path

        return False

    except:
        return False


root = Element("photodata")
root.set("DTD_version", "05")

base_info = SubElement(root, "基礎情報")

SubElement(base_info, "写真フォルダ名").text = "PHOTO/PIC"
SubElement(base_info, "参考図フォルダ名").text = "PHOTO/DRA"
SubElement(base_info, "適用要領基準").text = "土木202303-01"

image_files = []

for ext in ["*.jpg", "*.jpeg", "*.png"]:
    image_files.extend(
        Path(INPUT_FOLDER).rglob(ext)
    )

    image_files.extend(
        Path(INPUT_FOLDER).rglob(ext.upper())
    )

image_files = sorted(set(image_files))

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

        shutil.copy2(
            img_path,
            os.path.join(EXCLUDE_FOLDER, img_path.name)
        )

        continue

    result = analyze_image(str(img_path))

    usable = result.get("usable", False)
    unrelated = result.get("unrelated", False)

    blackboard_text = safe_text(
        result.get("blackboard_text")
    )

    photo_type = safe_text(
        result.get("photo_type")
    )

    work = safe_text(
        result.get("work")
    )

    type_name = safe_text(
        result.get("type_name")
    )

    detail_name = safe_text(
        result.get("detail_name")
    )

    title = safe_text(
        result.get("title")
    )

    location = safe_text(
        result.get("location")
    )

    work = normalize_work_name(work)

    type_name = normalize_type_name(
        type_name,
        detail_name,
        blackboard_text
    )

    detail_name = normalize_detail_name(
        detail_name,
        blackboard_text
    )

    print("黒板:")
    print(blackboard_text)

    print("写真区分:", photo_type)
    print("工種:", work)
    print("種別:", type_name)
    print("細別:", detail_name)

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

        if not type_name:
            type_name = matched.get("種別", "")

        if not detail_name:
            detail_name = matched.get("細別", "")

        if not title:
            title = matched.get("写真タイトル", "")

    if unrelated:
        print("別現場 → EXCLUDE")

        shutil.copy2(
            img_path,
            os.path.join(EXCLUDE_FOLDER, img_path.name)
        )

        continue

    if not usable:
        print("採用価値低 → CHECK")

        shutil.copy2(
            img_path,
            os.path.join(CHECK_FOLDER, img_path.name)
        )

        continue

    new_name = f"P{serial_no:07}.JPG"

    shutil.copy2(
        img_path,
        os.path.join(PIC_FOLDER, new_name)
    )

    print("採用保存:", new_name)

    photo_info = SubElement(root, "写真情報")

    file_info = SubElement(
        photo_info,
        "写真ファイル情報"
    )

    SubElement(file_info, "シリアル番号").text = str(serial_no)

    SubElement(file_info, "写真ファイル名").text = new_name

    SubElement(file_info, "メディア番号").text = "1"

    category = SubElement(
        photo_info,
        "撮影工種区分"
    )

    SubElement(category, "写真-大分類").text = "工事"
    SubElement(category, "写真区分").text = photo_type
    SubElement(category, "工種").text = work
    SubElement(category, "種別").text = type_name
    SubElement(category, "細別").text = detail_name
    SubElement(category, "写真タイトル").text = title

    shoot = SubElement(
        photo_info,
        "撮影情報"
    )

    SubElement(shoot, "撮影年月日").text = datetime.now().strftime("%Y-%m-%d")
    SubElement(shoot, "撮影箇所").text = location

    SubElement(photo_info, "代表写真").text = "0"
    SubElement(photo_info, "提出頻度写真").text = "0"

    serial_no += 1


xml_body = tostring(
    root,
    encoding="shift_jis",
    xml_declaration=False
)

with open(PHOTO_XML_PATH, "wb") as f:
    f.write(
        b'<?xml version="1.0" encoding="Shift_JIS"?>\r\n'
    )

    f.write(
        b'<!DOCTYPE photodata SYSTEM "PHOTO05.DTD">\r\n'
    )

    f.write(xml_body)

print()
print("================================")
print("PHOTO.XML 完成")
print(PHOTO_XML_PATH)
print("================================")


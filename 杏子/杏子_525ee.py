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

# =========================================
# API KEY
# =========================================

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# =========================================
# パス設定
# =========================================

BASE_FOLDER = r"C:\Users\user\foolder\杏子"
INPUT_FOLDER = r"C:/Users/user/OneDrive/hhh"

MASTER_CSV = os.path.join(BASE_FOLDER, "master_tree.csv")

PHOTO_XML_ROOT = os.path.join(
    BASE_FOLDER,
    "selected_photos",
    "PHOTO_XML"
)

PHOTO_XML_PATH = os.path.join(
    PHOTO_XML_ROOT,
    "PHOTO.XML"
)

PIC_FOLDER = os.path.join(PHOTO_XML_ROOT, "PIC")
EXCLUDE_FOLDER = os.path.join(PHOTO_XML_ROOT, "EXCLUDE")
CHECK_FOLDER = os.path.join(PHOTO_XML_ROOT, "CHECK")

SOURCE_DTD = os.path.join(BASE_FOLDER, "PHOTO05.DTD")

# =========================================
# フォルダ作成
# =========================================

os.makedirs(PHOTO_XML_ROOT, exist_ok=True)
os.makedirs(PIC_FOLDER, exist_ok=True)
os.makedirs(EXCLUDE_FOLDER, exist_ok=True)
os.makedirs(CHECK_FOLDER, exist_ok=True)

# =========================================
# DTDコピー
# =========================================

if os.path.exists(SOURCE_DTD):
    shutil.copy2(
        SOURCE_DTD,
        os.path.join(PHOTO_XML_ROOT, "PHOTO05.DTD")
    )
    print("PHOTO05.DTD コピーOK")
else:
    print("PHOTO05.DTD がありません")
    print(SOURCE_DTD)

# =========================================
# master_tree.csv 読込
# 対応列:
# 写真区分,工種,種別,細別,写真タイトル
# =========================================

master_list = []

if os.path.exists(MASTER_CSV):
    with open(MASTER_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            master_list.append(row)

    print("master_tree.csv 読込:", len(master_list))
else:
    print("master_tree.csv がありません")

# =========================================
# 安全文字化
# =========================================

def safe_text(v):
    if v is None:
        return ""
    return str(v)

# =========================================
# 重複判定
# =========================================

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

# =========================================
# テキスト正規化
# =========================================

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
    }

    for old, new in replace_map.items():
        text = text.replace(old, new)

    return text

# =========================================
# 撮影箇所補正
# 田番を最優先
# =========================================

def fix_location(location, blackboard_text):
    text = (
        safe_text(location)
        + "\n"
        + safe_text(blackboard_text)
    )

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
                str.maketrans(
                    "０１２３４５６７８９",
                    "0123456789"
                )
            )

            return f"田番{num}"

    if location and location not in ["不明", ""]:
        return location

    return ""

# =========================================
# 室内・事務所判定
# =========================================

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

# =========================================
# AI解析
# =========================================

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

最重要:
黒板文字を優先して読んでください。
ただし、写真全体も見てください。

黒板が写っていても、
室内・机・書類・会議室・事務所中心写真は、
現場施工写真として不適切な場合があります。

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

採用:
- 黒板が読める
- 工事内容が分かる
- 現場施工箇所が写る
- 作業内容が分かる
- 田番、測点、位置、作業名が分かる

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
黒板に「整地仕上げ」「均平度」「基盤整地」がある場合は、
work は 整地工
type_name は 整地仕上げ
detail_name は 均平度
寄りにしてください。

道路、市道取付、防護柵、敷砂利、表面排水などがある場合も、
黒板文字を優先して分類してください。
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

            response_format={
                "type": "json_object"
            }
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
            "title": "写真",
            "unrelated": True,
            "indoor_office": False,
            "confidence": 0
        }

# =========================================
# master_tree.csv 照合
# 写真区分・工種・種別・細別・写真タイトル対応
# =========================================

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

    src_photo_type = normalize_text(photo_type)
    src_work = normalize_text(work)
    src_type = normalize_text(type_name)
    src_detail = normalize_text(detail_name)
    src_title = normalize_text(title)
    src_blackboard = normalize_text(blackboard_text)

    source_all = (
        src_photo_type
        + src_work
        + src_type
        + src_detail
        + src_title
        + src_blackboard
    )

    for row in master_list:
        score = 0

        m_photo_type = normalize_text(row.get("写真区分", ""))
        m_work = normalize_text(row.get("工種", ""))
        m_type = normalize_text(row.get("種別", ""))
        m_detail = normalize_text(row.get("細別", ""))
        m_title = normalize_text(row.get("写真タイトル", ""))

        if m_photo_type and m_photo_type in source_all:
            score += 20

        if m_work and m_work in source_all:
            score += 30

        if m_type and m_type in source_all:
            score += 35

        if m_detail and m_detail in source_all:
            score += 40

        if m_title and m_title in source_all:
            score += 30

        if src_work and m_work and (src_work in m_work or m_work in src_work):
            score += 15

        if src_type and m_type and (src_type in m_type or m_type in src_type):
            score += 20

        if src_detail and m_detail and (src_detail in m_detail or m_detail in src_detail):
            score += 20

        if src_title and m_title and (src_title in m_title or m_title in src_title):
            score += 20

        if score > best_score:
            best_score = score
            best = row

    return best, best_score

# =========================================
# XML ROOT
# =========================================

root = Element("photodata")
root.set("DTD_version", "05")

# =========================================
# 基礎情報
# =========================================

base_info = SubElement(root, "基礎情報")

SubElement(base_info, "写真フォルダ名").text = "PHOTO/PIC"
SubElement(base_info, "参考図フォルダ名").text = "PHOTO/DRA"
SubElement(base_info, "適用要領基準").text = "土木202303-01"

# =========================================
# 画像一覧
# サブフォルダ込み
# =========================================

image_files = []

for ext in [
    "*.jpg",
    "*.jpeg",
    "*.png",
    "*.JPG",
    "*.JPEG",
    "*.PNG"
]:
    image_files.extend(
        Path(INPUT_FOLDER).rglob(ext)
    )

image_files = sorted(image_files)

print("================================")
print("工事写真解析開始")
print("対象枚数:", len(image_files))
print("================================")

# =========================================
# 写真処理
# =========================================

serial_no = 1

for img_path in image_files:
    print()
    print("================================")
    print(img_path.name)

    # =====================================
    # 重複
    # =====================================

    if is_duplicate(str(img_path)):
        print("重複検出 → EXCLUDE")

        shutil.copy2(
            img_path,
            os.path.join(EXCLUDE_FOLDER, img_path.name)
        )

        continue

    # =====================================
    # AI解析
    # =====================================

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

    # =====================================
    # 室内・事務所
    # =====================================

    if indoor_office or is_indoor_office(result):
        print("室内・事務所写真 → CHECK")

        shutil.copy2(
            img_path,
            os.path.join(CHECK_FOLDER, img_path.name)
        )

        continue

    # =====================================
    # master照合
    # =====================================

    matched, score = match_master(
        photo_type,
        work,
        type_name,
        detail_name,
        title,
        blackboard_text
    )

    print("master一致:", score)

    if matched:
        photo_type = matched.get("写真区分", photo_type) or photo_type
        work = matched.get("工種", work) or work
        type_name = matched.get("種別", type_name) or type_name
        detail_name = matched.get("細別", detail_name) or detail_name
        title = matched.get("写真タイトル", title) or title

        print("master採用 写真区分:", photo_type)
        print("master採用 工種:", work)
        print("master採用 種別:", type_name)
        print("master採用 細別:", detail_name)
        print("master採用 写真タイトル:", title)

    # =====================================
    # 別現場・無関係
    # =====================================

    if unrelated:
        print("別現場または無関係 → EXCLUDE")

        shutil.copy2(
            img_path,
            os.path.join(EXCLUDE_FOLDER, img_path.name)
        )

        continue

    # =====================================
    # AI価値低
    # =====================================

    if not usable:
        print("採用価値低 → CHECK")

        shutil.copy2(
            img_path,
            os.path.join(CHECK_FOLDER, img_path.name)
        )

        continue

    # =====================================
    # master一致低
    # =====================================

    if master_list and score < 30:
        print("master一致低 → CHECK")

        shutil.copy2(
            img_path,
            os.path.join(CHECK_FOLDER, img_path.name)
        )

        continue

    # =====================================
    # 採用保存
    # =====================================

    new_name = f"P{serial_no:07}.JPG"

    dst_path = os.path.join(PIC_FOLDER, new_name)

    shutil.copy2(img_path, dst_path)

    print("採用保存:", new_name)

    # =====================================
    # XML
    # =====================================

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

# =========================================
# XML保存
# =========================================

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
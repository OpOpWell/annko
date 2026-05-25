import os
import shutil
import base64
import json
import csv
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
黒板文字を最優先で読んでください。
黒板がある場合は、写真全体より黒板文字を優先してください。

JSONのみ返してください。

{
  "usable": true,
  "reason": "",
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

photo_type は以下から選んでください:
- 着手前及び完成写真
- 施工状況写真
- 安全管理写真
- 使用材料写真
- 品質管理写真
- 出来形管理写真
- 災害写真
- 事故写真
- その他

判定条件:

採用:
- 工事内容が分かる
- 黒板が読める
- 出来形管理や施工状況として使える
- 田番、測点、測定内容、作業内容が分かる

除外:
- 日常写真
- スナップ
- 別工事
- 別現場
- 黒板あるが無関係
- 黒板読めない
- ブレ
- ピンぼけ
- 工事写真として意味が薄い

注意:
工種・種別・細別は推測しすぎない。
黒板に「整地仕上げ」「均平度」がある場合は、
work は整地工寄り、
type_name は整地仕上げ寄り、
detail_name は均平度寄りにしてください。
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

        result = json.loads(
            response.choices[0].message.content
        )

        return result

    except Exception as e:
        print("AIエラー:", e)

        return {
            "usable": False,
            "reason": "AI失敗",
            "blackboard_text": "",
            "location": "",
            "photo_type": "その他",
            "work": "",
            "type_name": "",
            "detail_name": "",
            "title": "写真",
            "unrelated": True,
            "confidence": 0
        }

# =========================================
# master照合
# =========================================

def normalize_text(text):
    if text is None:
        return ""

    text = str(text)

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
        "整地整備": "整地",
        "整地場整備": "整地",
        "整地仕上": "整地仕上げ",
    }

    for old, new in replace_map.items():
        text = text.replace(old, new)

    return text

def match_master(work, type_name, detail_name, blackboard_text):
    best = None
    best_score = 0

    src_work = normalize_text(work)
    src_type = normalize_text(type_name)
    src_detail = normalize_text(detail_name)
    src_blackboard = normalize_text(blackboard_text)

    source_all = (
        src_work
        + src_type
        + src_detail
        + src_blackboard
    )

    for row in master_list:
        score = 0

        m_work = normalize_text(row.get("工種", ""))
        m_type = normalize_text(row.get("種別", ""))
        m_detail = normalize_text(row.get("細別", ""))

        # 工種一致
        if m_work and m_work in source_all:
            score += 30

        # 種別一致
        if m_type and m_type in source_all:
            score += 35

        # 細別一致
        if m_detail and m_detail in source_all:
            score += 35

        # AI欄との直接一致
        if src_work and m_work and (src_work in m_work or m_work in src_work):
            score += 15

        if src_type and m_type and (src_type in m_type or m_type in src_type):
            score += 20

        if src_detail and m_detail and (src_detail in m_detail or m_detail in src_detail):
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
    image_files.extend(Path(INPUT_FOLDER).glob(ext))

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
    # 重複チェック
    # =====================================

    if is_duplicate(str(img_path)):
        print("重複検出")

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
    reason = result.get("reason", "")
    blackboard_text = result.get("blackboard_text", "")
    location = result.get("location", "")
    photo_type = result.get("photo_type", "その他")
    work = result.get("work", "")
    type_name = result.get("type_name", "")
    detail_name = result.get("detail_name", "")
    title = result.get("title", "写真")
    confidence = result.get("confidence", 0)

    print("採用:", usable)
    print("理由:", reason)
    print("黒板:")
    print(blackboard_text)
    print("撮影箇所:", location)
    print("工種:", work)
    print("種別:", type_name)
    print("細別:", detail_name)
    print("信頼度:", confidence)

    # =====================================
    # master照合
    # =====================================

    matched, score = match_master(
        work,
        type_name,
        detail_name,
        blackboard_text
    )

    print("master一致:", score)

    if matched:
        work = matched.get("工種", work)
        type_name = matched.get("種別", type_name)
        detail_name = matched.get("細別", detail_name)

        print("master採用 工種:", work)
        print("master採用 種別:", type_name)
        print("master採用 細別:", detail_name)

    # =====================================
    # 別現場・無関係除外
    # =====================================

    if unrelated:
        print("別現場または無関係の可能性 → EXCLUDE")

        shutil.copy2(
            img_path,
            os.path.join(EXCLUDE_FOLDER, img_path.name)
        )

        continue

    # =====================================
    # AI的に価値低
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
    # master がある時だけ判定
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

    # -------------------------------------
    # 写真ファイル情報
    # -------------------------------------

    file_info = SubElement(photo_info, "写真ファイル情報")

    SubElement(file_info, "シリアル番号").text = str(serial_no)
    SubElement(file_info, "写真ファイル名").text = new_name
    SubElement(file_info, "メディア番号").text = "1"

    # -------------------------------------
    # 撮影工種区分
    # -------------------------------------

    category = SubElement(photo_info, "撮影工種区分")

    SubElement(category, "写真-大分類").text = "工事"
    SubElement(category, "写真区分").text = photo_type
    SubElement(category, "工種").text = work
    SubElement(category, "種別").text = type_name
    SubElement(category, "細別").text = detail_name
    SubElement(category, "写真タイトル").text = title

    # -------------------------------------
    # 撮影情報
    # -------------------------------------

    shoot = SubElement(photo_info, "撮影情報")

    SubElement(shoot, "撮影年月日").text = datetime.now().strftime("%Y-%m-%d")
    SubElement(shoot, "撮影箇所").text = location

    # -------------------------------------
    # その他
    # -------------------------------------

    SubElement(photo_info, "代表写真").text = "0"
    SubElement(photo_info, "提出頻度写真").text = "0"

    serial_no += 1

# =========================================
# XML保存
# =========================================

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





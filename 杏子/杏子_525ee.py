import os
import shutil
import base64
import json
from pathlib import Path
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring

from openai import OpenAI
from dotenv import load_dotenv

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

PHOTO_XML_ROOT = os.path.join(
    BASE_FOLDER,
    "selected_photos",
    "PHOTO_XML"
)

PHOTO_XML_PATH = os.path.join(
    PHOTO_XML_ROOT,
    "PHOTO.XML"
)

PHOTO_FOLDER = os.path.join(
    PHOTO_XML_ROOT,
    "PHOTO"
)

PIC_FOLDER = os.path.join(
    PHOTO_XML_ROOT,
    "PIC"
)

DRA_FOLDER = os.path.join(
    PHOTO_XML_ROOT,
    "DRA"
)

SOURCE_DTD = os.path.join(
    BASE_FOLDER,
    "PHOTO05.DTD"
)

# =========================================
# フォルダ作成
# =========================================

os.makedirs(PHOTO_XML_ROOT, exist_ok=True)
os.makedirs(PHOTO_FOLDER, exist_ok=True)
os.makedirs(PIC_FOLDER, exist_ok=True)
os.makedirs(DRA_FOLDER, exist_ok=True)

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
# AI分類
# =========================================

def classify_image(image_path):

    try:

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(
                f.read()
            ).decode()

        response = client.chat.completions.create(
            model="gpt-4.1-mini",

            messages=[
                {
                    "role": "user",

                    "content": [

                        {
                            "type": "text",

                            "text": """
工事写真を分類してください。

JSONのみ返してください。

{
  "photo_type":"施工状況写真",
  "work":"道路工",
  "type_name":"掘削工",
  "detail_name":"床掘",
  "title":"床掘状況"
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

        print("分類エラー:", e)

        return {
            "photo_type": "その他",
            "work": "",
            "type_name": "",
            "detail_name": "",
            "title": "写真"
        }

# =========================================
# XML ROOT
# =========================================

root = Element("photodata")

root.set("DTD_version", "05")

# =========================================
# 基礎情報
# =========================================

base_info = SubElement(
    root,
    "基礎情報"
)

SubElement(
    base_info,
    "写真フォルダ名"
).text = "PHOTO/PIC"

SubElement(
    base_info,
    "参考図フォルダ名"
).text = "PHOTO/DRA"

SubElement(
    base_info,
    "適用要領基準"
).text = "土木202303-01"

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

    image_files.extend(
        Path(INPUT_FOLDER).glob(ext)
    )

image_files = sorted(image_files)

print("================================")
print("PHOTO.XML 作成開始")
print("対象枚数:", len(image_files))
print("================================")

# =========================================
# 写真処理
# =========================================

serial_no = 1

for img_path in image_files:

    print()
    print(f"[{serial_no}] {img_path.name}")

    result = classify_image(
        str(img_path)
    )

    photo_type = result.get(
        "photo_type",
        "その他"
    )

    work_name = result.get(
        "work",
        ""
    )

    type_name = result.get(
        "type_name",
        ""
    )

    detail_name = result.get(
        "detail_name",
        ""
    )

    title = result.get(
        "title",
        "写真"
    )

    print("分類:", photo_type)
    print("工種:", work_name)
    print("種別:", type_name)
    print("細別:", detail_name)
    print("タイトル:", title)

    # =====================================
    # ファイルコピー
    # =====================================

    new_name = f"P{serial_no:07}.JPG"

    dst_path = os.path.join(
        PIC_FOLDER,
        new_name
    )

    shutil.copy2(
        img_path,
        dst_path
    )

    # =====================================
    # XML
    # =====================================

    photo_info = SubElement(
        root,
        "写真情報"
    )

    # -----------------------------
    # 写真ファイル情報
    # -----------------------------

    file_info = SubElement(
        photo_info,
        "写真ファイル情報"
    )

    SubElement(
        file_info,
        "シリアル番号"
    ).text = str(serial_no)

    SubElement(
        file_info,
        "写真ファイル名"
    ).text = new_name

    SubElement(
        file_info,
        "メディア番号"
    ).text = "1"

    # -----------------------------
    # 撮影工種区分
    # -----------------------------

    category = SubElement(
        photo_info,
        "撮影工種区分"
    )

    SubElement(
        category,
        "写真-大分類"
    ).text = "工事"

    SubElement(
        category,
        "写真区分"
    ).text = photo_type

    if work_name:

        SubElement(
            category,
            "工種"
        ).text = work_name

    if type_name:

        SubElement(
            category,
            "種別"
        ).text = type_name

    if detail_name:

        SubElement(
            category,
            "細別"
        ).text = detail_name

    SubElement(
        category,
        "写真タイトル"
    ).text = title

    # -----------------------------
    # 撮影情報
    # -----------------------------

    shoot = SubElement(
        photo_info,
        "撮影情報"
    )

    SubElement(
        shoot,
        "撮影年月日"
    ).text = datetime.now().strftime(
        "%Y-%m-%d"
    )

    # -----------------------------
    # その他
    # -----------------------------

    SubElement(
        photo_info,
        "代表写真"
    ).text = "0"

    SubElement(
        photo_info,
        "提出頻度写真"
    ).text = "0"

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

    f.write(
        b'<?xml version="1.0" encoding="Shift_JIS"?>\r\n'
    )

    f.write(
        b'<!DOCTYPE photodata SYSTEM "PHOTO05.DTD">\r\n'
    )

    f.write(xml_body)

print()
print("================================")
print("PHOTO.XML 作成完了")
print(PHOTO_XML_PATH)
print("================================")

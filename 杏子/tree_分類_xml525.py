import os
import csv
import xml.etree.ElementTree as ET
from pathlib import Path

# =========================================
# パス設定
# =========================================

BASE_FOLDER = r"C:\Users\user\foolder\杏子"

XML_FOLDER = os.path.join(
    BASE_FOLDER,
    "old_xml"
)

OUTPUT_CSV = os.path.join(
    BASE_FOLDER,
    "master_tree.csv"
)

# =========================================
# XML文字コード対応
# =========================================

def parse_xml(xml_path):
    encodings = [
        "shift_jis",
        "cp932",
        "utf-8",
        "utf-8-sig"
    ]

    last_error = None

    for enc in encodings:
        try:
            with open(xml_path, "r", encoding=enc) as f:
                text = f.read()

            root = ET.fromstring(text)

            return root

        except Exception as e:
            last_error = e

    raise last_error

# =========================================
# 安全文字取得
# =========================================

def get_text(parent, tag_name):
    if parent is None:
        return ""

    elem = parent.find(tag_name)

    if elem is None:
        return ""

    if elem.text is None:
        return ""

    return elem.text.strip()

# =========================================
# XMLからツリー抽出
# =========================================

def extract_tree_from_xml(xml_path):
    rows = []

    root = parse_xml(xml_path)

    for photo_info in root.findall(".//写真情報"):

        category = photo_info.find("撮影工種区分")

        if category is None:
            continue

        photo_type = get_text(
            category,
            "写真区分"
        )

        work = get_text(
            category,
            "工種"
        )

        type_name = get_text(
            category,
            "種別"
        )

        detail_name = get_text(
            category,
            "細別"
        )

        title = get_text(
            category,
            "写真タイトル"
        )

        # 全部空なら無視
        if not any([
            photo_type,
            work,
            type_name,
            detail_name,
            title
        ]):
            continue

        rows.append({
            "写真区分": photo_type,
            "工種": work,
            "種別": type_name,
            "細別": detail_name,
            "写真タイトル": title
        })

    return rows

# =========================================
# 重複除去
# =========================================

def unique_rows(rows):
    seen = set()
    result = []

    for row in rows:
        key = (
            row.get("写真区分", ""),
            row.get("工種", ""),
            row.get("種別", ""),
            row.get("細別", ""),
            row.get("写真タイトル", "")
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(row)

    return result

# =========================================
# メイン
# =========================================

def main():
    xml_files = []

    for ext in [
        "*.xml",
        "*.XML"
    ]:
        xml_files.extend(
            Path(XML_FOLDER).rglob(ext)
        )

    xml_files = sorted(xml_files)

    print("================================")
    print("デキスパートXML → master_tree.csv")
    print("XMLフォルダ:", XML_FOLDER)
    print("XML数:", len(xml_files))
    print("================================")

    if not xml_files:
        print("XMLがありません")
        return

    all_rows = []

    for xml_path in xml_files:
        print("読込:", xml_path.name)

        try:
            rows = extract_tree_from_xml(
                str(xml_path)
            )

            print("抽出:", len(rows))

            all_rows.extend(rows)

        except Exception as e:
            print("XML読込エラー:", xml_path)
            print(e)

    all_rows = unique_rows(all_rows)

    print("重複除去後:", len(all_rows))

    with open(
        OUTPUT_CSV,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "写真区分",
                "工種",
                "種別",
                "細別",
                "写真タイトル"
            ]
        )

        writer.writeheader()

        for row in all_rows:
            writer.writerow(row)

    print()
    print("================================")
    print("master_tree.csv 作成完了")
    print(OUTPUT_CSV)
    print("================================")

if __name__ == "__main__":
    main()
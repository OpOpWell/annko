from openai import OpenAI
import base64
import os
import csv
import re
import json

client = OpenAI()

print("SSK写真 OCR → 田番別CSV 自動作成開始")

image_folder = "SSK"
output_folder = "ssk_output"

os.makedirs(output_folder, exist_ok=True)

# 田番ごとの測点数
expected_counts = {
    "19": 30,
    "18": 16,
    "17": 14,
    "16": 12,
    "15": 12,
    "14": 11,
    "13": 22,
    "12": 23,
}

csv_by_taban = {}
meta_by_taban = {}
log_lines = []


def log(message):
    print(message)
    log_lines.append(str(message))


image_files = sorted([
    f for f in os.listdir(image_folder)
    if f.lower().endswith((".png", ".jpg", ".jpeg"))
    and not f.startswith("crop_")
])


def gpt_ocr(image_path, model_name):

    with open(image_path, "rb") as f:
        base64_image = base64.b64encode(f.read()).decode("utf-8")

    response = client.responses.create(
        model=model_name,
        temperature=0,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": """
このSSK出来形測定写真から情報を読み取ってください。

重要:
- 田番は、上部の「田番」欄に印刷されている数字だけを読む
- 大きく丸で書かれた手書き数字は田番として使わない
- 表の測点番号 1,2,3... は田番として使わない
- 測定項目は「均平度」
- 工種は「整地工」

読む項目:
- 田番
- 面積
- 測定基準
- 規格値
- 社内目標値
- 平均値
- Xmax
- Xmin
- 番号と手書き実測値

条件:
- 番号と手書き実測値を対応させる
- 空欄は無視
- 実測値は1.300〜1.600程度
- 実測値は小数3桁
- JSONのみ返す
- 説明不要
- ```json のようなコードブロックは禁止
- 推測しない
- 読めない値は空文字または除外

返却形式:
{
  "taban": "19",
  "work_type": "整地工",
  "measurement_item": "均平度",
  "area": "9750㎡",
  "standard": "10a当たり3点以上",
  "spec_value": "±50mm",
  "target_value": "±40mm",
  "average": "1.410",
  "xmax": "1.400",
  "xmin": "1.421",
  "values": [
    {"no": 1, "value": 1.418},
    {"no": 2, "value": 1.400}
  ]
}
"""
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{base64_image}"
                    }
                ]
            }
        ]
    )

    result_text = response.output_text.strip()

    log(f"\nGPT結果 ({model_name})")
    log(result_text)

    result_text = result_text.replace("```json", "")
    result_text = result_text.replace("```", "")

    match_json = re.search(r"\{.*\}", result_text, re.DOTALL)

    if not match_json:
        log("JSONが見つかりません")
        return {}

    try:
        return json.loads(match_json.group())
    except Exception as e:
        log("JSON変換失敗")
        log(e)
        return {}


for image_name in image_files:

    image_path = os.path.join(image_folder, image_name)

    log(f"\n処理中: {image_path}")

    result = gpt_ocr(image_path, "gpt-4.1-mini")

    taban = str(result.get("taban", "")).strip()
    work_type = str(result.get("work_type", "整地工")).strip()
    measurement_item = str(result.get("measurement_item", "均平度")).strip()

    if work_type == "":
        work_type = "整地工"

    if measurement_item == "":
        measurement_item = "均平度"

    # 田番が変ならファイル名から探す
    if taban not in expected_counts:
        name_without_ext = os.path.splitext(image_name)[0]

        found = ""
        for key in expected_counts.keys():
            if key in name_without_ext:
                found = key
                break

        if found:
            taban = found
        else:
            taban = "未分類"

    if taban not in meta_by_taban:
        meta_by_taban[taban] = {
            "工種": work_type,
            "測定項目": measurement_item,
            "面積": result.get("area", ""),
            "測定基準": result.get("standard", ""),
            "規格値": result.get("spec_value", ""),
            "社内目標値": result.get("target_value", ""),
            "平均値": result.get("average", ""),
            "Xmax": result.get("xmax", ""),
            "Xmin": result.get("xmin", ""),
        }

    values = result.get("values", [])

    value_dict = {}

    for item in values:
        try:
            no = int(item["no"])
            value = float(item["value"])
            value_dict[no] = value
        except:
            pass

    total_count = expected_counts.get(taban)

    if total_count is None:
        if value_dict:
            total_count = max(value_dict.keys())
        else:
            total_count = 0

    missing_no = []

    for no in range(1, total_count + 1):
        if no not in value_dict:
            missing_no.append(no)

    if missing_no:

        log("\n未読No検出")
        log(missing_no)

        log("\n4.1で再OCR実施")

        retry_result = gpt_ocr(image_path, "gpt-4.1")
        retry_values = retry_result.get("values", [])

        for item in retry_values:
            try:
                no = int(item["no"])
                value = float(item["value"])

                if no not in value_dict:
                    value_dict[no] = value
            except:
                pass

    if taban not in csv_by_taban:
        csv_by_taban[taban] = []

    for no in range(1, total_count + 1):

        point_name = f"No.{no}"

        if no in value_dict:
            value_text = f"{value_dict[no]:.3f}"
        else:
            value_text = ""

        csv_by_taban[taban].append([
            point_name,
            f"{work_type}田番{taban}",
            measurement_item,
            value_text
        ])


for taban, rows in csv_by_taban.items():

    missing_by_item = {}

    for row in rows:
        point_name = row[0]
        measurement_item = row[2]
        value_text = row[3]

        if value_text == "":
            if measurement_item not in missing_by_item:
                missing_by_item[measurement_item] = []

            missing_by_item[measurement_item].append(point_name)

    if missing_by_item:
        log(f"\n未読あり: 田番{taban}")

        for item_name, missing_no in missing_by_item.items():
            log(
                f"{item_name} 未読No: "
                + ", ".join(missing_no)
            )
    else:
        log(f"\n未読なし: 田番{taban}")

    output_csv = os.path.join(
        output_folder,
        f"田番{taban}.csv"
    )

    with open(
        output_csv,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "測点",
            "工種",
            "測定項目",
            "実測値"
        ])

        writer.writerows(rows)

    log(f"\nCSV保存完了: {output_csv}")

    for row in rows:
        log(" ".join(row))


meta_csv = os.path.join(output_folder, "測定情報.csv")

with open(
    meta_csv,
    "w",
    newline="",
    encoding="utf-8-sig"
) as f:

    writer = csv.writer(f)

    writer.writerow([
        "田番",
        "工種",
        "測定項目",
        "面積",
        "測定基準",
        "規格値",
        "社内目標値",
        "平均値",
        "Xmax",
        "Xmin"
    ])

    for taban, meta in meta_by_taban.items():
        writer.writerow([
            taban,
            meta.get("工種", ""),
            meta.get("測定項目", ""),
            meta.get("面積", ""),
            meta.get("測定基準", ""),
            meta.get("規格値", ""),
            meta.get("社内目標値", ""),
            meta.get("平均値", ""),
            meta.get("Xmax", ""),
            meta.get("Xmin", "")
        ])

log(f"\n測定情報CSV保存完了: {meta_csv}")

log("\n全部完了")

with open(
    "ssk_ocr_log.txt",
    "w",
    encoding="utf-8"
) as f:

    f.write("\n".join(log_lines))

print("OCRログ保存完了: ssk_ocr_log.txt")





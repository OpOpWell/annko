from openai import OpenAI
import base64
import os
import csv
import re
import json

client = OpenAI()

print("GPT OCR → デキスパートCSV 田番別自動作成開始")

image_folder = "images"
output_folder = "output"

os.makedirs(output_folder, exist_ok=True)

expected_counts = {
    "19": 30,
    "18": 17,
    "17": 14,
    "16": 12,
    "15": 12,
    "14": 11,
    "13": 22,
}

csv_by_taban = {}
meta_by_taban = {}
log_lines = []

image_files = sorted([
    f for f in os.listdir(image_folder)
    if f.lower().endswith((".png", ".jpg", ".jpeg"))
    and not f.startswith("crop_")
])


def log(message):
    print(message)
    log_lines.append(str(message))


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
この画像の出来形測定表から情報を読み取ってください。

読む項目:
- 面積
- 測定基準
- 規格値
- 社内目標値
- 平均値
- Xmax
- Xmin
- 番号と手書き実測値

条件:
- 田番と測定項目は読まなくてよい
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
  "area": "9750㎡",
  "standard": "10a当たり3点以上",
  "spec_value": "±50mm",
  "target_value": "±40mm",
  "average": "1.410",
  "xmax": "1.421",
  "xmin": "1.400",
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

    match_json = re.search(
        r"\{.*\}",
        result_text,
        re.DOTALL
    )

    if not match_json:
        log("JSONが見つかりません")
        return {}

    json_text = match_json.group()

    try:
        return json.loads(json_text)
    except Exception as e:
        log("JSON変換失敗")
        log(e)
        return {}


for image_name in image_files:

    image_path = os.path.join(image_folder, image_name)

    log(f"\n処理中: {image_path}")

    # 田番・測定項目はファイル名から取得
    parts = os.path.splitext(image_name)[0].split("_")

    if len(parts) >= 2:
        measurement_item = parts[1]
    else:
        measurement_item = "測定"

    if len(parts) >= 3:
        taban = parts[2]
    else:
        taban = "未分類"

    result = gpt_ocr(image_path, "gpt-4.1-mini")

    if taban not in meta_by_taban:
        meta_by_taban[taban] = {
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
            f"整地工田番{taban}",
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
    "ocr_log.txt",
    "w",
    encoding="utf-8"
) as f:

    f.write("\n".join(log_lines))

print("OCRログ保存完了: ocr_log.txt")





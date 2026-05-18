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

# 田番ごとの測点数
expected_counts = {
    "19": 30,
    "18": 12,
    "17": 14,
    "16": 12,
    "15": 12,
    "14": 11,
    "13": 22,
}

csv_by_taban = {}

image_files = sorted([
    f for f in os.listdir(image_folder)
    if f.lower().endswith((".png", ".jpg", ".jpeg"))
])

# -----------------------------
# OCR関数
# -----------------------------
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
この画像の測定表から、
番号と手書き実測値をセットで読み取ってください。

条件:
- 印刷された番号と、その横の手書き数値を対応させる
- 空欄は無視
- 実測値は1.300〜1.600程度
- 小数3桁
- JSONのみ返す
- 説明不要
- ```json のようなコードブロックは禁止
- 推測しない
- 読めない値は除外

返却形式:
[
  {"no": 1, "value": 1.418},
  {"no": 2, "value": 1.400}
]
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

    print(f"\nGPT結果 ({model_name})")
    print(result_text)

    result_text = result_text.replace("```json", "")
    result_text = result_text.replace("```", "")

    match_json = re.search(
        r"\[.*\]",
        result_text,
        re.DOTALL
    )

    if not match_json:
        return []

    json_text = match_json.group()

    try:
        values = json.loads(json_text)
        return values
    except:
        return []


# -----------------------------
# メイン処理
# -----------------------------
for image_name in image_files:

    image_path = os.path.join(image_folder, image_name)

    print(f"\n処理中: {image_path}")

    parts = os.path.splitext(image_name)[0].split("_")

    if len(parts) >= 2:
        measurement_item = parts[1]
    else:
        measurement_item = "測定"

    if len(parts) >= 3:
        taban = parts[2]
    else:
        taban = "未分類"

    # -----------------------------
    # 1回目 mini OCR
    # -----------------------------
    values = gpt_ocr(
        image_path,
        "gpt-4.1-mini"
    )

    value_dict = {}

    for item in values:
        try:
            no = int(item["no"])
            value = float(item["value"])
            value_dict[no] = value
        except:
            pass

    # 田番ごとの固定測点数
    total_count = expected_counts.get(taban)

    if total_count is None:
        if value_dict:
            total_count = max(value_dict.keys())
        else:
            total_count = 0

    # -----------------------------
    # 未読No検出
    # -----------------------------
    missing_no = []

    for no in range(1, total_count + 1):
        if no not in value_dict:
            missing_no.append(no)

    # -----------------------------
    # 未読があれば4.1再OCR
    # -----------------------------
    if missing_no:

        print("\n未読No検出")
        print(missing_no)

        print("\n4.1で再OCR実施")

        retry_values = gpt_ocr(
            image_path,
            "gpt-4.1"
        )

        for item in retry_values:
            try:
                no = int(item["no"])
                value = float(item["value"])

                # 未読のみ上書き
                if no not in value_dict:
                    value_dict[no] = value

            except:
                pass

    # -----------------------------
    # CSV格納
    # -----------------------------
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


# -----------------------------
# CSV保存
# -----------------------------
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

        print(f"\n未読あり: 田番{taban}")

        for item_name, missing_no in missing_by_item.items():
            print(
                f"{item_name} 未読No:",
                ", ".join(missing_no)
            )

    else:
        print(f"\n未読なし: 田番{taban}")

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
        writer.writerows(rows)

    print("\nCSV保存完了:", output_csv)

    for row in rows:
        print(*row)

print("\n全部完了")
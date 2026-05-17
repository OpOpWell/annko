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

for image_name in image_files:

    image_path = os.path.join(image_folder, image_name)

    print(f"処理中: {image_path}")

    parts = os.path.splitext(image_name)[0].split("_")

    if len(parts) >= 2:
        measurement_item = parts[1]
    else:
        measurement_item = "測定"

    if len(parts) >= 3:
        taban = parts[2]
    else:
        taban = "未分類"

    with open(image_path, "rb") as f:
        base64_image = base64.b64encode(f.read()).decode("utf-8")

    response = client.responses.create(
        model="gpt-4.1-mini",
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

    print("GPT結果")
    print(result_text)

    result_text = result_text.replace("```json", "")
    result_text = result_text.replace("```", "")

    match_json = re.search(
        r"\[.*\]",
        result_text,
        re.DOTALL
    )

    if not match_json:
        print("JSONが見つかりません")
        continue

    json_text = match_json.group()

    try:
        values = json.loads(json_text)
    except Exception as e:
        print("JSON変換失敗")
        print(e)
        continue

    if taban not in csv_by_taban:
        csv_by_taban[taban] = []

    value_dict = {}

    for item in values:
        try:
            no = int(item["no"])
            value = float(item["value"])
            value_dict[no] = value
        except:
            pass

    # 田番ごとの固定測点数を使う
    total_count = expected_counts.get(taban)

    if total_count is None:
        if value_dict:
            total_count = max(value_dict.keys())
        else:
            total_count = 0

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

    print("CSV保存完了:", output_csv)

    for row in rows:
        print(*row)

print("全部完了")
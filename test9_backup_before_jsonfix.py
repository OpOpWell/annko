from openai import OpenAI
import base64
import os
import csv
import re
import json

client = OpenAI()

print("GPT OCR → デキスパートCSV 自動作成開始")

image_folder = "images"
csv_data = []

# 画像ファイル取得
image_files = sorted([
    f for f in os.listdir(image_folder)
    if f.lower().endswith((".png", ".jpg", ".jpeg"))
])

for image_name in image_files:

    image_path = os.path.join(image_folder, image_name)

    print(f"処理中: {image_path}")

    # ----------------------------
    # ファイル名解析
    # ----------------------------

    # GE開始番号取得
    match = re.search(r"GE-(\d+)", image_name)

    if not match:
        print("GE番号なし:", image_name)
        continue

    start_num = int(match.group(1))

    # 測定項目名取得
    parts = image_name.split("_")

    if len(parts) >= 2:
        measurement_item = parts[1]
    else:
        measurement_item = "測定"

    # 拡張子削除
    measurement_item = os.path.splitext(measurement_item)[0]

    # ----------------------------
    # 画像base64化
    # ----------------------------

    with open(image_path, "rb") as f:
        base64_image = base64.b64encode(f.read()).decode("utf-8")

    # ----------------------------
    # GPT OCR
    # ----------------------------

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

    # ----------------------------
    # JSON変換
    # ----------------------------

    try:
        values = json.loads(result_text)

    except Exception as e:
        print("JSON変換失敗")
        print(e)
        continue

    # ----------------------------
    # CSVデータ作成
    # ----------------------------

    for item in values:

        try:

            no = int(item["no"])
            value = float(item["value"])

            point_no = start_num + no - 1

            point_name = f"GE-{point_no:03d}"

            csv_data.append([
                point_name,
                measurement_item,
                f"{value:.3f}"
            ])

        except Exception as e:
            print("データ変換失敗")
            print(item)
            print(e)

# ----------------------------
# CSV保存
# ----------------------------

with open("dekispart.csv", "w", newline="", encoding="utf-8-sig") as f:

    writer = csv.writer(f)

    writer.writerows(csv_data)

print("CSV保存完了: dekispart.csv")

print("CSV内容")

for row in csv_data:
    print(*row)
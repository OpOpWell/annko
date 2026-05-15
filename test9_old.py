from openai import OpenAI
import base64
import json
import pandas as pd
import os
import re

print("GPT OCR → デキスパートCSV 自動作成開始")

client = OpenAI()

image_folder = "images"
output_csv = "dekispart.csv"

measurement_item = "均平度"

csv_data = []

def image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

for filename in sorted(os.listdir(image_folder)):

    if filename.lower().endswith((".png", ".jpg", ".jpeg")):

        image_path = os.path.join(image_folder, filename)

        print("処理中:", image_path)

        base64_image = image_to_base64(image_path)

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": """
この画像の測定表から、手書きの実測値だけを番号順に読み取ってください。

条件:
- 番号列は読まない
- 実測値だけ読む
- 1.400〜1.500付近の数値だけ
- 小数3桁で返す
- JSON配列だけ返す
- 説明文はいらない

例:
[1.468, 1.453, 1.461]
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

        # JSONだけ抽出
        match = re.search(r"\[.*\]", result_text, re.DOTALL)

        if not match:
            print("JSONが見つかりません:", filename)
            continue

        values = json.loads(match.group())

        # ファイル名例: GE-001_均平度.jpg
        name_only = os.path.splitext(filename)[0]
        parts = name_only.split("_")

        start_point = parts[0]

        if len(parts) >= 2:
            measurement_item = parts[1]

        start_num = int(start_point.replace("GE-", ""))

        for i, value in enumerate(values):

            point_no = start_num + i
            point_name = f"GE-{point_no:03d}"

            csv_data.append([
                point_name,
                measurement_item,
                f"{float(value):.3f}"
            ])

df = pd.DataFrame(csv_data)

df.to_csv(
    output_csv,
    index=False,
    header=False,
    encoding="cp932"
)

print("CSV保存完了:", output_csv)

print("CSV内容")
for row in csv_data:
    print(row[0], row[1], row[2])
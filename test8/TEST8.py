from PIL import Image
import pytesseract
import re
import pandas as pd
import os
import base64
import json
from openai import OpenAI

print("OCR → デキスパートCSV 自動作成開始")

# =========================
# OpenAI設定
# =========================
client = OpenAI(api_key="ここにAPIキーを入れる")

# =========================
# Tesseractパス
# =========================
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

image_folder = "images"
output_csv = "dekispart.csv"

csv_data = []


def gpt_ocr(image_path):
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": """
この画像の中にある測定値だけを読んでください。

条件:
- 幅の値だけ読む
- 値はだいたい 1.300〜1.500 の範囲
- 余計な文字は出さない
- JSON配列だけで返す

例:
[1.403]
[1.403, 1.405, 1.400]
"""
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{image_b64}"
                    }
                ]
            }
        ]
    )

    text = response.output_text.strip()
    print("GPT結果")
    print(text)

    return json.loads(text)


def tesseract_ocr(image_file):
    img = Image.open(image_file)

    img = img.convert("L")
    img = img.point(lambda x: 0 if x < 200 else 255)

    debug_file = "確認_" + os.path.basename(image_file)
    img.save(debug_file)

    print("確認画像保存:", debug_file)

    text = pytesseract.image_to_string(
        img,
        lang="eng",
        config=(
            "--psm 4 "
            "-c tessedit_char_whitelist=0123456789."
        )
    )

    print("OCR結果")
    print(text)

    raw_values = re.findall(
        r"[0-9]?\.[0-9]{1,3}|[0-9]{4}",
        text
    )

    print("抽出数値")
    print(raw_values)

    values = []

    for v in raw_values:

        if v.startswith("."):
            v = "1" + v

        elif "." not in v and len(v) == 4:
            v = str(float(v) / 1000)

        if "." in v:
            left, right = v.split(".")

            if len(right) == 1:
                right = right + "00"
            elif len(right) == 2:
                right = right + "0"

            v = left + "." + right

        num = float(v)

        if 1.3 <= num <= 1.5:
            values.append(num)

    return values


for filename in sorted(os.listdir(image_folder)):

    if filename.lower().endswith((".png", ".jpg", ".jpeg")):

        image_file = os.path.join(image_folder, filename)

        print("処理中:", image_file)

        # まずTesseract
        values = tesseract_ocr(image_file)

        # 取れなかったらGPT
        if True:
            print("Tesseractで取れないためGPT OCRへ")
            values = gpt_ocr(image_file)

        values = [float(v) for v in values if 1.3 <= float(v) <= 1.5]

        print(filename, "→", values)

        name_only = os.path.splitext(filename)[0]
        parts = name_only.split("_")

        start_point = parts[0]

        if len(parts) >= 2:
            measurement_item = parts[1]
        else:
            measurement_item = "幅"

        start_num = int(start_point.replace("GE-", ""))

        for i, value in enumerate(values):

            point_no = start_num + i
            point_name = f"GE-{point_no:03d}"

            csv_data.append([
                point_name,
                measurement_item,
                f"{value:.3f}"
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

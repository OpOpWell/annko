from openai import OpenAI
from PIL import Image
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
log_lines = []

# crop_画像は除外
image_files = sorted([
    f for f in os.listdir(image_folder)
    if f.lower().endswith((".png", ".jpg", ".jpeg"))
    and not f.startswith("crop_")
])


def log(message):
    print(message)
    log_lines.append(str(message))


# -----------------------------
# 下1/3切り抜きOCR用
# -----------------------------
def crop_bottom_half(image_path):

    img = Image.open(image_path)

    width, height = img.size

    crop_area = (
        0,
        height * 2 // 3,
        width,
        height
    )

    cropped = img.crop(crop_area)

    base_name = os.path.basename(image_path)

    crop_path = os.path.join(
        image_folder,
        "crop_" + base_name
    )

    cropped.save(crop_path)

    log(f"切り抜き保存: {crop_path}")

    return crop_path


# -----------------------------
# GPT OCR関数
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

    log(f"\nGPT結果 ({model_name})")
    log(result_text)

    result_text = result_text.replace("```json", "")
    result_text = result_text.replace("```", "")

    match_json = re.search(
        r"\[.*\]",
        result_text,
        re.DOTALL
    )

    if not match_json:
        log("JSONが見つかりません")
        return []

    json_text = match_json.group()

    try:
        values = json.loads(json_text)
        return values

    except Exception as e:
        log("JSON変換失敗")
        log(e)
        return []


# -----------------------------
# メイン処理
# -----------------------------
for image_name in image_files:

    image_path = os.path.join(
        image_folder,
        image_name
    )

    log(f"\n処理中: {image_path}")

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

    # -----------------------------
    # 固定測点数
    # -----------------------------
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
    # 未読あれば分割OCR
    # -----------------------------
    if missing_no:

        log("\n未読No検出")
        log(missing_no)

        log("\n画像切り抜きOCR開始")

        crop_path = crop_bottom_half(
            image_path
        )

        retry_values = gpt_ocr(
            crop_path,
            "gpt-4.1"
        )

        for item in retry_values:

            try:
                no = int(item["no"])
                value = float(item["value"])

                # 未読のみ追加
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

        # ヘッダ追加
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


log("\n全部完了")

# -----------------------------
# OCRログ保存
# -----------------------------
with open(
    "ocr_log.txt",
    "w",
    encoding="utf-8"
) as f:

    f.write("\n".join(log_lines))

print("OCRログ保存完了: ocr_log.txt")
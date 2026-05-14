from PIL import Image
import pytesseract
import re
import pandas as pd
import os

print("OCR → デキスパートCSV 自動作成開始")

# Tesseractパス
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# 画像フォルダ
image_folder = "images"

# 出力CSV
output_csv = "dekispart.csv"

csv_data = []

# ファイル名順に処理
for filename in sorted(os.listdir(image_folder)):

    if filename.lower().endswith((".png", ".jpg", ".jpeg")):

        image_file = os.path.join(image_folder, filename)

        print("処理中:", image_file)

        # 画像読込
        img = Image.open(image_file)

        # グレースケール化
        img = img.convert("L")

        # OCR精度向上（二値化）
        img = img.point(lambda x: 0 if x < 180 else 255)

        # 確認画像保存
        debug_file = "確認_" + filename
        img.save(debug_file)

        print("確認画像保存:", debug_file)

        # OCR
        text = pytesseract.image_to_string(
            img,
            lang="eng",
            config=(
                "--psm 11 "
                "-c tessedit_char_whitelist=0123456789."
            )
        )

        print("OCR結果")
        print(text)

        # 数値抽出
        raw_values = re.findall(
            r"[0-9]?\.[0-9]{1,3}|[0-9]{4}",
            text
        )

        print("抽出数値")
        print(raw_values)

        values = []

        for v in raw_values:

            # .403 → 1.403
            if v.startswith("."):
                v = "1" + v

            # 1405 → 1.405
            elif "." not in v and len(v) == 4:
                v = str(float(v) / 1000)

            # 小数3桁補正
            if "." in v:

                left, right = v.split(".")

                # 1.4 → 1.400
                if len(right) == 1:
                    right = right + "00"

                # 1.41 → 1.410
                elif len(right) == 2:
                    right = right + "0"

                v = left + "." + right

            num = float(v)

            # 幅の範囲だけ採用
            if 1.3 <= num <= 1.5:
                values.append(num)

        print(filename, "→", values)

        # =========================
        # 写真名から測点・項目名取得
        # =========================

        # 例:
        # GE-001_幅.jpg
        # GE-002_厚さ.jpg

        name_only = os.path.splitext(filename)[0]

        parts = name_only.split("_")

        # 測点名
        if len(parts) >= 1:
            point_name = parts[0]
        else:
            point_name = f"GE-{len(csv_data)+1}"

        # 測定項目名
        if len(parts) >= 2:
            measurement_item = parts[1]
        else:
            measurement_item = "幅"

        # CSV追加
        for value in values:

            csv_data.append([
                point_name,
                measurement_item,
                f"{value:.3f}"
            ])

# =========================
# CSV保存
# =========================

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
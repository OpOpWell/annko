from PIL import Image
import pytesseract
import re
from openpyxl import load_workbook

print("OCR → デキスパートExcel 自動入力開始")

# Tesseract
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# 画像
image_file = "LLEFT NNMBER.png"
# Excel
input_file = "sample.xlsx"
output_file = "完成_自動入力.xlsx"

# OCR
img = Image.open(image_file)

text = text = pytesseract.image_to_string(
    img,
    lang="eng",
    config="--psm 6 -c tessedit_char_whitelist=0123456789."
)

print("OCR結果")
print(text)

# 4桁数字だけ抽出 例: 1404
raw_values = re.findall(r"[0-9]?\.[0-9]{2,3}|[0-9]{4}", text)
print("抽出数値")
print(raw_values)

values = []

for v in raw_values:
    if v.startswith("."):
        v = "1" + v

    elif "." not in v and len(v) == 4:
        v = str(float(v) / 1000)

    values.append(float(v))

print("復元値")
print(values)

# Excel入力
wb = load_workbook(input_file)
ws = wb["測定結果表"]

start_row = 10
target_col = "C"

for i, value in enumerate(values):
    row = start_row + i * 2
    ws[f"{target_col}{row}"] = value
    print(f"{target_col}{row} = {value}")

wb.save(output_file)

print("保存しました:", output_file)

img = Image.open(image_file)

# 白黒化
img = img.convert("L")

# 二値化
img = img.point(lambda x: 0 if x < 180 else 255)
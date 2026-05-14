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
image_file = "number.png.jpg"

# Excel
input_file = "sample.xlsx"
output_file = "完成_自動入力.xlsx"

# OCR
img = Image.open(image_file)

text = pytesseract.image_to_string(
    img,
    lang="eng",
    config="--psm 6"
)

print("OCR結果")
print(text)

# 4桁数字だけ抽出 例: 1404
nums = re.findall(r"\d{4}", text)

print("抽出数値")
print(nums)

# 1404 → 1.404
values = [float(x) / 1000 for x in nums]

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
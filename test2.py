from PIL import Image
import pytesseract
import re

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

img = Image.open("number.png.jpg")

text = pytesseract.image_to_string(
    img,
    lang="eng",
    config="--psm 6"
)

print("OCR結果")
print(text)

nums = re.findall(r"\d{4}", text)

print("数値")
print(nums)

values = [float(x) / 1000 for x in nums]

print("復元")
print(values)

import pandas as pd

df = pd.DataFrame(values, columns=["測定値"])

df.to_excel("ocr_result.xlsx", index=False)

print("Excel保存完了")
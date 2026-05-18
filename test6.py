import cv2
from PIL import Image
import pytesseract

# これ追加
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# 画像読込
img = cv2.imread("number.png.jpg")

# 2倍拡大
big = cv2.resize(
    img,
    None,
    fx=2,
    fy=2
)

# 保存
cv2.imwrite("big.png", big)

print("拡大完了")

# OCR
img2 = Image.open("big.png")

text = pytesseract.image_to_string(
    img2,
    lang="eng",
    config="--psm 6"
)

print(text)
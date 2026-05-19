from openai import OpenAI
import os
import glob
import shutil
import base64
import json
import re
import cv2
import subprocess

client = OpenAI()

# =========================
# 設定
# =========================

INPUT_FOLDER = r"C:\Users\user\foolder\634\images_all"

OUTPUT_FOLDER = r"C:\Users\user\foolder\634\photo_sorted"

AUTO_RUN_OCR = True

ANKO_SCRIPT = r"C:\Users\user\foolder\杏子\杏子_cli.py"

USE_MEASUREMENT_PHOTO = True
USE_WORK_PHOTO = True
USE_BOARD_PHOTO = True
USE_BLUR_CHECK = True

BLUR_LIMIT = 120

# =========================
# 出力フォルダ
# =========================

MEASUREMENT_FOLDER = os.path.join(OUTPUT_FOLDER, "出来形測定写真")
WORK_FOLDER = os.path.join(OUTPUT_FOLDER, "作業風景")
BOARD_FOLDER = os.path.join(OUTPUT_FOLDER, "黒板写真")
CHECK_FOLDER = os.path.join(OUTPUT_FOLDER, "要確認")
NG_FOLDER = os.path.join(OUTPUT_FOLDER, "除外")

for folder in [
    MEASUREMENT_FOLDER,
    WORK_FOLDER,
    BOARD_FOLDER,
    CHECK_FOLDER,
    NG_FOLDER
]:
    os.makedirs(folder, exist_ok=True)


def blur_score(image_path):
    img = cv2.imread(image_path)

    if img is None:
        return 0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    return cv2.Laplacian(gray, cv2.CV_64F).var()


def gpt_photo_check(image_path):

    with open(image_path, "rb") as f:
        base64_image = base64.b64encode(
            f.read()
        ).decode("utf-8")

    response = client.responses.create(
        model="gpt-4.1-mini",
        temperature=0,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": """
この写真を工事写真として分類してください。

分類候補:
- 出来形測定写真
- 作業風景
- 黒板写真
- 要確認
- 除外

判定ポイント:
- 測定表、手書き数字、田番、測点番号があれば「出来形測定写真」
- 作業員、重機、施工中の様子があれば「作業風景」
- 黒板が大きく写っていれば「黒板写真」
- 工事関係だが判断が難しければ「要確認」
- 関係ない、空、地面だけ、写真として使いにくい場合は「除外」

JSONのみ返してください。

形式:
{
  "category": "出来形測定写真",
  "reason": "測定表と手書き数字がある",
  "has_board": true,
  "has_numbers": true,
  "has_measurement_table": true,
  "has_worker": false,
  "has_machine": false,
  "useful": true
}
"""
                    },
                    {
                        "type": "input_image",
                        "image_url":
                        f"data:image/jpeg;base64,{base64_image}"
                    }
                ]
            }
        ]
    )

    text = response.output_text.strip()
    text = text.replace("```json", "")
    text = text.replace("```", "")

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        return {
            "category": "要確認",
            "reason": "JSON取得失敗",
            "useful": False
        }

    try:
        return json.loads(match.group())

    except:
        return {
            "category": "要確認",
            "reason": "JSON変換失敗",
            "useful": False
        }


def safe_copy(src, dst_folder):

    name = os.path.basename(src)

    dst = os.path.join(dst_folder, name)

    if os.path.exists(dst):

        base, ext = os.path.splitext(name)

        count = 1

        while True:

            new_name = f"{base}_{count}{ext}"

            dst = os.path.join(dst_folder, new_name)

            if not os.path.exists(dst):
                break

            count += 1

    shutil.copy2(src, dst)


def run_ocr():

    print()
    print("OCR自動接続開始")

    subprocess.run([
        r"C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe",
        ANKO_SCRIPT
    ])

    print("OCR自動接続完了")


def main():

        # 出力フォルダ初期化

    for folder in [
        MEASUREMENT_FOLDER,
        WORK_FOLDER,
        BOARD_FOLDER,
        CHECK_FOLDER,
        NG_FOLDER
    ]:

        files = glob.glob(
            os.path.join(folder, "*")
        )

        for file in files:
            os.remove(file)

    print("AI写真整理開始")

    image_files = [
        f for f in os.listdir(INPUT_FOLDER)
        if f.lower().endswith(
            (
                ".jpg",
                ".jpeg",
                ".png"
            )
        )
    ]

    print(f"対象枚数: {len(image_files)}")

    for image_name in image_files:

        image_path = os.path.join(INPUT_FOLDER, image_name)

        print()
        print(f"処理中: {image_name}")

        if USE_BLUR_CHECK:

            score = blur_score(image_path)

            print(f"ブレスコア: {score:.2f}")

            if score < BLUR_LIMIT:

                print("保存先: 除外（ピンボケ）")

                safe_copy(image_path, NG_FOLDER)

                continue

        result = gpt_photo_check(image_path)

        category = result.get("category", "要確認")
        reason = result.get("reason", "")
        has_board = result.get("has_board", False)
        has_numbers = result.get("has_numbers", False)
        has_measurement_table = result.get("has_measurement_table", False)
        has_worker = result.get("has_worker", False)
        has_machine = result.get("has_machine", False)

        print(f"分類: {category}")
        print(f"理由: {reason}")
        print(f"黒板: {has_board}")
        print(f"数字: {has_numbers}")
        print(f"測定表: {has_measurement_table}")
        print(f"作業員: {has_worker}")
        print(f"重機: {has_machine}")

        if (
            category == "出来形測定写真"
            and USE_MEASUREMENT_PHOTO
        ):

            print("保存先: 出来形測定写真")

            safe_copy(image_path, MEASUREMENT_FOLDER)

        elif (
            category == "作業風景"
            and USE_WORK_PHOTO
        ):

            print("保存先: 作業風景")

            safe_copy(image_path, WORK_FOLDER)

        elif (
            category == "黒板写真"
            and USE_BOARD_PHOTO
        ):

            print("保存先: 黒板写真")

            safe_copy(image_path, BOARD_FOLDER)

        elif category == "除外":

            print("保存先: 除外")

            safe_copy(image_path, NG_FOLDER)

        else:

            print("保存先: 要確認")

            safe_copy(image_path, CHECK_FOLDER)

    print()
    print("AI写真整理完了")
    print(f"出力先: {OUTPUT_FOLDER}")

    if AUTO_RUN_OCR:
        run_ocr()


main()
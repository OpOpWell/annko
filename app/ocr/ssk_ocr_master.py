from openai import OpenAI
import base64
import os
import csv
import re
import json

client = OpenAI()


MASTER_TABAN_CSV = "master_taban.csv"
MASTER_ITEM_CSV = "master_items.csv"


def load_expected_counts(master_csv):
    """田番マスタCSVから、田番ごとの測点数を読み込む。"""
    expected_counts = {}

    if not os.path.exists(master_csv):
        raise FileNotFoundError(f"田番マスタがありません: {master_csv}")

    with open(master_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            taban = str(row.get("田番", "")).strip()
            count_text = str(row.get("測点数", "")).strip()

            if taban == "":
                continue

            try:
                expected_counts[taban] = int(count_text)
            except:
                expected_counts[taban] = 0

    return expected_counts


def load_allowed_items(master_csv):
    """測定項目マスタCSVから、許可する測定項目を読み込む。"""
    allowed_items = []

    if not os.path.exists(master_csv):
        raise FileNotFoundError(f"測定項目マスタがありません: {master_csv}")

    with open(master_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            item = str(row.get("測定項目", "")).strip()

            if item and item not in allowed_items:
                allowed_items.append(item)

    return allowed_items


def make_item_prompt_text(allowed_items):
    """GPTに渡す測定項目候補の文章を、マスタから作る。"""
    return "\n".join([f"- {item}" for item in allowed_items])


def to_mm_text(value):
    try:
        return str(int(round(float(value) * 1000)))
    except:
        return ""


def gpt_ocr(image_path, model_name, log, allowed_items):

    item_prompt_text = make_item_prompt_text(allowed_items)

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
                        "text": f"""
このSSK出来形測定写真から情報を読み取ってください。

重要:
- 田番は上部の「田番」欄の数字
- 大きく丸で書かれた手書き数字は田番にしない

測定項目は次の候補から選択してください。

{item_prompt_text}

必ず上記候補から選択すること。
候補に無い場合は「不明」を返すこと。

読む項目:
- 田番
- 工種
- 測定項目
- 面積
- 測定基準
- 規格値
- 社内目標値
- 平均値
- Xmax
- Xmin
- 番号と手書き実測値

条件:
- 番号と手書き実測値を対応させる
- 空欄は無視
- 実測値は1.300〜1.600程度
- 実測値は小数3桁
- JSONのみ返す
- 説明不要
- 推測しない
- 読めない値は空文字または除外

返却形式:
{{
  "taban": "19",
  "work_type": "整地工",
  "measurement_item": "均平度",
  "area": "9750㎡",
  "standard": "10a当たり3点以上",
  "spec_value": "±50mm",
  "target_value": "±40mm",
  "average": "1.410",
  "xmax": "1.400",
  "xmin": "1.421",
  "values": [
    {{"no": 1, "value": 1.418}},
    {{"no": 2, "value": 1.400}}
  ]
}}
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

    match_json = re.search(r"\{.*\}", result_text, re.DOTALL)

    if not match_json:
        log("JSONが見つかりません")
        return {}

    try:
        return json.loads(match_json.group())
    except Exception as e:
        log("JSON変換失敗")
        log(e)
        return {}


def run_ocr(image_folder, output_folder):

    os.makedirs(output_folder, exist_ok=True)

    expected_counts = load_expected_counts(MASTER_TABAN_CSV)
    allowed_items = load_allowed_items(MASTER_ITEM_CSV)

    csv_by_taban = {}
    meta_by_taban = {}
    log_lines = []

    def log(message):
        print(message)
        log_lines.append(str(message))

    log("田番マスタ読込: " + str(expected_counts))
    log("測定項目マスタ読込: " + ", ".join(allowed_items))

    image_files = sorted([
        f for f in os.listdir(image_folder)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ])

    total_images = len(image_files)

    if total_images == 0:
        log("画像がありません")
        return

    log("SSK写真 OCR → デキスパートCSV 自動作成開始")

    for index, image_name in enumerate(image_files, start=1):

        image_path = os.path.join(image_folder, image_name)

        log(f"\n処理中: {image_path}")

        result = gpt_ocr(image_path, "gpt-4.1-mini", log, allowed_items)

        taban = str(result.get("taban", "")).strip()

        work_type = str(result.get("work_type", "整地工")).strip()

        measurement_item = str(
            result.get("measurement_item", "不明")
        ).strip()

        if measurement_item not in allowed_items:
            measurement_item = "不明"

        design_value_raw = str(result.get("average", "")).strip()
        design_value = to_mm_text(design_value_raw)

        if work_type == "":
            work_type = "整地工"

        if taban not in expected_counts:
            taban = "未分類"

        if taban not in meta_by_taban:
            meta_by_taban[taban] = {
                "工種": work_type,
                "測定項目": measurement_item,
                "面積": result.get("area", ""),
                "測定基準": result.get("standard", ""),
                "規格値": result.get("spec_value", ""),
                "社内目標値": result.get("target_value", ""),
                "設計値": design_value,
                "Xmax": result.get("xmax", ""),
                "Xmin": result.get("xmin", ""),
            }

        values = result.get("values", [])
        value_dict = {}

        for item in values:
            try:
                no = int(item["no"])
                value = float(item["value"])
                value_dict[no] = value
            except:
                pass

        total_count = expected_counts.get(taban, 0)

        missing_no = []

        for no in range(1, total_count + 1):
            if no not in value_dict:
                missing_no.append(no)

        if missing_no:

            log("\n未読No検出")
            log(missing_no)
            log("\n4.1で再OCR実施")

            retry_result = gpt_ocr(image_path, "gpt-4.1", log, allowed_items)

            for item in retry_result.get("values", []):
                try:
                    no = int(item["no"])
                    value = float(item["value"])

                    if no not in value_dict:
                        value_dict[no] = value
                except:
                    pass

        if taban not in csv_by_taban:
            csv_by_taban[taban] = []

        for no in range(1, total_count + 1):

            point_name = f"No.{no}"

            if no in value_dict:
                value_text = to_mm_text(value_dict[no])
            else:
                value_text = ""

            csv_by_taban[taban].append([
                point_name,
                f"{work_type}田番{taban}",
                measurement_item,
                design_value,
                value_text
            ])

    for taban, rows in csv_by_taban.items():

        missing_no = []

        for row in rows:
            if row[4] == "":
                missing_no.append(row[0])

        if missing_no:
            log(f"\n未読あり: 田番{taban}")
            log("未読No: " + ", ".join(missing_no))
        else:
            log(f"\n未読なし: 田番{taban}")

        output_csv = os.path.join(output_folder, f"田番{taban}.csv")

        with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)

            writer.writerow([
                "測点",
                "工種名",
                "測定項目",
                "設計値",
                "実測値1"
            ])

            writer.writerows(rows)

        log(f"CSV保存完了: {output_csv}")

    meta_csv = os.path.join(output_folder, "測定情報.csv")

    with open(meta_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        writer.writerow([
            "田番",
            "工種",
            "測定項目",
            "面積",
            "測定基準",
            "規格値",
            "社内目標値",
            "設計値",
            "Xmax",
            "Xmin"
        ])

        for taban, meta in meta_by_taban.items():
            writer.writerow([
                taban,
                meta.get("工種", ""),
                meta.get("測定項目", ""),
                meta.get("面積", ""),
                meta.get("測定基準", ""),
                meta.get("規格値", ""),
                meta.get("社内目標値", ""),
                meta.get("設計値", ""),
                meta.get("Xmax", ""),
                meta.get("Xmin", "")
            ])

    log_path = os.path.join(output_folder, "ssk_ocr_log.txt")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    log("\n全部完了")
    log(f"測定情報CSV保存完了: {meta_csv}")
    log(f"ログ保存完了: {log_path}")


image_folder = "hhh"
output_folder = "zzz"

run_ocr(
    image_folder,
    output_folder
)

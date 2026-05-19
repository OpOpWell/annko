# ocr_checker.py

def check_ocr_result(result, taban_master=None):
    """
    GPT OCR結果の信頼度チェック

    result 例:
    {
      "taban": "9",
      "measurement_item": "均平度",
      "average": "1.452",
      "xmax": "1.446",
      "xmin": "1.465",
      "values": [
        {"no": 1, "value": 1.446}
      ]
    }
    """

    warnings = []
    score = 100

    taban = str(result.get("taban", "")).strip()
    item = str(result.get("measurement_item", "")).strip()
    values = result.get("values", [])

    # =========================
    # 基本項目チェック
    # =========================

    if not taban:
        warnings.append("田番が読めていません")
        score -= 30

    if not item:
        warnings.append("測定項目が読めていません")
        score -= 20

    if not values:
        warnings.append("測定値が1つも読めていません")
        score -= 50

    # =========================
    # No / 値チェック
    # =========================

    nos = []
    nums = []

    for row in values:
        no = row.get("no")
        value = row.get("value")

        if no is None:
            warnings.append("Noなしの測定値があります")
            score -= 10
            continue

        if value is None:
            warnings.append(f"No.{no} の値が空です")
            score -= 10
            continue

        try:
            no = int(no)
            value = float(value)
        except:
            warnings.append(f"No.{no} の値が数値ではありません: {value}")
            score -= 15
            continue

        nos.append(no)
        nums.append(value)

        # 均平度想定のざっくり異常値
        if value < 0.5 or value > 3.0:
            warnings.append(f"No.{no} の値が異常かもしれません: {value}")
            score -= 20

    # =========================
    # No重複
    # =========================

    duplicated = sorted([
        no for no in set(nos)
        if nos.count(no) >= 2
    ])

    if duplicated:
        warnings.append(f"Noが重複しています: {duplicated}")
        score -= 25

    # =========================
    # No抜け
    # =========================

    if nos:
        missing = [
            n for n in range(1, max(nos) + 1)
            if n not in nos
        ]

        if missing:
            warnings.append(f"No抜けがあります: {missing}")
            score -= 15

    # =========================
    # 田番マスタとの点数比較
    # =========================

    if taban_master and taban in taban_master:

        expected_count = int(taban_master[taban])
        actual_count = len(nums)

        if expected_count != actual_count:
            warnings.append(
                f"田番{taban}の測点数が不一致です。予定:{expected_count}点 / OCR:{actual_count}点"
            )
            score -= 30

    # =========================
    # average / xmax / xmin チェック
    # =========================

    if nums:
        calc_avg = round(sum(nums) / len(nums), 3)
        calc_max = round(max(nums), 3)
        calc_min = round(min(nums), 3)

        average = result.get("average")
        xmax = result.get("xmax")
        xmin = result.get("xmin")

        try:
            if average not in [None, ""]:
                average = round(float(average), 3)

                if abs(calc_avg - average) >= 0.005:
                    warnings.append(
                        f"平均値が合いません。OCR:{average} / 計算:{calc_avg}"
                    )
                    score -= 20
        except:
            warnings.append(f"平均値が数値ではありません: {average}")
            score -= 10

        try:
            if xmax not in [None, ""]:
                xmax = round(float(xmax), 3)

                if xmax != calc_max:
                    warnings.append(
                        f"最大値が合いません。OCR:{xmax} / 計算:{calc_max}"
                    )
                    score -= 15
        except:
            warnings.append(f"最大値が数値ではありません: {xmax}")
            score -= 10

        try:
            if xmin not in [None, ""]:
                xmin = round(float(xmin), 3)

                if xmin != calc_min:
                    warnings.append(
                        f"最小値が合いません。OCR:{xmin} / 計算:{calc_min}"
                    )
                    score -= 15
        except:
            warnings.append(f"最小値が数値ではありません: {xmin}")
            score -= 10

    # =========================
    # 判定
    # =========================

    if score >= 90:
        level = "OK"
    elif score >= 70:
        level = "要確認"
    else:
        level = "危険"

    if score < 0:
        score = 0

    return {
        "score": score,
        "level": level,
        "warnings": warnings
    }



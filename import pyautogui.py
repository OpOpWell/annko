import pyautogui
import time
import csv

csv_file = "ssk_output/田番19.csv"

print("5秒以内にデキスパートの最初の入力セルへカーソルを置いてください")
time.sleep(5)

with open(csv_file, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)

    for row in reader:
        actual_value = row["実測値"]

        if actual_value == "":
            continue

        # 設計値
        pyautogui.write("1.410")
        pyautogui.press("tab")

        # 実測値
        pyautogui.write(actual_value)
        pyautogui.press("tab")

        # 次の行へ移動
        pyautogui.press("enter")
        time.sleep(0.1)

print("入力完了")

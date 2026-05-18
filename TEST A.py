import pyautogui
import pyperclip
import time

print("5秒以内に工種名欄へマウスを置いてください")

time.sleep(5)

# マウス位置取得
pos = pyautogui.position()

print("取得座標")
print(pos)

# ----------------------------
# 入力内容
# ----------------------------

koumei = "整地工"
shubetsu = "整地仕上げ"
saibetsu = "ほ場整備工(表土扱い)(標準区画0.3ha以上)"

# ----------------------------
# 工種名
# ----------------------------

pyautogui.click(pos.x, pos.y)

pyautogui.hotkey("ctrl", "a")

pyperclip.copy(koumei)

pyautogui.hotkey("ctrl", "v")

time.sleep(0.5)

# ----------------------------
# 種別名
# ----------------------------

pyautogui.press("tab")

pyautogui.hotkey("ctrl", "a")

pyperclip.copy(shubetsu)

pyautogui.hotkey("ctrl", "v")

time.sleep(0.5)

# ----------------------------
# 細別名
# ----------------------------

pyautogui.press("tab")

pyautogui.hotkey("ctrl", "a")

pyperclip.copy(saibetsu)

pyautogui.hotkey("ctrl", "v")

print("入力完了")

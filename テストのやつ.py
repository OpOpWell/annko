import os
import glob
import shutil

SOURCE = r"C:\Users\user\foolder\634\photo_sorted"
DEST = r"C:\Users\user\foolder\634\images_all"

folders = [
    "出来形測定写真",
    "作業風景",
    "黒板写真",
    "要確認",
    "除外"
]

for folder in folders:

    path = os.path.join(SOURCE, folder)

    files = glob.glob(os.path.join(path, "*"))

    for file in files:

        name = os.path.basename(file)

        dst = os.path.join(DEST, name)

        shutil.move(file, dst)

        print(f"戻した: {name}")

print("全部戻しました")
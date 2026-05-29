# 杏子 - 建設写真AI整理システム

## 概要

建設現場写真をAIで分類し、
電子納品用PHOTO.XMLおよび
デキスパート連携CSVを自動生成する
Python業務支援ツールです。

黒板OCR・写真内容解析・現場別masterを組み合わせ、
採用写真・CHECK写真・除外写真へ自動分類します。

さらに、
出来形管理写真から実測値OCRを行い、
田番別CSVを自動生成します。

---

## 主な機能

- 工事写真AI分類
- PHOTO.XML自動生成
- CHECK写真分離
- 重複写真除外
- 実測値OCR
- 田番別CSV生成
- 未読No検出
- GPT-4.1再OCR
- GUI操作対応

---

## 使用技術

- Python
- OpenAI API
- Tkinter
- CSV
- XML
- OCR

---

## フォルダ構成

```text
杏子/
├─ 杏子統合GUI.py
├─ 杏子526ees.py
├─ 杏子子_gui.py
├─ config.yml
├─ master_project.csv
├─ selected_photos/
└─ csv_output/
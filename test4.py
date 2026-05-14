print("test4開始")

from openpyxl import load_workbook

input_file = "sample.xlsx"
output_file = "完成_デキスパート入力.xlsx"

values = [
    1.418, 1.400, 1.409, 1.409, 1.415,
    1.419, 1.421, 1.412, 1.403, 1.403,
]

wb = load_workbook(input_file)
ws = wb["測定結果表"]

def writable_cell(ws, cell_address):
    for merged_range in ws.merged_cells.ranges:
        if cell_address in merged_range:
            return merged_range.start_cell.coordinate
    return cell_address

start_row = 10
target_col = "C"

for i, value in enumerate(values):
    cell = f"{target_col}{start_row + i * 2}"
    write_cell = writable_cell(ws, cell)
    print(cell, "→", write_cell, value)
    ws[write_cell] = value

wb.save(output_file)

print("保存しました:", output_file)
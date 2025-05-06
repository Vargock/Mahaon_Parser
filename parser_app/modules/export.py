import csv
import openpyxl
from io import BytesIO, StringIO
from flask import Response


def export_to_csv(data, columns, filename):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in data:
        writer.writerow(row)
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"},
    )


def export_to_xlsx(data, columns, filename):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(columns)
    for row in data:
        ws.append(row)
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment;filename={filename}"},
    )

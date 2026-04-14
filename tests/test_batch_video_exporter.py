import pytest
from timemachine_video_export.batch_video_exporter import BatchVideoExporter

export_sheet_name = "Batch video exports test sheet"

def test_export_first_video():
    exporter = BatchVideoExporter(export_sheet_name)
    exporter.export_video(exporter.df.iloc[0])

def test_export_second_video():
    exporter = BatchVideoExporter(export_sheet_name)
    exporter.export_video(exporter.df.iloc[1])

def test_export_third_video():
    # takes 143 seconds for 1h of video
    # 214 with 5 chunk threads
    exporter = BatchVideoExporter(export_sheet_name)
    exporter.export_video(exporter.df.iloc[2])

def test_export_shenango_avalon_accan_video():
    exporter = BatchVideoExporter(export_sheet_name)
    exporter.export_video(exporter.df.iloc[4])

def test_export_shenango_bellevue_achd_video():
    exporter = BatchVideoExporter(export_sheet_name)
    exporter.export_video(exporter.df.iloc[5])

# def test_export_fourth_video():
#     exporter = BatchVideoExporter("Natisha BreatheCam video exports")
#     exporter.export_video(exporter.df.iloc[3])

def test_export_next_video():
    exporter = BatchVideoExporter("Natisha Breathe Cam video exports")
    exporter.export_next()

def test_noop():
    print("hello from test_noop")

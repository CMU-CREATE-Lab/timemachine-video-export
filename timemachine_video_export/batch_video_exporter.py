from functools import cache
import os
import sys
import dateutil
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime
import argparse

import pytz

from .stopwatch import Stopwatch
from .video_renderer import render_video_site

# Configuration via environment variables
BREATHECAM_SECRETS_PATH = os.environ.get('BREATHECAM_SECRETS_PATH',
                                          os.path.join(os.getcwd(), 'secrets'))
BREATHECAM_EXPORT_DIR = os.environ.get('BREATHECAM_EXPORT_DIR',
                                        os.path.join(os.getcwd(), 'exports'))

print(f"{datetime.datetime.now()} Starting batch_video_exporter.py with Python {sys.version} ")

@cache
def client():
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials_file = os.path.join(BREATHECAM_SECRETS_PATH,
                                    "createlab-breathecam-bulk-video-generation-58427be4b55f.json")
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
    client = gspread.authorize(creds)
    return client

required_columns = ["Site", "Date", "Begin time", "End time", "Video", "Notes"]
first_col = "A"
last_col = chr(ord("A") + len(required_columns) - 1)
# Use the configured export directory
export_directory = BREATHECAM_EXPORT_DIR

class BatchVideoExporter:
    def __init__(self, spreadsheet_name):
        self.spreadsheet_name = spreadsheet_name
        self.df = self.read_spreadsheet(spreadsheet_name)

    def read_spreadsheet(self, spreadsheet_name):
        # Open the main sheet in this spreadsheet.  Complain if there's more than one sheet
        spreadsheet = client().open(spreadsheet_name)
        worksheets = spreadsheet.worksheets()
        if len(worksheets) > 1:
            raise ValueError(f"Expected only one sheet in {spreadsheet_name}, but found {len(worksheets)} sheets")
        worksheet = worksheets[0]

        # Get all tables in the worksheet    df = pd.DataFrame(data[1:], columns=data[0])
        rows = worksheet.get(f"{first_col}:{last_col}")

        header = rows[0]
        data_rows = rows[1:]
        assert header == required_columns

        df = pd.DataFrame(data_rows, columns=header)
        # None in Video or Notes columns should be empty string instead
        df["Video"] = df["Video"].fillna("")
        df["Notes"] = df["Notes"].fillna("")

        return df

    def export_video(self, row):
        site = row["Site"]
        # Parse as datetime.date
        date = dateutil.parser.parse(row["Date"]).date()
        # Parse as datetime.time
        begin_time = dateutil.parser.parse(row["Begin time"]).time()
        end_time = dateutil.parser.parse(row["End time"]).time()
        video = row["Video"]
        notes = row["Notes"]

        et = pytz.timezone("America/New_York")
        begin_datetime = et.localize(datetime.datetime.combine(date, begin_time))
        end_datetime = et.localize(datetime.datetime.combine(date, end_time))

        # Don't create exports directory since we need to symlink it to the web server exports directory
        #os.makedirs(export_directory, exist_ok=True)
        # Create temporary file in exports directory
        export_filename = site
        export_filename += f"-{begin_datetime.strftime('%Y%m%d-%H%M%S')}"
        export_filename += f"-{end_datetime.strftime('%H%M%S')}-et"
        export_filename += ".mp4"
        export_path = os.path.join(export_directory, export_filename)

        row_idx = row.name
        start_time = datetime.datetime.now(pytz.UTC).astimezone()
        self.update_spreadsheet_cell(row_idx, f"Started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            with Stopwatch(f"Exporting video for {site} from {begin_datetime} to {end_datetime}"):
                render_video_site(site, begin_datetime, end_datetime, export_path, use_original_full_res=True)
                print(f"BatchVideoExporter: Exported video to {export_path} ({os.path.getsize(export_path)/1e6:.06f} MB)")

            web_export_prefix = "https://videos.breathecam.org/"

            video_url = web_export_prefix + os.path.basename(export_path)
            video_link = f'=hyperlink("{video_url}", "{os.path.basename(export_path)}")'
            self.update_spreadsheet_cell(row_idx, video_link)
            return export_path

        except Exception as e:
            self.update_spreadsheet_cell(row_idx, f"Error: {str(e)}")
            raise

    def export_next(self):
        """Export the next video in the queue"""
        row = self.find_next_row()
        if row is None:
            print("No more videos to export")
            return False
        self.export_video(row)
        return True

    def find_next_row(self):
        """Find the first row where Video column is empty and all required fields are present"""
        empty_video_mask = self.df["Video"] == ""
        valid_fields_mask = (
            self.df["Site"].notna() &
            self.df["Date"].notna() &
            self.df["Begin time"].notna() &
            self.df["End time"].notna()
        )
        eligible_rows = self.df[empty_video_mask & valid_fields_mask]
        if len(eligible_rows) == 0:
            return None
        return eligible_rows.iloc[0]

    def update_spreadsheet_cell(self, row_idx, value):
        """Update the Video cell for the given row, but verify row contents first"""
        worksheet = client().open(self.spreadsheet_name).worksheets()[0]
        # Spreadsheet rows are 1-based and include header
        sheet_row = row_idx + 2

        # Read the entire row to verify contents
        row_data = worksheet.row_values(sheet_row)
        expected_row = self.df.iloc[row_idx]

        # Verify key fields match
        if (row_data[0] != expected_row["Site"] or
            row_data[1] != expected_row["Date"] or
            row_data[2] != expected_row["Begin time"] or
            row_data[3] != expected_row["End time"]):
            raise ValueError(
                f"Row contents changed while processing! Expected:\n"
                f"Site: {expected_row['Site']}, Date: {expected_row['Date']}, "
                f"Begin: {expected_row['Begin time']}, End: {expected_row['End time']}\n"
                f"But found:\n"
                f"Site: {row_data[0]}, Date: {row_data[1]}, "
                f"Begin: {row_data[2]}, End: {row_data[3]}"
            )

        # If verification passes, update the cell
        # Update using row/col numbers instead of A1 notation
        worksheet.update_cell(sheet_row, 5, value)  # 5 is the column number for "Video" (E)
        # Update local dataframe
        self.df.at[row_idx, "Video"] = value



def main():
    parser = argparse.ArgumentParser(description='Batch Video Exporter for Breathecam')
    parser.add_argument('spreadsheet_name', help='Name of the Google Spreadsheet to process')
    parser.add_argument('--export-next', action='store_true',
                       help='Export the next pending video from the spreadsheet')

    args = parser.parse_args()

    exporter = BatchVideoExporter(args.spreadsheet_name)

    if args.export_next:
        try:
            if exporter.export_next():
                print("Successfully exported next video")
                return 0
            else:
                print("No videos pending export")
                return 1
        except Exception as e:
            print(f"Error exporting video: {str(e)}")
            # Show traceback
            import traceback
            traceback.print_exc()
            return 2
    else:
        parser.print_help()
        return 1

if __name__ == '__main__':
    exit(main())

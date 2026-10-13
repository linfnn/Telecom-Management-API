import os
import re
import sys
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_NAME = "QuanLyMangVienThong"
SQL_FILE = BASE_DIR / "MSSQL" / "SQL_total_local.sql"


class SQLConnection:
    def __init__(self):
        load_dotenv(BASE_DIR / ".env")

        self.server = os.getenv("DB_HOST")
        self.port = os.getenv("DB_PORT")
        self.username = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")
        self.database = os.getenv("DB_NAME")
        self.connection = None
        self.cursor = None

        missing = [
            name
            for name, value in (
                ("DB_HOST", self.server),
                ("DB_PORT", self.port),
                ("DB_USER", self.username),
                ("DB_PASSWORD", self.password),
                ("DB_NAME", self.database),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"Thiếu cấu hình trong .env: {', '.join(missing)}"
            )

        if self.database != DATABASE_NAME:
            raise ValueError(
                f"SQL script tạo database '{DATABASE_NAME}'. "
                f"Hãy đặt DB_NAME={DATABASE_NAME} trong .env."
            )

    @staticmethod
    def _odbc_value(value):
        return "{" + value.replace("}", "}}") + "}"

    def connect(self):
        server = f"{self.server},{self.port}"
        connection_string = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={self._odbc_value(server)};"
            f"DATABASE={self._odbc_value('master')};"
            f"UID={self._odbc_value(self.username)};"
            f"PWD={self._odbc_value(self.password)};"
            "Encrypt=no;"
            "TrustServerCertificate=yes;"
        )
        self.connection = pyodbc.connect(connection_string, autocommit=True)
        self.cursor = self.connection.cursor()
        print(f"Đã kết nối SQL Server: {server}")

    @staticmethod
    def read_sql_file(filepath):
        raw = filepath.read_bytes()
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16")
        return raw.decode("utf-8-sig")

    @staticmethod
    def split_batches(sql):
        return re.split(r"(?im)^\s*GO\s*(?:--.*)?$", sql)

    def run(self):
        if not SQL_FILE.is_file():
            raise FileNotFoundError(f"Không tìm thấy SQL script: {SQL_FILE}")

        batches = [
            batch.strip()
            for batch in self.split_batches(self.read_sql_file(SQL_FILE))
            if batch.strip()
        ]
        self.connect()
        try:
            for index, batch in enumerate(batches, start=1):
                try:
                    self.cursor.execute(batch)
                except pyodbc.Error as exc:
                    raise RuntimeError(
                        f"Lỗi khi chạy batch {index}/{len(batches)} "
                        f"của {SQL_FILE.name}: {exc}"
                    ) from exc
                print(f"Đã chạy batch {index}/{len(batches)}")
        finally:
            self.close()

        print(
            f"Khởi tạo database '{DATABASE_NAME}' hoàn tất "
            f"({len(batches)} batch SQL)."
        )

    def close(self):
        if self.cursor is not None:
            self.cursor.close()
        if self.connection is not None:
            self.connection.close()


if __name__ == "__main__":
    try:
        SQLConnection().run()
    except Exception as exc:
        print(f"Không thể khởi tạo database: {exc}", file=sys.stderr)
        sys.exit(1)

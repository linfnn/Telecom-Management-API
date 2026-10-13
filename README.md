# QLMVT Web API

API quản lý mạng viễn thông: nhân viên, thiết bị, liên kết, chỉ số hiệu suất,
lỗ hổng bảo mật, nhật ký lỗi và báo cáo. Backend được xây dựng bằng Django REST
Framework; dữ liệu nghiệp vụ lưu trong Microsoft SQL Server. Các model nghiệp
vụ dùng `managed = False`, vì vậy Django không tạo schema nghiệp vụ: schema và
các SQL object được cung cấp trong `MSSQL/SQL_total_local.sql`.

## Công nghệ

- Python 3.12+ và Django 6.1.
- Django REST Framework, Simple JWT (access token 1 giờ, refresh token 7 ngày).
- Microsoft SQL Server; kết nối từ Python qua `mssql-django`, `pyodbc` và
  Microsoft ODBC Driver 18 for SQL Server.
- OpenAPI 3 / Swagger UI.
- Database nghiệp vụ gồm các bảng `NhanVien`, `ThietBi`, `LienKet`,
  `ChiSoHieuSuat`, `LoHong`, `NhatKyLoi`; Django còn dùng các bảng auth,
  session, token blacklist và `api_useraccount`.

## Yêu cầu

- Python 3.12 trở lên.
- Microsoft SQL Server tương thích với database backup/schema. Script SQL đi
  kèm đặt compatibility level 170; nên dùng SQL Server 2025 trở lên.
- Microsoft ODBC Driver 18 for SQL Server. Cài driver riêng với package Python:
  - Windows: cài Microsoft ODBC Driver 18 for SQL Server.
  - macOS/Homebrew:

    ```bash
    brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
    brew update
    HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql18
    ```

    Nếu máy chưa có Homebrew, cài Homebrew trước theo hướng dẫn chính thức.
- macOS không chạy SQL Server native. Có thể dùng Docker Desktop để chạy SQL
  Server Linux, hoặc kết nối tới một SQL Server khác trong mạng. Container SQL
  Server Linux cần kiến trúc được SQL Server hỗ trợ; trên Apple Silicon có thể
  cần máy ảo/host x86-64.

## Cài đặt và chạy

### 1. Clone và tạo Python virtual environment

```bash
git clone <URL_REPOSITORY>
cd QLMVT_Web_API
```

macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Nếu PowerShell chặn kích hoạt virtual environment, chạy lệnh sau trong
PowerShell với quyền phù hợp:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 2. Cài đặt và khởi động SQL Server

Trên Windows có thể cài SQL Server Developer và SSMS. Trên macOS, SQL Server
không chạy native; dùng Docker Desktop hoặc kết nối tới một SQL Server ở máy
khác.

#### SQL Server bằng Docker trên macOS

Ví dụ tạo container và volume để dữ liệu SQL Server được giữ lại khi container
dừng:

```bash
docker volume create qlmvt-sql-data
docker run --name qlmvt-sqlserver \
  -e ACCEPT_EULA=Y \
  -e MSSQL_PID=Developer \
  -e MSSQL_SA_PASSWORD='<SA_PASSWORD>' \
  -p 1433:1433 \
  -v qlmvt-sql-data:/var/opt/mssql \
  -d mcr.microsoft.com/mssql/server:2025-latest
```

Mật khẩu `sa` phải đáp ứng yêu cầu độ phức tạp của SQL Server; dùng cùng mật
khẩu trong `.env`. Chờ SQL Server sẵn sàng trước khi import/restore:

```bash
docker logs -f qlmvt-sqlserver
```

Nhấn `Ctrl+C` sau khi thấy log báo server sẵn sàng. Các lần chạy sau:

```bash
docker start qlmvt-sqlserver
```

Nếu tag image không có sẵn cho kiến trúc máy, dùng SQL Server trong máy ảo hoặc
trên một host tương thích rồi cấu hình `DB_HOST` và `DB_PORT` trỏ tới host đó.

### 3. Cấu hình `.env`

Tạo file riêng từ mẫu:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Điền kết nối SQL Server trong `.env`:

```dotenv
DB_NAME=QuanLyMangVienThong
DB_USER=sa
DB_PASSWORD=<SA_PASSWORD>
DB_HOST=127.0.0.1
DB_PORT=1433
IMPORT_EXPORT_FORMAT=qlmvt-json-import-export
IMPORT_EXPORT_VERSION=1
BACKUP_FORMAT=qlmvt-json-backup
BACKUP_VERSION=1
```

Các biến format/version là bắt buộc khi khởi động Django; giá trị mẫu cần được
giữ nguyên để tương thích với JSON export/backup của project. Khi Django chạy
trên máy host và SQL Server trong Docker publish cổng `1433`, dùng
`DB_HOST=127.0.0.1`. Nếu đổi cổng publish, đổi tương ứng `DB_PORT`. Không commit
`.env` hoặc thay mật khẩu mẫu bằng thông tin thật trong README.

### 4. Khởi tạo hoặc phục hồi database

Chọn **một** trong hai cách sau. Không chạy cách khởi tạo mới trên database đã
được restore hoặc database đang chứa dữ liệu cần giữ.

#### Cách 1: restore database backup

Lấy file `backups/QuanLyMangVienThong.bak` từ người quản lý dự án rồi làm theo
[hướng dẫn restore `.bak`](#phục-hồi-database-từ-file-bak). File backup không
được Git theo dõi nên không có trong bản clone; cần dùng SQL Server tương thích
với phiên bản tạo backup.

#### Cách 2: khởi tạo database mới bằng `MSSQLConnection.py`

Đảm bảo SQL Server đang chạy, đã cài dependencies ở bước 1, `.env` đã cấu hình
ở bước 3 và SQL Server hỗ trợ compatibility level 170 (SQL Server 2025 trở
lên). Chạy lệnh từ thư mục gốc project:

macOS/Linux:

```bash
python MSSQL/MSSQLConnection.py
```

Windows PowerShell:

```powershell
python .\MSSQL\MSSQLConnection.py
```

Runner đọc thông tin kết nối từ `.env`, kết nối database `master` bằng ODBC
Driver 18 rồi thực thi [`MSSQL/SQL_total_local.sql`](MSSQL/SQL_total_local.sql)
theo từng batch `GO`. Script tổng tạo database `QuanLyMangVienThong`, 6 bảng
nghiệp vụ, 2 database role, 3 function, 21 stored procedure và 11 trigger.
Script cũng nạp dữ liệu mẫu cho sáu bảng nghiệp vụ, nhưng **không tạo tài khoản
đăng nhập Django/API**; tài khoản mẫu trong README chỉ có sẵn khi dùng backup
chứa các tài khoản đó. Django tạo các bảng auth và `api_useraccount` ở bước
migrate bên dưới.

Đây là thao tác tạo database mới, không phải cập nhật/restore. Script không
ghi đè database cùng tên: nếu database đã tồn tại, lệnh tạo database sẽ báo
lỗi và runner dừng với mã lỗi. Không chạy lại để “làm mới” database có dữ liệu.
Các batch được thực thi riêng lẻ; nếu có lỗi ở batch sau, database có thể đã
được tạo một phần. Runner báo số batch gây lỗi. Chỉ xóa database khởi tạo dở
để chạy lại nếu đã xác nhận database đó không chứa dữ liệu cần giữ.
Nếu cần phục hồi dữ liệu có sẵn, dùng Cách 1. Các file trong
[`MSSQL/SQL_thuc_thi`](MSSQL/SQL_thuc_thi) là script object riêng, không dùng
thay cho quy trình khởi tạo đầy đủ này.

### 5. Khởi tạo Django và chạy API

Từ thư mục gốc, với virtual environment đã kích hoạt:

```bash
python manage.py migrate
python manage.py check
python manage.py runserver
```

`migrate` tạo các bảng hệ thống Django và `api_useraccount`; nó không tạo hoặc
thay đổi các bảng nghiệp vụ. Chỉ chạy `createsuperuser` nếu cần đăng nhập
trang Django Admin:

```bash
python manage.py createsuperuser
```

Server mặc định chạy ở `http://127.0.0.1:8000`; Django Admin ở
`http://127.0.0.1:8000/admin/`. Dừng server bằng `Ctrl+C`.

## Phục hồi database từ file `.bak`

File backup SQL Server là bản sao vật lý của database, khác với JSON backup của
API. Nó có thể chứa dữ liệu nghiệp vụ và tài khoản; chỉ dùng nếu file được
người quản lý dự án cung cấp và phù hợp phiên bản SQL Server đang chạy. Restore
database sẽ thay thế nội dung database đích, nên sao lưu dữ liệu hiện tại trước
khi tiếp tục.

### Windows / SSMS

1. Mở SSMS và kết nối tới SQL Server.
2. Chuột phải **Databases** → **Restore Database...**.
3. Chọn **Device** và file `QuanLyMangVienThong.bak`.
4. Đặt database đích là `QuanLyMangVienThong`. Nếu database đó đã tồn tại, chỉ
   chọn ghi đè khi chắc chắn có thể thay toàn bộ dữ liệu hiện tại.
5. Nếu SSMS báo không tìm thấy đường dẫn file dữ liệu cũ, mở trang **Files** và
   chọn đường dẫn đích mới cho các file data/log trước khi restore.

Có thể kiểm tra tính hợp lệ của file trước khi restore:

```powershell
sqlcmd -S localhost,1433 -U sa -P "<SA_PASSWORD>" -C -Q `
  "RESTORE VERIFYONLY FROM DISK = N'C:\path\QuanLyMangVienThong.bak'"
```

### macOS / SQL Server trong Docker

Đặt file `.bak` trên máy host rồi copy vào thư mục data có sẵn trong container:

```bash
docker cp backups/QuanLyMangVienThong.bak \
  qlmvt-sqlserver:/var/opt/mssql/data/QuanLyMangVienThong.bak
```

Liệt kê logical file name được lưu trong backup:

```bash
docker exec qlmvt-sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P '<SA_PASSWORD>' -C \
  -Q "RESTORE FILELISTONLY FROM DISK = N'/var/opt/mssql/data/QuanLyMangVienThong.bak'"
```

Đóng API và các kết nối tới database trước khi restore. Thay
`<LOGICAL_DATA_NAME>` và `<LOGICAL_LOG_NAME>` bằng cột `LogicalName` tương ứng
trong kết quả `FILELISTONLY`:

```bash
docker exec qlmvt-sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P '<SA_PASSWORD>' -C \
  -Q "RESTORE DATABASE [QuanLyMangVienThong] FROM DISK = N'/var/opt/mssql/data/QuanLyMangVienThong.bak' WITH MOVE N'<LOGICAL_DATA_NAME>' TO N'/var/opt/mssql/data/QuanLyMangVienThong.mdf', MOVE N'<LOGICAL_LOG_NAME>' TO N'/var/opt/mssql/data/QuanLyMangVienThong_log.ldf', RECOVERY, REPLACE"
```

Nếu backup có nhiều file data, phải thêm một `MOVE` cho từng file theo kết quả
`FILELISTONLY`. Chỉ dùng `REPLACE` khi đã xác nhận database đích được phép ghi
đè. Sau restore, cấu hình `.env` trỏ tới database vừa phục hồi rồi chạy
`python manage.py migrate` để áp dụng các migration Django còn thiếu.

## Tài khoản đăng nhập mẫu

Các tài khoản dưới đây được giữ nguyên theo danh sách hiện có. Chúng chỉ đăng
nhập được khi database được phục hồi có chứa các tài khoản tương ứng; script
tạo schema mới không tạo sẵn những tài khoản này. Vai trò do dữ liệu tài khoản
trong database quyết định (`admin` nếu Django `is_staff=true`, ngược lại là
`user`).

| Email | Mật khẩu |
|---|---|
| admin@telecom.com | 1234567890 |
| admin@gmail.com | 1234567890 |
| Nga.24730212@uit.edu.vn | 1234567890 |
| khoa.24730203@uit.edu.vn | 1234567890 |
| 24730185@uit.edu.vn | 1234567890 |
| cuonghm@gmail.com | 1234567890 |

Đây là thông tin demo, không dùng lại mật khẩu này cho môi trường thật.

## API và Swagger

- **Swagger UI:** `http://127.0.0.1:8000/qlmvt/swagger/`
- **OpenAPI YAML:** `http://127.0.0.1:8000/qlmvt/swagger.yaml`
- **API base path:** `http://127.0.0.1:8000/qlmvt`

Trong Swagger UI, bấm **Authorize** và nhập access token theo scheme Bearer để
thử các API cần đăng nhập. Mọi endpoint bên dưới dùng JSON trừ khi ghi rõ
multipart file. ID trong `{...}` là giá trị thực. Tên field JSON dùng
`snake_case` như được liệt kê. Các endpoint `PUT` thông thường cần gửi đầy đủ
object; chỉ các endpoint được ghi rõ là cập nhật từng phần mới nhận payload
một phần.

**Quyền:** `Public` không cần đăng nhập; `Đã đăng nhập` yêu cầu JWT; `Admin`
nghĩa là tài khoản có `is_staff=true`; `Nhân viên được phân công` là user chỉ
được thao tác dữ liệu lỗi/lỗ hổng được giao. Quyền `admin` vẫn cần tài khoản
được liên kết với nhân viên ở các thao tác có sử dụng mã nhân viên.

### Xác thực

| Method | Path | Mô tả / dữ liệu gửi | Trả về | Quyền |
|---|---|---|---|---|
| POST | `/qlmvt/api_login/` | Đăng nhập; JSON `{ "email": "...", "password": "..." }` | Access/refresh token, thời điểm hết hạn và `{ma_nv, ho_ten, email, role}` | Public |
| POST | `/qlmvt/api_logout/` | Blacklist refresh token; JSON `{ "refresh": "<refresh_token>" }` | `{ "message": "Đăng xuất thành công" }` | Không bắt buộc access token; gửi refresh token |
| GET | `/qlmvt/api_me/` | Lấy hồ sơ tài khoản hiện tại | `{ma_nv, ho_ten, email, role}` | Đã đăng nhập |
| POST | `/qlmvt/api_create-account/` | Tạo tài khoản cho nhân viên đã tồn tại; JSON `{ "ma_nv": 1, "password": "...", "is_admin": false }` | Message và object tài khoản | Admin |
| POST | `/qlmvt/api_change_password/` | Đổi mật khẩu; JSON `{ "old_password": "...", "new_password": "..." }` | Message yêu cầu đăng nhập lại | Đã đăng nhập |
| POST | `/qlmvt/api_refresh_token/` | Làm mới access token; JSON `{ "refresh": "<refresh_token>" }` | Token mới theo Simple JWT; refresh có thể được rotate | Public |

Với API cần đăng nhập, gửi access token trong header `Authorization` với scheme
`Bearer` (giá trị gồm tiền tố `Bearer ` theo sau bởi access token nhận từ login).

### Nhân viên

Field nhân viên: `ma_nv` (tự tăng), `ho_ten`, `email`, `so_dien_thoai`,
`vai_tro`, `chuyen_mon`. JSON trả về là object nhân viên hoặc danh sách object.

| Method | Path | Mô tả / dữ liệu gửi | Trả về | Quyền |
|---|---|---|---|---|
| GET | `/qlmvt/api_get_ds_nv/` | Danh sách nhân viên | Mảng nhân viên | Đã đăng nhập |
| GET | `/qlmvt/api_get_nv/{ma_nv}/` | Chi tiết nhân viên | Object nhân viên | Admin xem tất cả; user chỉ xem mình |
| POST | `/qlmvt/api_create_nv/` | Tạo một object hoặc mảng object; gửi field nhân viên, không gửi `ma_nv` | Object/mảng đã tạo (201) | Admin |
| PUT | `/qlmvt/api_update_nv/{ma_nv}/` | Cập nhật hồ sơ bằng payload đầy đủ; user không được gửi/sửa `vai_tro` hoặc `chuyen_mon` | Object đã cập nhật | Admin; user chỉ sửa hồ sơ mình |
| DELETE | `/qlmvt/api_delete_nv/{ma_nv}/` | Xóa nhân viên | `{ "message": "Đã xoá thành công" }` | Admin |

### Thiết bị

Field: `ma_tb` (tự tăng), `ten_tb`, `loai_tb`, `dia_chi_ip`, `vi_tri`,
`trang_thai`, `tinh_trang`. `dia_chi_ip` là duy nhất; `tinh_trang` bắt buộc khi
tạo/cập nhật.

| Method | Path | Mô tả / dữ liệu gửi | Trả về | Quyền |
|---|---|---|---|---|
| GET | `/qlmvt/api_get_ds_tb/` | Danh sách thiết bị | Mảng thiết bị | Đã đăng nhập |
| GET | `/qlmvt/api_get_tb/{ma_tb}/` | Chi tiết thiết bị | Object thiết bị | Đã đăng nhập |
| GET | `/qlmvt/api_get_tb_theo_loai_tb?loai_tb=router` | Lọc theo chuỗi con của `loai_tb`; bỏ query để lấy tất cả | Mảng thiết bị; 404 nếu không có kết quả | Đã đăng nhập |
| POST | `/qlmvt/api_create_tb/` | Tạo một object hoặc mảng object; không gửi `ma_tb` | Object/mảng đã tạo (201) | Admin |
| PUT | `/qlmvt/api_update_tb/{ma_tb}/` | Gửi object đầy đủ; không gửi/sửa `ma_tb` | Object đã cập nhật | Admin |
| DELETE | `/qlmvt/api_delete_tb/{ma_tb}/` | Xóa thiết bị | Message thành công | Admin |

### Chỉ số hiệu suất

Field: `ma_cs`, `ma_tb`, `thoi_gian_ghi_nhan`, `do_tre`, `mat_goi`,
`bang_thong_su_dung`. Chỉ có endpoint đọc trong API hiện tại.

| Method | Path | Mô tả / dữ liệu gửi | Trả về | Quyền |
|---|---|---|---|---|
| GET | `/qlmvt/api_get_ds_cshs/` | Danh sách chỉ số hiệu suất | Mảng chỉ số | Đã đăng nhập |
| GET | `/qlmvt/api_get_cshs/{ma_cs}/` | Chi tiết chỉ số | Object chỉ số | Đã đăng nhập |

### Lỗ hổng

Field: `ma_lh` (tự tăng), `ma_tb`, `ten_lo_hong`, `muc_do`,
`trang_thai_khac_phuc`, `thoi_gian_xay_ra_su_co`, `thoi_gian_xu_ly_su_co`,
`manv_xuly`. Trạng thái lọc dùng `fixed`, `unfixed`, `processing`; trạng thái
trong body là `Đã vá`, `Chưa vá`, `Đang xử lý`.

| Method | Path | Mô tả / dữ liệu gửi | Trả về | Quyền |
|---|---|---|---|---|
| GET | `/qlmvt/api_get_ds_lh/` | Danh sách lỗ hổng | Mảng lỗ hổng | Admin xem tất cả; user xem lỗ hổng được giao |
| GET | `/qlmvt/api_get_lh/{ma_lh}/` | Chi tiết lỗ hổng | Object lỗ hổng | Admin; user được phân công |
| GET | `/qlmvt/api_get_lh_theo_trangthai?trang_thai=fixed` | `trang_thai` tùy chọn: `fixed`, `unfixed`, `processing`; bỏ query để lấy tất cả | Mảng lỗ hổng; 400 nếu trạng thái sai | Admin xem tất cả; user chỉ xem dữ liệu được giao |
| POST | `/qlmvt/api_create_lh/` | Tạo một object hoặc mảng; gửi field lỗ hổng, không gửi `ma_lh`; thời điểm phát hiện mặc định là hiện tại, trạng thái mặc định `Chưa vá` | Object/mảng đã tạo (201) | Admin |
| PUT | `/qlmvt/api_update_lh/{ma_lh}/` | Payload cập nhật một phần; không gửi `ma_lh`. User chỉ gửi `trang_thai_khac_phuc` theo thứ tự `Chưa vá` → `Đang xử lý` → `Đã vá`; admin có thể cập nhật field khác theo quy tắc phân công | Object đã cập nhật | Admin; user được phân công |
| DELETE | `/qlmvt/api_delete_lh/{ma_lh}/` | Xóa lỗ hổng | Message thành công | Admin |

### Liên kết thiết bị

Field: `ma_lk` (tự tăng), `matb_goc`, `matb_dich`, `bang_thong_toi_da`,
`manv_tao`.

| Method | Path | Mô tả / dữ liệu gửi | Trả về | Quyền |
|---|---|---|---|---|
| GET | `/qlmvt/api_get_ds_lk/` | Danh sách liên kết | Mảng liên kết | Đã đăng nhập |
| GET | `/qlmvt/api_get_lk/{ma_lk}/` | Chi tiết liên kết | Object liên kết | Đã đăng nhập |
| POST | `/qlmvt/api_create_lk/` | Tạo một object hoặc mảng; gửi field liên kết. Nếu bỏ `manv_tao`, hệ thống dùng nhân viên liên kết với admin hiện tại | Object/mảng đã tạo (201) | Admin |
| PUT | `/qlmvt/api_update_lk/{ma_lk}/` | Cập nhật payload đầy đủ; admin chỉ sửa liên kết do chính mình tạo | Object đã cập nhật | Admin tạo liên kết đó |
| DELETE | `/qlmvt/api_delete_lk/{ma_lk}/` | Xóa liên kết; admin chỉ xóa liên kết do chính mình tạo | Message thành công | Admin tạo liên kết đó |

### Nhật ký lỗi

Field: `ma_loi` (tự tăng), `ma_tb`, `thoi_gian_loi`, `mo_ta_loi`,
`muc_do_nghiem_trong`, `manv_xuly`, `da_xu_ly`, `thoi_gian_hoan_thanh`.
`thoi_gian_loi` mặc định là thời điểm hiện tại khi tạo; `da_xu_ly` phải có khi
tạo.

| Method | Path | Mô tả / dữ liệu gửi | Trả về | Quyền |
|---|---|---|---|---|
| GET | `/qlmvt/api_get_ds_nkl/` | Danh sách nhật ký lỗi | Mảng nhật ký lỗi | Admin xem tất cả; user xem lỗi được giao |
| GET | `/qlmvt/api_get_nkl/{ma_loi}/` | Chi tiết nhật ký lỗi | Object nhật ký lỗi | Admin; user được phân công |
| GET | `/qlmvt/api_get_nkl_theo_xuly?da_xu_ly=false` | Query tùy chọn `da_xu_ly=true` hoặc `false`; bỏ query để lấy tất cả | Mảng nhật ký lỗi; 400 nếu giá trị khác true/false | Admin xem tất cả; user chỉ xem lỗi được giao |
| POST | `/qlmvt/api_create_nkl/` | Tạo một object hoặc mảng; gửi field lỗi, không gửi `ma_loi`; `da_xu_ly` bắt buộc | Object/mảng đã tạo (201) | Admin |
| PUT | `/qlmvt/api_update_nkl/{ma_loi}/` | Payload cập nhật một phần; không gửi `ma_loi`, `thoi_gian_loi`, `thoi_gian_hoan_thanh`. User chỉ chuyển `da_xu_ly` từ false sang true; thời gian hoàn thành tự ghi | Object nhật ký đã cập nhật | Admin; user được phân công |
| PUT | `/qlmvt/api_phan_cong_nv_xuly_loi/{ma_loi}/` | JSON `{ "manv_xuly": 1 }`; mã nhân viên phải tồn tại; chỉ phân công lỗi chưa xử lý | `{ "message": "Phân công nhân viên xử lý lỗi thành công" }` | Admin |
| DELETE | `/qlmvt/api_delete_nkl/{ma_loi}/` | Xóa nhật ký lỗi | Message thành công | Admin |

### Báo cáo

| Method | Path | Mô tả / dữ liệu gửi | Trả về | Quyền |
|---|---|---|---|---|
| GET | `/qlmvt/api_get_bao_cao_tong_quan` | Tổng quan số lượng nhân viên, thiết bị, liên kết, chỉ số, lỗi và lỗ hổng | Object gồm `nhan_vien`, `thiet_bi`, `lien_ket`, `chi_so_hieu_suat`, `nhat_ky_loi{tong,da_xu_ly,chua_xu_ly}`, `lo_hong{tong,da_va,chua_va,dang_xu_ly}` | Đã đăng nhập; số lỗi/lỗ hổng của user chỉ tính dữ liệu được giao |
| GET | `/qlmvt/api_get_tong_loi_nv_xu_ly` | Tổng số lỗi theo nhân viên | Mảng `{ma_nv, ho_ten, su_co{tong,da_xu_ly,dang_xu_ly}}` | Admin xem tất cả; user chỉ xem mình |
| GET | `/qlmvt/api_get_kpi_nhan_vien` | KPI nhân viên; cần function `dbo.fn_BangKPI_NhanVien` | Mảng kết quả KPI từ SQL function | Admin xem tất cả; user chỉ xem mình |
| GET | `/qlmvt/api_get_tinh_trang_lo_hong` | Tổng lỗ hổng theo trạng thái | `{tong, da_va, chua_va, dang_xu_ly}` | Admin xem tất cả; user chỉ xem dữ liệu được giao |
| GET | `/qlmvt/api_get_lo_hong_theo_thiet_bi` | Thống kê lỗ hổng theo thiết bị; cần procedure `dbo.sp_GetVulnerabilityMap` | Mảng `{ten_tb, tong_lo_hong, muc_do{critical,high,medium,low}}` | Đã đăng nhập |

### Backup/restore JSON và import/export

Các endpoint JSON bên dưới xử lý sáu bảng nghiệp vụ, không tạo hoặc phục hồi
file backup vật lý SQL Server `.bak`. Chúng yêu cầu JWT admin và access token
theo scheme Bearer.

| Method | Path | Mô tả / dữ liệu gửi | Trả về | Quyền |
|---|---|---|---|---|
| GET | `/qlmvt/api_backup_database` | Tải snapshot JSON gồm `nhanvien`, `thietbi`, `lienket`, `hieusuat`, `lohong`, `nhatkyloi` | File `qlmvt_backup.json` với `{format, version, models}` | Admin |
| POST | `/qlmvt/api_restore_database` | Gửi JSON backup trong request body; `format`/`version` phải khớp `.env`, record phải có khóa chính | `{message, data}`; `data` đếm số record theo model | Admin |
| GET | `/qlmvt/api_export_table/{model_name}` | Tải một bảng; `model_name` là `nhanvien`, `thietbi`, `lienket`, `hieusuat`, `lohong`, hoặc `nhatkyloi` | File `{model_name}_export.json` | Admin |
| POST | `/qlmvt/api_import_table/{model_name}` | Multipart form-data, key `file`, file `.json` UTF-8 đúng model/format/version | `{message, data:{model,total,created,updated}}` | Admin |

Restore JSON cập nhật record cùng khóa chính hoặc tạo record mới; **không xóa**
record hiện có không xuất hiện trong file. Import cũng upsert, không xóa dữ liệu.
Thứ tự restore được sắp xếp theo khóa ngoại và thao tác JSON restore chạy trong
transaction. Mỗi file import/export một bảng có cấu trúc
`{format, version, model, records}`. Các định dạng và version cần khớp cấu hình
trong `.env`.

## Xử lý lỗi khởi động phổ biến

- **ODBC Driver not found / login timeout:** cài ODBC Driver 18 và kiểm tra SQL
  Server đang chạy, firewall, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`.
- **Database does not exist:** restore file `.bak` hoặc chạy
  `MSSQL/SQL_total_local.sql` trước `migrate`.
- **Invalid object name:** schema chưa được tạo/restore đầy đủ hoặc `.env` đang
  trỏ nhầm database.
- **Lỗi parse biến môi trường khi import settings:** kiểm tra đủ bốn biến
  `IMPORT_EXPORT_FORMAT`, `IMPORT_EXPORT_VERSION`, `BACKUP_FORMAT`,
  `BACKUP_VERSION` trong `.env`.
- **Port 1433 already in use:** đổi cổng publish Docker (ví dụ
  `-p 1434:1433`) và đặt `DB_PORT=1434`.
- **Không có tài khoản để đăng nhập:** SQL script tạo schema không thêm dữ liệu
  demo; cần restore bản `.bak` có tài khoản hoặc nạp dữ liệu/tài khoản phù hợp.

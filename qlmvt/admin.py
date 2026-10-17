from django.contrib import admin

# Register your models here.
from .models.nhanvien import NhanVien
from .models.thietbi import ThietBi
from .models.lienket import LienKet
from .models.hieusuat import ChiSoHieuSuat
from .models.lohong import LoHong
from .models.nhatkyloi import NhatKyLoi

admin.site.register(NhanVien)
admin.site.register(ThietBi)
admin.site.register(LienKet)
admin.site.register(ChiSoHieuSuat)
admin.site.register(LoHong)
admin.site.register(NhatKyLoi)

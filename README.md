# Shadow Core Boot Puller 🖤

أداة CLI لسحب `boot.img` من هاتف **OPPO Reno 5 CPH2159** (ColorOS)
تعمل مباشرة على الهاتف عبر **Termux**

## المتطلبات
- Termux مثبت على الهاتف
- صلاحيات Root (Magisk)
- Python 3

## التثبيت
```bash
pkg update && pkg install python git
git clone https://github.com/Youssefzdb/root
cd root
python boot_pull.py
```

## الميزات
- كشف تلقائي لـ boot partition
- التحقق من صحة الملف (Magic bytes)
- حفظ منظم مع timestamp
- واجهة ملونة وتفاعلية

## الجهاز المستهدف
| المعلومة | القيمة |
|----------|--------|
| الموديل | CPH2159 |
| الاسم | OPPO Reno 5 |
| النظام | ColorOS |
| المعالج | MediaTek Helio P95 |

---
*Built by Shadow Core*


## منبع جایگزین داده

اگر TSETMC از GitHub Actions یا شبکه اجرا پاسخ ندهد، می‌توان یک کلید رایگان BRSAPI را در تنظیمات مخزن با نام `BRS_API_KEY` به‌صورت Secret ثبت کرد. مسیر GitHub: `Settings → Secrets and variables → Actions → New repository secret`. کلید را در فایل، commit، log یا URL عمومی قرار ندهید. سامانه ابتدا TSETMC را امتحان می‌کند و فقط در صورت وجود این Secret از BRSAPI استفاده می‌کند.

BRSAPI یک سرویس واسط داده TSETMC است و باید محدودیت‌ها، نرخ درخواست و شرایط استفاده آن بررسی شود؛ منبع fallback جایگزین اعتبارسنجی بازار یا تضمین صحت داده نیست.

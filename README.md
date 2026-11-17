# gardegypt-content-writer

**المهمة:** تحديث محتوى الصفحات وحقول Rank Math.

هذا المستودع يحفظ أوامر المهام بصيغة JSON فقط. GitHub Actions يتحقق من سلامة ملف المهمة، ولا يتصل بالموقع أو يكتب عليه. إضافة GitHub Token لا تتم هنا.

## التنفيذ
1. أضف كل مهمة فريدة إلى jobs/ بصيغة JSON، مستندًا إلى examples/job-template.json.
2. احفظ موافقة التنفيذ في الحقل الخاص بالمهمة؛ المهام غير المعتمدة تظل في الانتظار.
3. إضافة الملف تشغل فحص صيغة تلقائيًا.
4. إضافة GardEgypt WordPress GitHub Bridge داخل الموقع تسحب المهام المعتمدة وتطبقها من داخل ووردبريس، ثم تكتب إيصالًا في receipts/.

## الربط
ضع Fine-grained GitHub token في إعدادات إضافة GardEgypt Bridge داخل ووردبريس. لا تستخدم WordPress Application Password ولا تضع أي token أو كلمة مرور في هذا المستودع. يحتاج التوكن صلاحية Contents read/write للمستودعات الستة حتى يقرأ المهام ويكتب الإيصالات.






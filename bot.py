import logging
import sqlite3
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("hepiq_support_bot")

DB_PATH = "hepiq_support.db"

# الأقسام كما زودتني
DEPARTMENTS = [
    "قسم علوم الحاسوب",
    "قسم نظم المعلومات",
    "قسم الأنظمة الطبية الذكية",
    "قسم الأمن السيبراني",
]

# ضع هنا chat_id لمسؤول كل قسم (بعد أن يأخذوه عبر /myid)
# مثال: "قسم علوم الحاسوب": 123456789
DEPT_ADMIN_CHAT_ID = {
    "قسم علوم الحاسوب": 155833648,
    "قسم نظم المعلومات": 192801128,
    "قسم الأنظمة الطبية الذكية": 7583987364,
    "قسم الأمن السيبراني": 197659956,
}



STUDY_TYPES = ["صباحية", "مسائية"]
STAGES = ["1", "2", "3", "4"]

# حالات محادثة الطالب
(
    S_FULLNAME,
    S_DEPARTMENT,
    S_STAGE,
    S_STUDY_TYPE,
    S_DESCRIPTION,
    S_PHOTO_OPTIONAL,
) = range(6)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_chat_id INTEGER NOT NULL,
        student_fullname TEXT NOT NULL,
        department TEXT NOT NULL,
        stage INTEGER NOT NULL,
        study_type TEXT NOT NULL,
        description TEXT NOT NULL,
        photo_file_id TEXT,
        status TEXT NOT NULL,
        admin_chat_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_pending (
        admin_chat_id INTEGER PRIMARY KEY,
        action TEXT NOT NULL,
        ticket_id INTEGER NOT NULL
    );
    """)

    conn.commit()
    conn.close()


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("طلب جديد", callback_data="NEW_TICKET")],
        [InlineKeyboardButton("تعليمات سريعة", callback_data="FAQ")],
    ])


def departments_kb() -> InlineKeyboardMarkup:
    rows = []
    for d in DEPARTMENTS:
        rows.append([InlineKeyboardButton(d, callback_data=f"DEP::{d}")])
    return InlineKeyboardMarkup(rows)


def stages_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("المرحلة 1", callback_data="STAGE::1")],
        [InlineKeyboardButton("المرحلة 2", callback_data="STAGE::2")],
        [InlineKeyboardButton("المرحلة 3", callback_data="STAGE::3")],
        [InlineKeyboardButton("المرحلة 4", callback_data="STAGE::4")],
    ])


def study_types_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("صباحية", callback_data="STUDY::صباحية")],
        [InlineKeyboardButton("مسائية", callback_data="STUDY::مسائية")],
    ])


def photo_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("إرسال لقطة شاشة", callback_data="PHOTO::YES")],
        [InlineKeyboardButton("تخطي", callback_data="PHOTO::NO")],
    ])


def admin_ticket_actions_kb(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("استلام", callback_data=f"ADM::ASSIGN::{ticket_id}"),
            InlineKeyboardButton("طلب معلومات إضافية", callback_data=f"ADM::ASK::{ticket_id}"),
        ],
        [
            InlineKeyboardButton("تم الحل", callback_data=f"ADM::RESOLVE::{ticket_id}"),
        ],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحباً. هذا بوت دعم مشاكل تسجيل الدخول في تطبيق HEPIQ.\n"
        "اختر من القائمة:",
        reply_markup=main_menu_kb(),
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Chat ID الخاص بك هو: {update.effective_chat.id}")


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "NEW_TICKET":
        await q.message.reply_text("اكتب الاسم الثلاثي (إلزامي):")
        return S_FULLNAME

    if q.data == "FAQ":
        await q.message.reply_text(
            "تعليمات سريعة:\n"
            "- لا ترسل كلمة المرور.\n"
            "- اكتب وصف المشكلة بدقة.\n"
            "- إن أمكن أرسل لقطة شاشة لرسالة الخطأ.\n"
            "للإنشاء: اختر (طلب جديد).",
            reply_markup=main_menu_kb(),
        )
        return ConversationHandler.END

    return ConversationHandler.END


async def fullname_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fullname = (update.message.text or "").strip()
    if len(fullname.split()) < 3:
        await update.message.reply_text("الرجاء إدخال الاسم الثلاثي (ثلاث كلمات على الأقل).")
        return S_FULLNAME

    context.user_data["student_fullname"] = fullname
    await update.message.reply_text("اختر القسم:", reply_markup=departments_kb())
    return S_DEPARTMENT


async def department_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not q.data.startswith("DEP::"):
        await q.message.reply_text("اختر القسم من الأزرار.")
        return S_DEPARTMENT

    dept = q.data.split("DEP::", 1)[1]
    context.user_data["department"] = dept

    # تحقق أن مسؤول القسم معرف
    admin_id = DEPT_ADMIN_CHAT_ID.get(dept, 0)
    if not admin_id:
        await q.message.reply_text(
            "تنبيه إداري: لم يتم ضبط معرف مسؤول هذا القسم بعد.\n"
            "الرجاء إبلاغ الإدارة لضبط Chat ID لمسؤول القسم."
        )
        return ConversationHandler.END

    await q.message.reply_text("اختر المرحلة:", reply_markup=stages_kb())
    return S_STAGE


async def stage_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not q.data.startswith("STAGE::"):
        await q.message.reply_text("اختر المرحلة من الأزرار.")
        return S_STAGE

    stage = q.data.split("STAGE::", 1)[1]
    context.user_data["stage"] = int(stage)

    await q.message.reply_text("اختر نوع الدراسة:", reply_markup=study_types_kb())
    return S_STUDY_TYPE


async def study_type_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not q.data.startswith("STUDY::"):
        await q.message.reply_text("اختر نوع الدراسة من الأزرار.")
        return S_STUDY_TYPE

    study = q.data.split("STUDY::", 1)[1]
    context.user_data["study_type"] = study

    await q.message.reply_text("اكتب وصف المشكلة (مثال: تظهر رسالة خطأ / لا يصل OTP / كلمة المرور مرفوضة...):")
    return S_DESCRIPTION


async def description_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = (update.message.text or "").strip()
    if len(desc) < 10:
        await update.message.reply_text("الرجاء كتابة وصف أوضح (10 أحرف على الأقل).")
        return S_DESCRIPTION

    context.user_data["description"] = desc
    await update.message.reply_text("هل تريد إرسال لقطة شاشة؟", reply_markup=photo_choice_kb())
    return S_PHOTO_OPTIONAL


async def photo_choice_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "PHOTO::YES":
        await q.message.reply_text("أرسل الصورة الآن (لقطة شاشة).")
        return S_PHOTO_OPTIONAL

    if q.data == "PHOTO::NO":
        # إنشاء التذكرة بدون صورة
        ticket_id = create_ticket(update, context, photo_file_id=None)
        await q.message.reply_text(
            f"تم استلام طلبك بنجاح.\nرقم التذكرة: #{ticket_id}\nسيتم التواصل معك برسالة خاصة عبر هذا البوت.",
            reply_markup=main_menu_kb(),
        )
        return ConversationHandler.END

    await q.message.reply_text("اختر من الأزرار.")
    return S_PHOTO_OPTIONAL


async def photo_received_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # هذه الدالة تُستدعى عندما يرسل الطالب صورة
    if not update.message.photo:
        await update.message.reply_text("الرجاء إرسال صورة (لقطة شاشة) أو اختر (تخطي) من القائمة.")
        await update.message.reply_text("هل تريد إرسال لقطة شاشة؟", reply_markup=photo_choice_kb())
        return S_PHOTO_OPTIONAL

    photo_file_id = update.message.photo[-1].file_id
    ticket_id = create_ticket(update, context, photo_file_id=photo_file_id)

    await update.message.reply_text(
        f"تم استلام طلبك بنجاح.\nرقم التذكرة: #{ticket_id}\nسيتم التواصل معك برسالة خاصة عبر هذا البوت.",
        reply_markup=main_menu_kb(),
    )
    return ConversationHandler.END


def create_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE, photo_file_id: str | None) -> int:
    student_chat_id = update.effective_chat.id
    fullname = context.user_data["student_fullname"]
    department = context.user_data["department"]
    stage = context.user_data["stage"]
    study_type = context.user_data["study_type"]
    description = context.user_data["description"]
    admin_chat_id = DEPT_ADMIN_CHAT_ID[department]
    ts = now_iso()

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tickets (
            student_chat_id, student_fullname, department, stage, study_type,
            description, photo_file_id, status, admin_chat_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        student_chat_id, fullname, department, stage, study_type,
        description, photo_file_id, "NEW", admin_chat_id, ts, ts
    ))
    ticket_id = cur.lastrowid
    conn.commit()
    conn.close()

    # إرسال الطلب لمسؤول القسم
    # ملاحظة: نستخدم application عبر context.application في بيئات async
    # لكن هنا داخل sync؛ سنرسل من خلال create_task في مكان آخر إن أحببت.
    # للحفاظ على البساطة: سنؤجل الإرسال عبر job queue في النسخة المتقدمة.
    # الآن: سنرسل فوراً باستخدام create_task من loop.
    app = context.application
    app.create_task(notify_admin_new_ticket(
        app=app,
        admin_chat_id=admin_chat_id,
        ticket_id=ticket_id,
        fullname=fullname,
        department=department,
        stage=stage,
        study_type=study_type,
        description=description,
        photo_file_id=photo_file_id,
    ))
    return ticket_id


async def notify_admin_new_ticket(
    app: Application,
    admin_chat_id: int,
    ticket_id: int,
    fullname: str,
    department: str,
    stage: int,
    study_type: str,
    description: str,
    photo_file_id: str | None,
):
    text = (
        f"طلب دعم جديد (HEPIQ)\n"
        f"تذكرة: #{ticket_id}\n"
        f"الاسم الثلاثي: {fullname}\n"
        f"القسم: {department}\n"
        f"المرحلة: {stage}\n"
        f"نوع الدراسة: {study_type}\n"
        f"وصف المشكلة:\n{description}"
    )
    await app.bot.send_message(
        chat_id=admin_chat_id,
        text=text,
        reply_markup=admin_ticket_actions_kb(ticket_id),
    )
    if photo_file_id:
        await app.bot.send_photo(chat_id=admin_chat_id, photo=photo_file_id)


def is_admin(chat_id: int) -> bool:
    return chat_id in set(DEPT_ADMIN_CHAT_ID.values()) and chat_id != 0


async def admin_actions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    admin_chat_id = update.effective_chat.id
    if not is_admin(admin_chat_id):
        await q.message.reply_text("هذا الإجراء مخصص لمسؤولي الأقسام فقط.")
        return

    # ADM::ASSIGN::{id} / ADM::ASK::{id} / ADM::RESOLVE::{id}
    parts = q.data.split("::")
    if len(parts) != 3:
        await q.message.reply_text("صيغة أمر غير صحيحة.")
        return

    _, action, ticket_id_str = parts
    ticket_id = int(ticket_id_str)

    ticket = get_ticket(ticket_id)
    if not ticket:
        await q.message.reply_text("التذكرة غير موجودة.")
        return
    if ticket["admin_chat_id"] != admin_chat_id:
        await q.message.reply_text("هذه التذكرة ليست ضمن قسمك.")
        return

    if action == "ASSIGN":
        update_ticket_status(ticket_id, "ASSIGNED")
        await q.message.reply_text(f"تم استلام التذكرة #{ticket_id}.")
        await notify_student(ticket_id, context, "تم استلام طلبك من مسؤول القسم، وسيتم العمل على الحل.")
        return

    if action == "ASK":
        set_admin_pending(admin_chat_id, "ASK_MORE", ticket_id)
        update_ticket_status(ticket_id, "WAITING_STUDENT")
        await q.message.reply_text(
            f"اكتب الآن رسالة (السؤال/المطلوب) لإرسالها للطالب بخصوص التذكرة #{ticket_id}:"
        )
        return

    if action == "RESOLVE":
        set_admin_pending(admin_chat_id, "SEND_SOLUTION", ticket_id)
        await q.message.reply_text(
            f"اكتب الآن نص الحل لإرساله للطالب وإغلاق التذكرة #{ticket_id}:"
        )
        return


async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_chat_id = update.effective_chat.id
    if not is_admin(admin_chat_id):
        return

    pending = get_admin_pending(admin_chat_id)
    if not pending:
        return

    text = (update.message.text or "").strip()
    ticket_id = pending["ticket_id"]

    if pending["action"] == "ASK_MORE":
        clear_admin_pending(admin_chat_id)
        await notify_student(ticket_id, context, f"طلب معلومات إضافية بخصوص تذكرتك #{ticket_id}:\n{text}\n\nالرجاء الرد هنا على نفس البوت.")
        # هنا يمكن إضافة مسار لربط رد الطالب بالتذكرة (نسخة متقدمة)
        await update.message.reply_text("تم إرسال الطلب للطالب.")
        return

    if pending["action"] == "SEND_SOLUTION":
        clear_admin_pending(admin_chat_id)
        update_ticket_status(ticket_id, "RESOLVED")
        await notify_student(ticket_id, context, f"تم حل تذكرتك #{ticket_id}.\nتفاصيل الحل:\n{text}")
        await update.message.reply_text("تم إرسال الحل للطالب وإغلاق التذكرة.")
        return


def get_ticket(ticket_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    row = cur.fetchone()
    conn.close()
    return row


def update_ticket_status(ticket_id: int, status: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), ticket_id))
    conn.commit()
    conn.close()


async def notify_student(ticket_id: int, context: ContextTypes.DEFAULT_TYPE, message: str):
    ticket = get_ticket(ticket_id)
    if not ticket:
        return
    await context.bot.send_message(chat_id=ticket["student_chat_id"], text=message)


def set_admin_pending(admin_chat_id: int, action: str, ticket_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO admin_pending(admin_chat_id, action, ticket_id)
        VALUES (?, ?, ?)
        ON CONFLICT(admin_chat_id) DO UPDATE SET action=excluded.action, ticket_id=excluded.ticket_id
    """, (admin_chat_id, action, ticket_id))
    conn.commit()
    conn.close()


def get_admin_pending(admin_chat_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM admin_pending WHERE admin_chat_id = ?", (admin_chat_id,))
    row = cur.fetchone()
    conn.close()
    return row


def clear_admin_pending(admin_chat_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM admin_pending WHERE admin_chat_id = ?", (admin_chat_id,))
    conn.commit()
    conn.close()


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.", reply_markup=main_menu_kb())
    return ConversationHandler.END


def build_app(token: str) -> Application:
    init_db()

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_callback, pattern="^(NEW_TICKET|FAQ)$")],
        states={
            S_FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fullname_step)],
            S_DEPARTMENT: [CallbackQueryHandler(department_step, pattern="^DEP::")],
            S_STAGE: [CallbackQueryHandler(stage_step, pattern="^STAGE::")],
            S_STUDY_TYPE: [CallbackQueryHandler(study_type_step, pattern="^STUDY::")],
            S_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description_step)],
            S_PHOTO_OPTIONAL: [
                CallbackQueryHandler(photo_choice_step, pattern="^PHOTO::"),
                MessageHandler(filters.PHOTO, photo_received_step),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))

    # محادثة الطلب
    app.add_handler(conv)

    # أزرار المسؤول
    app.add_handler(CallbackQueryHandler(admin_actions_callback, pattern="^ADM::"))

    # نصوص المسؤول بعد الضغط (ASK / RESOLVE)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler))

    return app


if __name__ == "__main__":
    # ضع التوكن هنا
    BOT_TOKEN = "8549926870:AAGk2Qg1LKbaVNbEPZkBPoR4vnF8o5QQLeg"

    app = build_app(BOT_TOKEN)
    app.run_polling(drop_pending_updates=True)

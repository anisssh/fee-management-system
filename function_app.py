import json
import logging
from datetime import date
import azure.functions as func
import azure.durable_functions as df

from repositories.student_repository import get_student_by_id, get_overdue_students, update_student_fee
from services.fee_service import get_payment_status
from services.notification_service import send_reminder_email
from jwt_validator import validate_token, require_role, AuthError

app = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="students/{studentId}/fees", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def GetStudentFees(req: func.HttpRequest) -> func.HttpResponse:
    student_id_raw = req.route_params.get("studentId")

    if not student_id_raw or not student_id_raw.isdigit():
        return func.HttpResponse(
            json.dumps({"error": "studentId must be a valid integer"}),
            status_code=400,
            mimetype="application/json",
        )

    student_id = int(student_id_raw)

    try:
        student = get_student_by_id(student_id)
    except Exception as e:
        logging.error(f"Database error fetching student {student_id}: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Internal server error"}),
            status_code=500,
            mimetype="application/json",
        )

    if student is None:
        return func.HttpResponse(
            json.dumps({"error": f"Student {student_id} not found"}),
            status_code=404,
            mimetype="application/json",
        )

    response_body = student.to_dict()
    response_body["paymentStatus"] = get_payment_status(student)

    return func.HttpResponse(
        json.dumps(response_body),
        status_code=200,
        mimetype="application/json",
    )


# ---------------------------------------------------------------------------
# Task 2: Automated fee reminders via Durable Functions
# ---------------------------------------------------------------------------

@app.timer_trigger(schedule="0 0 8 * * *", arg_name="timer", run_on_startup=False)
@app.durable_client_input(client_name="client")
async def ReminderTimerTrigger(timer: func.TimerRequest, client) -> None:
    """
    Fires daily at 8:00 AM UTC. Starts the reminder orchestration.
    Cron format here is NCRONTAB: {second} {minute} {hour} {day} {month} {day-of-week}.
    """
    instance_id = await client.start_new("ReminderOrchestrator")
    logging.info(f"Started reminder orchestration with instance ID = {instance_id}")


@app.orchestration_trigger(context_name="context")
def ReminderOrchestrator(context: df.DurableOrchestrationContext):
    """
    Fetches all overdue students, then fans out one activity call per
    student to send a reminder email. Fans back in to log a summary.
    """
    overdue_students = yield context.call_activity("GetOverdueStudentsActivity")

    tasks = [
        context.call_activity("SendReminderActivity", student)
        for student in overdue_students
    ]
    results = yield context.task_all(tasks)

    sent = sum(1 for r in results if r)
    failed = len(results) - sent
    logging.info(f"Reminder run complete: {sent} sent, {failed} failed, {len(overdue_students)} overdue total")

    return {"totalOverdue": len(overdue_students), "sent": sent, "failed": failed}


@app.activity_trigger(input_name="ignore")
def GetOverdueStudentsActivity(ignore) -> list:
    """
    Activity function: queries the database for overdue students.
    Returns plain dicts (durable activities must return JSON-serializable data,
    not Student dataclass instances directly).
    """
    students = get_overdue_students()
    return [
        {
            "studentId": s.student_id,
            "name": s.name,
            "course": s.course,
            "totalFee": s.total_fee,
            "paidAmount": s.paid_amount,
            "dueDate": s.due_date.isoformat(),
            "email": s.email,
        }
        for s in students
    ]


@app.activity_trigger(input_name="studentDict")
def SendReminderActivity(studentDict: dict) -> bool:
    """
    Activity function: sends one reminder email for one student.
    Rebuilds a Student object from the dict passed through the orchestrator.
    """
    from datetime import date as date_cls
    from models import Student

    student = Student(
        student_id=studentDict["studentId"],
        name=studentDict["name"],
        course=studentDict["course"],
        total_fee=studentDict["totalFee"],
        paid_amount=studentDict["paidAmount"],
        due_date=date_cls.fromisoformat(studentDict["dueDate"]),
        email=studentDict["email"],
    )

    return send_reminder_email(student)


# ---------------------------------------------------------------------------
# Task 4: Secure admin fee updates (Entra ID JWT + RBAC)
# ---------------------------------------------------------------------------

@app.route(route="manage/fees/{studentId}", methods=["PUT"], auth_level=func.AuthLevel.ANONYMOUS)
def UpdateStudentFee(req: func.HttpRequest) -> func.HttpResponse:
    """
    Admin-only endpoint to update a student's PaidAmount and/or DueDate.
    Requires a valid Entra ID JWT with the "Admin" app role.
    """
    # --- Auth check first, before touching the database or request body ---
    try:
        auth_header = req.headers.get("Authorization")
        claims = validate_token(auth_header)
        require_role(claims, "Admin")
    except AuthError as e:
        logging.warning(f"Authorization failed: {e.message}")
        return func.HttpResponse(
            json.dumps({"error": e.message}),
            status_code=e.status_code,
            mimetype="application/json",
        )

    # --- Validate route param ---
    student_id_raw = req.route_params.get("studentId")
    if not student_id_raw or not student_id_raw.isdigit():
        return func.HttpResponse(
            json.dumps({"error": "studentId must be a valid integer"}),
            status_code=400,
            mimetype="application/json",
        )
    student_id = int(student_id_raw)

    # --- Validate request body ---
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON"}),
            status_code=400,
            mimetype="application/json",
        )

    paid_amount = body.get("paidAmount")
    due_date_raw = body.get("dueDate")

    if paid_amount is None and due_date_raw is None:
        return func.HttpResponse(
            json.dumps({"error": "Provide at least one of paidAmount or dueDate"}),
            status_code=400,
            mimetype="application/json",
        )

    due_date_parsed = None
    if due_date_raw is not None:
        try:
            due_date_parsed = date.fromisoformat(due_date_raw)
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "dueDate must be in YYYY-MM-DD format"}),
                status_code=400,
                mimetype="application/json",
            )

    # --- Perform the update ---
    try:
        updated = update_student_fee(student_id, paid_amount=paid_amount, due_date=due_date_parsed)
    except Exception as e:
        logging.error(f"Database error updating student {student_id}: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Internal server error"}),
            status_code=500,
            mimetype="application/json",
        )

    if not updated:
        return func.HttpResponse(
            json.dumps({"error": f"Student {student_id} not found"}),
            status_code=404,
            mimetype="application/json",
        )

    student = get_student_by_id(student_id)
    response_body = student.to_dict()
    response_body["paymentStatus"] = get_payment_status(student)

    return func.HttpResponse(
        json.dumps(response_body),
        status_code=200,
        mimetype="application/json",
    )
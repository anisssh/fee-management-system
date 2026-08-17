import os
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from models import Student

SENDER_EMAIL = "anish160503@gmail.com"  # must match your SendGrid verified single sender


def send_reminder_email(student: Student) -> bool:
    """
    Sends a fee reminder email to one student via SendGrid.
    Returns True on success, False on failure (never raises, so one
    failed email doesn't stop the rest of the batch from being sent).
    """
    if not student.email:
        logging.warning(f"Student {student.student_id} has no email on file; skipping.")
        return False

    outstanding = student.total_fee - student.paid_amount

    message = Mail(
        from_email=Email(SENDER_EMAIL, "Fee Management Office"),
        to_emails=To(student.email),
        subject="Fee Payment Reminder",
        plain_text_content=Content(
            "text/plain",
            f"Dear {student.name},\n\n"
            f"This is a reminder that your fee payment for {student.course} is overdue.\n"
            f"Total fee: {student.total_fee}\n"
            f"Amount paid: {student.paid_amount}\n"
            f"Outstanding amount: {outstanding}\n"
            f"Due date: {student.due_date.isoformat()}\n\n"
            f"Please clear the pending amount at your earliest convenience.\n\n"
            f"Regards,\nFee Management Office"
        ),
    )

    try:
        sg = SendGridAPIClient(os.environ["SENDGRID_API_KEY"])
        response = sg.send(message)
        logging.info(f"Reminder sent to student {student.student_id}, status {response.status_code}")
        return True
    except Exception as e:
        logging.error(f"Failed to send reminder to student {student.student_id}: {e}")
        return False
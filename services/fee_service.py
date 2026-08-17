from datetime import date
from models import Student


def get_payment_status(student: Student) -> str:
    """
    Determines payment status per the assignment's three-state model:
    - "Paid": fully paid, regardless of due date
    - "Overdue": not fully paid AND due date has passed
    - "Partially Paid": not fully paid, but due date hasn't passed yet
      (this includes students who haven't paid anything at all, since the
      assignment only specifies three states)
    """
    if student.paid_amount >= student.total_fee:
        return "Paid"

    if student.due_date < date.today():
        return "Overdue"

    return "Partially Paid"
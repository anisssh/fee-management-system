from db import get_connection
from models import Student


def get_student_by_id(student_id: int):
    """
    Fetches a single student row by StudentID.
    Returns a Student object, or None if not found.
    Uses a parameterized query to prevent SQL injection.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT StudentID, Name, Course, TotalFee, PaidAmount, DueDate, Email
        FROM Students
        WHERE StudentID = ?
        """,
        student_id,
    )
    row = cursor.fetchone()

    if row is None:
        return None

    return Student(
        student_id=row.StudentID,
        name=row.Name,
        course=row.Course,
        total_fee=float(row.TotalFee),
        paid_amount=float(row.PaidAmount),
        due_date=row.DueDate,
        email=row.Email,
    )


def get_overdue_students():
    """
    Fetches all students who are not fully paid AND past their due date.
    This matches the "Overdue" status rule from fee_service.get_payment_status:
    PaidAmount < TotalFee AND DueDate < today.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT StudentID, Name, Course, TotalFee, PaidAmount, DueDate, Email
        FROM Students
        WHERE PaidAmount < TotalFee AND DueDate < CAST(GETDATE() AS DATE)
        """
    )
    rows = cursor.fetchall()

    return [
        Student(
            student_id=row.StudentID,
            name=row.Name,
            course=row.Course,
            total_fee=float(row.TotalFee),
            paid_amount=float(row.PaidAmount),
            due_date=row.DueDate,
            email=row.Email,
        )
        for row in rows
    ]


def update_student_fee(student_id: int, paid_amount: float = None, due_date=None) -> bool:
    """
    Updates a student's PaidAmount and/or DueDate.
    Only updates fields that were actually provided (partial update).
    Returns True if a row was updated, False if no student matched the ID.
    """
    if paid_amount is None and due_date is None:
        return False

    conn = get_connection()
    cursor = conn.cursor()

    set_clauses = []
    params = []

    if paid_amount is not None:
        set_clauses.append("PaidAmount = ?")
        params.append(paid_amount)

    if due_date is not None:
        set_clauses.append("DueDate = ?")
        params.append(due_date)

    params.append(student_id)

    cursor.execute(
        f"UPDATE Students SET {', '.join(set_clauses)} WHERE StudentID = ?",
        *params,
    )
    conn.commit()

    return cursor.rowcount > 0
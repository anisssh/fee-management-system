from dataclasses import dataclass
from datetime import date


@dataclass
class Student:
    student_id: int
    name: str
    course: str
    total_fee: float
    paid_amount: float
    due_date: date
    email: str = None

    def to_dict(self):
        return {
            "studentId": self.student_id,
            "name": self.name,
            "course": self.course,
            "totalFee": self.total_fee,
            "paidAmount": self.paid_amount,
            "dueDate": self.due_date.isoformat(),
        }
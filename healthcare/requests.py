"""Synthetic healthcare requests and their timing requirements."""

from dataclasses import dataclass, field
from enum import IntEnum
from math import isfinite


class Priority(IntEnum):
    ADMINISTRATIVE = 1
    ROUTINE = 2
    URGENT = 3
    EMERGENCY = 4


RELATIVE_DEADLINE_SECONDS = {
    Priority.EMERGENCY: 2,
    Priority.URGENT: 10,
    Priority.ROUTINE: 60,
    Priority.ADMINISTRATIVE: 120,
}


@dataclass(frozen=True)
class HealthcareRequest:
    request_id: str
    arrival_time: float
    deadline: float
    priority: Priority
    required_key_bits: int = 256
    payload: bytes = field(default=b"", repr=False)

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id must be nonempty")
        if not isfinite(self.arrival_time) or not isfinite(self.deadline):
            raise ValueError("request times must be finite")
        if not 0 <= self.arrival_time <= self.deadline:
            raise ValueError("deadline must be at or after a nonnegative arrival time")
        if not isinstance(self.priority, Priority):
            raise ValueError("priority must be a Priority")
        if type(self.required_key_bits) is not int or self.required_key_bits <= 0:
            raise ValueError("required_key_bits must be a positive integer")

    @property
    def critical(self) -> bool:
        return self.priority == Priority.EMERGENCY

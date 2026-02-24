from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
import io, csv
from fastapi.responses import StreamingResponse

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.schemas.holiday import HolidayCreate, HolidayUpdate, HolidayOut, HolidayBulkDeleteRequest
from app.services import holiday_service

router = APIRouter(prefix="/holidays", tags=["Holidays"])


# ─── LIST ──────────────────────────────────────────────────────────────────────
@router.get("/", response_model=list[HolidayOut])
def list_holidays(
    year: Optional[int] = Query(default=None),
    month: Optional[int] = Query(default=None),
    department: Optional[str] = Query(default=None),
    type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return holiday_service.get_all_holidays(
        db,
        year=year,
        month=month,
        department=department,
        holiday_type=type,
    )


# ─── CREATE ────────────────────────────────────────────────────────────────────
@router.post("/", response_model=HolidayOut, status_code=201)
def create_holiday(
    data: HolidayCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    holiday = holiday_service.create_holiday(db, data)
    return holiday


# ─── GET ONE ───────────────────────────────────────────────────────────────────
@router.get("/{holiday_id}", response_model=HolidayOut)
def get_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    holiday = holiday_service.get_holiday_by_id(db, holiday_id)
    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return holiday


# ─── UPDATE ────────────────────────────────────────────────────────────────────
@router.put("/{holiday_id}", response_model=HolidayOut)
def update_holiday(
    holiday_id: int,
    data: HolidayUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    holiday = holiday_service.update_holiday(db, holiday_id, data)
    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return holiday


# ─── DELETE ONE ────────────────────────────────────────────────────────────────
@router.delete("/{holiday_id}", status_code=204)
def delete_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    success = holiday_service.delete_holiday(db, holiday_id)
    if not success:
        raise HTTPException(status_code=404, detail="Holiday not found")


# ─── BULK DELETE ───────────────────────────────────────────────────────────────
@router.delete("/", status_code=200)
def bulk_delete_holidays(
    payload: HolidayBulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    deleted = holiday_service.bulk_delete_holidays(db, payload.ids)
    return {"deleted": deleted}


# ─── EXPORT CSV ────────────────────────────────────────────────────────────────
@router.get("/export/csv")
def export_holidays_csv(
    year: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    holidays = holiday_service.get_all_holidays(db, year=year)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Holiday Name", "Date", "Type", "Department", "Repeat Yearly"])

    for h in holidays:
        writer.writerow([h.id, h.name, str(h.date), h.type.value, h.department, h.repeat_yearly])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=holidays_{year or 'all'}.csv"},
    )


# ─── CHECK DATE IS HOLIDAY ─────────────────────────────────────────────────────
@router.get("/check/{date_str}")
def check_date_holiday(
    date_str: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns list of holidays on a specific date. Used by frontend attendance calendar."""
    from datetime import date as date_type
    try:
        target = date_type.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    holidays = holiday_service.get_holidays_for_date(db, target)
    return [HolidayOut.model_validate(h) for h in holidays]
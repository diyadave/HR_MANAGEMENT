from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database.session import get_db
from app.core.dependencies import get_current_user, get_current_admin
from app.models.user import User
from app.models.research import (
    ResearchFile,
    ResearchColumn,
    ResearchRow,
    ResearchCell,
    ResearchColumnPermission,
    ResearchDocument,
    ResearchDocumentPermission
)
from app.schemas.research import ResearchFileCreate, ResearchFileOut, CellUpdate


router = APIRouter(prefix="/research", tags=["Research"])

@router.post("/files", response_model=ResearchFileOut)
def create_file(
    payload: ResearchFileCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    file = ResearchFile(
        name=payload.name,
        type=payload.type,
        created_by=admin.id
    )

    db.add(file)
    db.commit()
    db.refresh(file)

    # =========================
    # EXCEL LOGIC
    # =========================
    if payload.type == "excel":

        if not payload.rows or not payload.columns:
            raise HTTPException(status_code=400, detail="Rows and columns required")

        columns = []
        for i in range(payload.columns):
            col = ResearchColumn(
                file_id=file.id,
                column_name=f"Column {i+1}",
                column_order=i+1
            )
            db.add(col)
            columns.append(col)

        db.commit()

        for r in range(payload.rows):
            row = ResearchRow(
                file_id=file.id,
                row_number=r+1
            )
            db.add(row)
            db.commit()
            db.refresh(row)

            for col in columns:
                cell = ResearchCell(
                    row_id=row.id,
                    column_id=col.id,
                    value=""
                )
                db.add(cell)

        db.commit()

    # =========================
    # DOCUMENT LOGIC
    # =========================
    if payload.type == "document":

        if not payload.title:
            raise HTTPException(status_code=400, detail="Title required")

        doc = ResearchDocument(
            file_id=file.id,
            title=payload.title,
            content=payload.content,
            visibility=payload.visibility
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        if payload.visibility == "selected":
            for uid in (payload.user_ids or []):
                db.add(ResearchDocumentPermission(document_id=doc.id, user_id=uid))
            db.commit()

    return file


# =========================
# GET FILES
# CHANGED: employees see only files they have access to
# =========================
@router.get("/files", response_model=List[ResearchFileOut])
def get_files(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # Admin: return all files (unchanged)
    if user.role == "admin":
        return db.query(ResearchFile).all()

    # Employee: collect file IDs accessible via column or document permissions
    accessible_ids = set()

    # 1. Excel files: any column where employee has can_view
    col_perms = db.query(ResearchColumnPermission).filter(
        ResearchColumnPermission.user_id == user.id,
        ResearchColumnPermission.can_view == True
    ).all()
    for cp in col_perms:
        col = db.query(ResearchColumn).filter(ResearchColumn.id == cp.column_id).first()
        if col:
            accessible_ids.add(col.file_id)

    # 2. Documents: visibility=everyone, or selected + employee has a permission record
    for doc in db.query(ResearchDocument).all():
        if doc.visibility == "everyone":
            accessible_ids.add(doc.file_id)
        elif doc.visibility == "selected":
            dp = db.query(ResearchDocumentPermission).filter(
                ResearchDocumentPermission.document_id == doc.id,
                ResearchDocumentPermission.user_id == user.id
            ).first()
            if dp:
                accessible_ids.add(doc.file_id)
        # visibility == "admin" → never accessible to employees

    if not accessible_ids:
        return []

    return db.query(ResearchFile).filter(ResearchFile.id.in_(accessible_ids)).all()


# =========================
# GET FILE DETAIL
# CHANGED: added role, can_edit per cell/column, columns filtered for employees
# =========================
@router.get("/files/{file_id}")
def get_file_detail(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    file = db.query(ResearchFile).filter(ResearchFile.id == file_id).first()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    # =========================
    # EXCEL FILE
    # =========================
    if file.type == "excel":

        all_columns = db.query(ResearchColumn).filter(
            ResearchColumn.file_id == file.id
        ).order_by(ResearchColumn.column_order).all()

        rows = db.query(ResearchRow).filter(
            ResearchRow.file_id == file.id
        ).order_by(ResearchRow.row_number).all()

        # Build permission map for this employee: column_id → perm record
        # Skipped entirely for admin (admin always has full access)
        col_perm_map = {}
        if user.role != "admin":
            for p in db.query(ResearchColumnPermission).filter(
                ResearchColumnPermission.user_id == user.id
            ).all():
                col_perm_map[p.column_id] = p

        # Build visible columns list, each entry includes can_edit flag
        visible_columns = []
        for col in all_columns:
            if user.role == "admin":
                visible_columns.append({
                    "id":       col.id,
                    "name":     col.column_name,
                    "can_edit": True
                })
            else:
                perm = col_perm_map.get(col.id)
                if perm and perm.can_view:
                    visible_columns.append({
                        "id":       col.id,
                        "name":     col.column_name,
                        "can_edit": bool(perm.can_edit)
                    })

        visible_col_ids = {c["id"] for c in visible_columns}
        if user.role != "admin" and not visible_col_ids:
            raise HTTPException(status_code=403, detail="Access denied")

        result_rows = []
        for row in rows:
            cells = db.query(ResearchCell).filter(
                ResearchCell.row_id == row.id
            ).all()

            row_data = []
            for cell in cells:
                if cell.column_id not in visible_col_ids:
                    continue

                if user.role == "admin":
                    can_edit = True
                else:
                    perm = col_perm_map.get(cell.column_id)
                    can_edit = bool(perm and perm.can_edit)

                row_data.append({
                    "cell_id":   cell.id,
                    "column_id": cell.column_id,
                    "value":     cell.value,
                    "can_edit":  can_edit
                })

            result_rows.append({
                "row_id":     row.id,
                "row_number": row.row_number,
                "cells":      row_data
            })

        return {
            "id":      file.id,
            "name":    file.name,
            "type":    file.type,
            "role":    user.role,
            "columns": visible_columns,
            "rows":    result_rows
        }

    # =========================
    # DOCUMENT FILE
    # =========================
    if file.type == "document":

        doc = db.query(ResearchDocument).filter(
            ResearchDocument.file_id == file.id
        ).first()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Access control (unchanged)
        if doc.visibility == "admin" and user.role != "admin":
            raise HTTPException(status_code=403, detail="Access denied")

        if doc.visibility == "selected" and user.role != "admin":
            perm = db.query(ResearchDocumentPermission).filter(
                ResearchDocumentPermission.document_id == doc.id,
                ResearchDocumentPermission.user_id == user.id
            ).first()
            if not perm:
                raise HTTPException(status_code=403, detail="Access denied")

        # Determine edit permission
        if user.role == "admin":
            can_edit_doc = True
        else:
            doc_perm = db.query(ResearchDocumentPermission).filter(
                ResearchDocumentPermission.document_id == doc.id,
                ResearchDocumentPermission.user_id == user.id
            ).first()
            can_edit_doc = bool(doc_perm)

        return {
            "id":         file.id,
            "name":       file.name,
            "type":       file.type,
            "role":       user.role,
            "doc_id":     doc.id,
            "title":      doc.title,
            "content":    doc.content,
            "visibility": doc.visibility,
            "can_edit":   can_edit_doc
        }


# =========================
# ADD ROW TO EXCEL FILE
# (unchanged)
# =========================
@router.post("/files/{file_id}/rows")
def add_row(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    file = db.query(ResearchFile).filter(ResearchFile.id == file_id).first()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    if file.type != "excel":
        raise HTTPException(status_code=400, detail="Not an excel file")

    existing_rows = db.query(ResearchRow).filter(
        ResearchRow.file_id == file_id
    ).order_by(ResearchRow.row_number.desc()).all()

    next_number = (existing_rows[0].row_number + 1) if existing_rows else 1

    new_row = ResearchRow(
        file_id=file_id,
        row_number=next_number
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)

    columns = db.query(ResearchColumn).filter(ResearchColumn.file_id == file_id).all()
    for col in columns:
        cell = ResearchCell(
            row_id=new_row.id,
            column_id=col.id,
            value=""
        )
        db.add(cell)

    db.commit()

    return {"message": "Row added", "row_id": new_row.id, "row_number": new_row.row_number}


# =========================
# DELETE ROW FROM EXCEL FILE
# =========================
@router.delete("/rows/{row_id}")
def delete_row(
    row_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    row = db.query(ResearchRow).filter(ResearchRow.id == row_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Row not found")

    file_id = row.file_id

    # Delete row cells explicitly for DB engines where FK cascade may not be enforced.
    db.query(ResearchCell).filter(ResearchCell.row_id == row_id).delete()
    db.delete(row)
    db.flush()

    # Keep row numbers contiguous after delete.
    rows = db.query(ResearchRow).filter(
        ResearchRow.file_id == file_id
    ).order_by(ResearchRow.row_number.asc(), ResearchRow.id.asc()).all()

    for index, r in enumerate(rows, start=1):
        r.row_number = index

    db.commit()
    return {"message": "Row deleted", "file_id": file_id}


# =========================
# ADD COLUMN TO EXCEL FILE
# (unchanged)
# =========================
@router.post("/files/{file_id}/columns")
def add_column(
    file_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    file = db.query(ResearchFile).filter(ResearchFile.id == file_id).first()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    if file.type != "excel":
        raise HTTPException(status_code=400, detail="Not an excel file")

    existing_cols = db.query(ResearchColumn).filter(
        ResearchColumn.file_id == file_id
    ).order_by(ResearchColumn.column_order.desc()).all()

    next_order = (existing_cols[0].column_order + 1) if existing_cols else 1

    col_name = payload.get("name") or f"Column {next_order}"

    new_col = ResearchColumn(
        file_id=file_id,
        column_name=col_name,
        column_order=next_order
    )
    db.add(new_col)
    db.commit()
    db.refresh(new_col)

    rows = db.query(ResearchRow).filter(ResearchRow.file_id == file_id).all()
    for row in rows:
        cell = ResearchCell(
            row_id=row.id,
            column_id=new_col.id,
            value=""
        )
        db.add(cell)

    db.commit()

    return {"message": "Column added", "column_id": new_col.id, "column_name": new_col.column_name}


# =========================
# UPDATE CELL
# (unchanged)
# =========================
@router.put("/cells/{cell_id}")
def update_cell(
    cell_id: int,
    payload: CellUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    cell = db.query(ResearchCell).filter(ResearchCell.id == cell_id).first()

    if not cell:
        raise HTTPException(status_code=404, detail="Cell not found")

    if user.role != "admin":
        permission = db.query(ResearchColumnPermission).filter(
            ResearchColumnPermission.column_id == cell.column_id,
            ResearchColumnPermission.user_id == user.id,
            ResearchColumnPermission.can_edit == True
        ).first()

        if not permission:
            raise HTTPException(status_code=403, detail="No edit permission")

    cell.value = payload.value
    cell.updated_by = user.id

    db.commit()

    return {"message": "Cell updated"}


# =========================
# UPDATE COLUMN NAME
# (unchanged)
# =========================
@router.put("/columns/{column_id}")
def update_column(
    column_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    column = db.query(ResearchColumn).filter(ResearchColumn.id == column_id).first()

    if not column:
        raise HTTPException(status_code=404, detail="Column not found")

    column.column_name = payload.get("name", column.column_name)
    db.commit()

    return {"message": "Column updated"}


# =========================
# UPDATE COLUMN PERMISSIONS
# (unchanged)
# =========================
@router.post("/columns/{column_id}/permissions")
def update_permissions(
    column_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    column = db.query(ResearchColumn).filter(ResearchColumn.id == column_id).first()
    if not column:
        raise HTTPException(status_code=404, detail="Column not found")

    db.query(ResearchColumnPermission).filter(
        ResearchColumnPermission.column_id == column_id
    ).delete()

    everyone = payload.get("everyone", False)
    if everyone:
        employee_ids = db.query(User.id).filter(User.role == "employee").all()
        for (user_id,) in employee_ids:
            perm = ResearchColumnPermission(
                column_id=column_id,
                user_id=user_id,
                can_view=True,
                can_edit=True
            )
            db.add(perm)
    else:
        for user_id in set(payload.get("user_ids", [])):
            perm = ResearchColumnPermission(
                column_id=column_id,
                user_id=user_id,
                can_view=True,
                can_edit=True
            )
            db.add(perm)

    db.commit()

    return {"message": "Permissions updated"}


# =========================
# DELETE COLUMN
# (unchanged)
# =========================
@router.delete("/columns/{column_id}")
def delete_column(
    column_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    db.query(ResearchColumn).filter(ResearchColumn.id == column_id).delete()
    db.commit()

    return {"message": "Column deleted"}


# =========================
# UPDATE DOCUMENT (with permissions)
# CHANGED: employees cannot change visibility or user_ids
# =========================
@router.put("/documents/{document_id}")
def update_document(
    document_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    doc = db.query(ResearchDocument).filter(ResearchDocument.id == document_id).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Only admin or permitted users can edit
    if user.role != "admin":
        perm = db.query(ResearchDocumentPermission).filter(
            ResearchDocumentPermission.document_id == doc.id,
            ResearchDocumentPermission.user_id == user.id
        ).first()
        if not perm:
            raise HTTPException(status_code=403, detail="No edit permission")

    # title and content: both roles can update
    if "title" in payload:
        doc.title = payload["title"]

    if "content" in payload:
        doc.content = payload["content"]

    # visibility and permission assignments: admin only
    if user.role == "admin":
        if "visibility" in payload:
            doc.visibility = payload["visibility"]

    if hasattr(doc, "updated_by"):
        doc.updated_by = user.id

    db.commit()

    # Permission record management: admin only
    if user.role == "admin":
        if payload.get("visibility") == "selected":
            db.query(ResearchDocumentPermission).filter(
                ResearchDocumentPermission.document_id == doc.id
            ).delete()
            for uid in payload.get("user_ids", []):
                dp = ResearchDocumentPermission(
                    document_id=doc.id,
                    user_id=uid
                )
                db.add(dp)
            db.commit()
        elif payload.get("visibility") in ("everyone", "admin"):
            db.query(ResearchDocumentPermission).filter(
                ResearchDocumentPermission.document_id == doc.id
            ).delete()
            db.commit()

    return {"message": "Document updated"}

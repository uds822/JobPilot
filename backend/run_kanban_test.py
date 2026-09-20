from app.database.database import SessionLocal
from app.models.applications import Application
from app.models.companies import Company
from app.models.jobs import Job
from app.models.users import User
from app.services.application import get_user_applications_paginated, get_kanban_board_data
import uuid


def run_tests():
    db = SessionLocal()
    print("Starting Kanban Board & Pagination Tests...")
    test_user_ids = []
    test_company_ids = []

    try:
        # Test 1: Empty board
        uid = f"test_user_{uuid.uuid4().hex[:6]}"
        user = User(username=uid, email=f"{uid}@example.com", password_hash="pw")
        db.add(user)
        db.commit()
        db.refresh(user)
        test_user_ids.append(user.id)

        empty_kanban = get_kanban_board_data(db, user, limit_per_status=20)
        assert empty_kanban["applied"]["total"] == 0
        assert empty_kanban["applied"]["items"] == []
        assert empty_kanban["applied"]["has_more"] is False
        print("[PASS] Test 1: Empty Kanban board returns 0 total count and empty items")

        # Test 2: 250 Applications Pagination & Limit Capping
        company = Company(name=f"Co_{uid}")
        db.add(company)
        db.commit()
        db.refresh(company)
        test_company_ids.append(company.id)

        for i in range(250):
            j = Job(title=f"Dev #{i}", company_id=company.id)
            db.add(j)
            db.flush()
            app = Application(user_id=user.id, job_id=j.id, status="APPLIED", notes=f"Note #{i}")
            db.add(app)
        db.commit()

        # Batch 1 (limit=20, offset=0)
        res1 = get_user_applications_paginated(db, user, status="APPLIED", limit=20, offset=0)
        assert res1["total"] == 250
        assert len(res1["items"]) == 20
        assert res1["has_more"] is True
        print("[PASS] Test 2.1: 250 total count accurately returned with has_more=True")

        # Capping test: limit=500 should be capped at 100
        res_cap = get_user_applications_paginated(db, user, status="APPLIED", limit=500, offset=0)
        assert res_cap["limit"] == 100
        assert len(res_cap["items"]) == 100
        assert res_cap["has_more"] is True
        print("[PASS] Test 2.2: Server capped limit=500 request to maximum 100 items")

        # End batch offset=240
        res_end = get_user_applications_paginated(db, user, status="APPLIED", limit=20, offset=240)
        assert len(res_end["items"]) == 10
        assert res_end["has_more"] is False
        print("[PASS] Test 2.3: Final pagination batch offset=240 correctly returns remaining 10 items with has_more=False")

        # Test 3: User Isolation
        uid2 = f"test_user_{uuid.uuid4().hex[:6]}"
        user2 = User(username=uid2, email=f"{uid2}@example.com", password_hash="pw")
        db.add(user2)
        db.commit()
        db.refresh(user2)
        test_user_ids.append(user2.id)

        j2 = Job(title="User 2 Job", company_id=company.id)
        db.add(j2)
        db.flush()
        db.add(Application(user_id=user2.id, job_id=j2.id, status="OFFERED"))
        db.commit()

        u2_kanban = get_kanban_board_data(db, user2)
        assert u2_kanban["applied"]["total"] == 0
        assert u2_kanban["offered"]["total"] == 1
        print("[PASS] Test 3: User isolation strictly enforced (User 2 sees only User 2 data)")

        print("\nALL BACKEND KANBAN & PAGINATION TESTS PASSED CLEANLY!")

    finally:
        # Clean up test data
        try:
            for uid in test_user_ids:
                db.query(Application).filter(Application.user_id == uid).delete(synchronize_session=False)
                db.query(User).filter(User.id == uid).delete(synchronize_session=False)

            for cid in test_company_ids:
                jobs = db.query(Job).filter(Job.company_id == cid).all()
                for j in jobs:
                    db.query(Application).filter(Application.job_id == j.id).delete(synchronize_session=False)
                    db.delete(j)
                db.flush()
                db.query(Company).filter(Company.id == cid).delete(synchronize_session=False)

            db.commit()
            print("[INFO] Test data successfully cleaned up from database.")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Failed to clean up test data: {e}")
        finally:
            db.close()


if __name__ == "__main__":
    run_tests()



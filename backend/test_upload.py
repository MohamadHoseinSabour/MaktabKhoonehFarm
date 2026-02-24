import os
import sys

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.services.upload.firefox_navigator import FirefoxUploadNavigator
from app.models.course import Course
from app.models.episode import Episode

def test_course_creation():
    db = SessionLocal()
    try:
        navigator = FirefoxUploadNavigator(db)
        
        # Create a dummy course that doesn't exist
        dummy_course = Course(
            id=99999,
            title_fa="دوره آزمایشی تست اتوماسیون (حذف شود)",
            title_en="Test Automation Course (Delete)",
            slug="test-automation-course-delete-99"
        )
        
        dummy_episode = Episode(
            id=99999,
            course_id=99999,
            episode_number=1,
            title_fa="جلسه اول تست",
            title_en="Test Episode 1"
        )
        
        print(f"Triggering upload for non-existent course: '{dummy_course.title_fa}'")
        print("A Firefox window should open and attempt to create the draft...")
        
        # Keep browser open to visually verify
        result = navigator.open_course_episode_page(
            course=dummy_course,
            episode=dummy_episode,
            keep_browser_open=True
        )
        
        print("\nTest Result:")
        print(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nError occurred: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_course_creation()

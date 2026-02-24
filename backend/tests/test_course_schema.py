import pytest
from pydantic import ValidationError

from app.schemas.course import CourseCreate


def test_course_create_trims_source_url():
    payload = CourseCreate(source_url='  https://git.ir/sample-course/  ', debug_mode=True)
    assert str(payload.source_url) == 'https://git.ir/sample-course/'


def test_course_create_normalizes_duplicated_source_url():
    payload = CourseCreate(
        source_url='https://git.ir/sample-course/https://git.ir/sample-course/',
        debug_mode=True,
    )
    assert str(payload.source_url) == 'https://git.ir/sample-course/'


def test_course_create_rejects_multiple_different_urls():
    with pytest.raises(ValidationError):
        CourseCreate(
            source_url='https://git.ir/sample-course/https://en.git.ir/another-course/',
            debug_mode=True,
        )

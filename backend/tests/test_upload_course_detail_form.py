import sys
from types import ModuleType, SimpleNamespace

import pytest
import requests
from bs4 import BeautifulSoup


def _install_selenium_stub() -> None:
    if 'selenium' in sys.modules:
        return

    selenium = ModuleType('selenium')
    webdriver = ModuleType('selenium.webdriver')
    common = ModuleType('selenium.common')
    exceptions = ModuleType('selenium.common.exceptions')
    by = ModuleType('selenium.webdriver.common.by')
    keys = ModuleType('selenium.webdriver.common.keys')
    firefox_options = ModuleType('selenium.webdriver.firefox.options')
    firefox_service = ModuleType('selenium.webdriver.firefox.service')
    support_ec = ModuleType('selenium.webdriver.support.expected_conditions')
    support_ui = ModuleType('selenium.webdriver.support.ui')

    class _DummyException(Exception):
        pass

    class _By:
        CSS_SELECTOR = 'css selector'
        TAG_NAME = 'tag name'

    class _Keys:
        CONTROL = 'CONTROL'
        DELETE = 'DELETE'
        ENTER = 'ENTER'

    class _Firefox:
        pass

    class _FirefoxOptions:
        pass

    class _FirefoxService:
        pass

    class _WebDriverWait:
        def __init__(self, *args, **kwargs):
            pass

    webdriver.Firefox = _Firefox
    webdriver.FirefoxOptions = _FirefoxOptions
    exceptions.TimeoutException = _DummyException
    exceptions.WebDriverException = _DummyException
    by.By = _By
    keys.Keys = _Keys
    firefox_options.Options = _FirefoxOptions
    firefox_service.Service = _FirefoxService
    support_ui.WebDriverWait = _WebDriverWait
    support_ec.presence_of_element_located = lambda *args, **kwargs: None
    support_ec.element_to_be_clickable = lambda *args, **kwargs: None

    selenium.webdriver = webdriver
    sys.modules['selenium'] = selenium
    sys.modules['selenium.webdriver'] = webdriver
    sys.modules['selenium.common'] = common
    sys.modules['selenium.common.exceptions'] = exceptions
    sys.modules['selenium.webdriver.common.by'] = by
    sys.modules['selenium.webdriver.common.keys'] = keys
    sys.modules['selenium.webdriver.firefox.options'] = firefox_options
    sys.modules['selenium.webdriver.firefox.service'] = firefox_service
    sys.modules['selenium.webdriver.support'] = ModuleType('selenium.webdriver.support')
    sys.modules['selenium.webdriver.support.expected_conditions'] = support_ec
    sys.modules['selenium.webdriver.support.ui'] = support_ui


def _install_backend_import_stubs() -> None:
    if 'sqlalchemy' not in sys.modules:
        sqlalchemy = ModuleType('sqlalchemy')
        orm = ModuleType('sqlalchemy.orm')

        class _Session:
            pass

        orm.Session = _Session
        sqlalchemy.orm = orm
        sys.modules['sqlalchemy'] = sqlalchemy
        sys.modules['sqlalchemy.orm'] = orm

    for module_name, class_name in (
        ('app.models.course', 'Course'),
        ('app.models.episode', 'Episode'),
        ('app.models.setting', 'Setting'),
    ):
        if module_name in sys.modules:
            continue
        module = ModuleType(module_name)
        setattr(module, class_name, type(class_name, (), {}))
        sys.modules[module_name] = module


_install_selenium_stub()
_install_backend_import_stubs()

from app.services.upload.firefox_navigator import MaktabMarketplaceClient, UploadConfigurationError


def _client() -> MaktabMarketplaceClient:
    client = object.__new__(MaktabMarketplaceClient)
    client.base_url = 'https://maktabkhooneh.org'
    return client


def test_course_detail_form_fields_include_english_title_and_learning_goals():
    soup = BeautifulSoup(
        """
        <html><body>
        <form method="post">
          <input type="hidden" name="csrfmiddlewaretoken" value="old-token" />
          <input type="text" name="title" value="عنوان فارسی" />
          <input type="text" name="english_title" value="" required />
          <textarea name="description"></textarea>
          <textarea name="prerequisite_description"></textarea>
          <input type="text" name="learning_goals" value="" />
          <input type="text" name="learning_goals" value="" />
          <select name="prerequisites" multiple>
            <option value="1" selected>One</option>
            <option value="2">Two</option>
            <option value="3" selected>Three</option>
          </select>
        </form>
        </body></html>
        """,
        'html.parser',
    )
    course = SimpleNamespace(
        title_en='Prompt Engineering Fundamentals',
        title_fa='مبانی پرامپت نویسی',
        slug='prompt-engineering-fundamentals',
        description_en='Learn prompt design with practical examples.',
        description_fa='یادگیری طراحی پرامپت با مثال های عملی.',
        extra_metadata={},
    )

    fields = _client()._course_detail_form_fields(soup, 'new-token', course)
    payload = [(name, value[1]) for name, value in fields]

    assert ('csrfmiddlewaretoken', 'new-token') in payload
    assert ('english_title', 'Prompt Engineering Fundamentals') in payload
    assert ('title', 'عنوان فارسی') in payload
    assert ('description', '<p>یادگیری طراحی پرامپت با مثال های عملی.</p>') in payload
    assert ('prerequisites', '1') in payload
    assert ('prerequisites', '3') in payload

    learning_goals = [value for name, value in payload if name == 'learning_goals']
    assert len(learning_goals) == 4


def test_assert_course_detail_saved_raises_on_validation_errors():
    response = requests.Response()
    response.status_code = 200
    response._content = b"""
    <html><body>
      <ul class=\"errorlist\"><li>This field is required.</li></ul>
    </body></html>
    """
    response.headers['Content-Type'] = 'text/html; charset=utf-8'

    with pytest.raises(UploadConfigurationError, match='validation failed'):
        _client()._assert_course_detail_saved(response, '/marketplace/teacher/course/1/detail/edit')


def test_upload_course_episodes_tolerates_order_sync_failure():
    client = _client()
    client.ensure_course_details = lambda *args, **kwargs: {'teaser': {'result': 'uploaded'}}
    client.ensure_video_chapter = lambda *args, **kwargs: SimpleNamespace(
        id='10',
        title='ویدیو های دوره',
        units_url='https://maktabkhooneh.org/marketplace/teacher/course/1/chapters/10/units/',
        edit_url=None,
    )
    client.upload_episode = lambda *args, **kwargs: {'episode_id': 'ep-1', 'result': 'uploaded'}

    def _raise_sync_error(*args, **kwargs):
        raise UploadConfigurationError('unit order sync failed')

    client._sync_unit_order = _raise_sync_error
    course = SimpleNamespace(title_fa='دوره تست', title_en='Test Course', slug='test-course', episodes=[])
    episode = SimpleNamespace(id='ep-1', episode_number=1, sort_order=1)
    route = SimpleNamespace(course_id='1', source='draft-api')

    result = client.upload_course_episodes(course, [episode], route)

    assert result['ok'] is True
    assert result['results'][0]['result'] == 'uploaded'
    assert result['order_sync']['result'] == 'warning'
    assert 'unit order sync failed' in result['order_sync']['error']


def test_ensure_course_details_tolerates_teaser_failure():
    client = _client()
    client._get_soup = lambda *args, **kwargs: BeautifulSoup('<html><form></form></html>', 'html.parser')
    client._csrf_from_soup = lambda *args, **kwargs: 'csrf'
    client._course_detail_form_fields = lambda *args, **kwargs: [('csrfmiddlewaretoken', (None, 'csrf'))]
    client._course_thumbnail_file_path = lambda *args, **kwargs: None

    response = requests.Response()
    response.status_code = 200
    response._content = b'<html></html>'
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    client._post_form = lambda *args, **kwargs: response
    client._assert_course_detail_saved = lambda *args, **kwargs: None

    def _raise_teaser_error(*args, **kwargs):
        raise UploadConfigurationError('teaser upload failed')

    client._upload_first_episode_as_teaser = _raise_teaser_error
    course = SimpleNamespace()

    result = client.ensure_course_details('1', course, [])

    assert result['form_status_code'] == 200
    assert result['teaser']['result'] == 'warning'
    assert 'teaser upload failed' in result['teaser']['error']

import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.episode import Episode
from app.models.setting import Setting


class UploadAutomationError(Exception):
    pass


class UploadConfigurationError(UploadAutomationError):
    pass


class UploadAuthExpiredError(UploadAutomationError):
    pass


@dataclass
class UploadAutomationConfig:
    headless: bool
    target_url: str
    cookies_json: str
    search_input_selector: str
    course_result_xpath_template: str
    sections_button_xpath: str
    units_button_xpath: str
    login_check_selector: str
    episode_page_indicator_selector: str
    geckodriver_path: str | None


def _parse_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join([f"'{part}'" for part in parts]) + ")"


class FirefoxUploadNavigator:
    PAGE_WAIT_SECONDS = 8
    ELEMENT_WAIT_SECONDS = 5
    FORM_WAIT_SECONDS = 10
    LOGIN_WAIT_SECONDS = 6
    SUBMIT_WAIT_SECONDS = 15
    UPLOAD_PAGE_WAIT_SECONDS = 30
    VIDEO_UPLOAD_WAIT_SECONDS = 1800
    VIDEO_UPLOAD_START_WAIT_SECONDS = 45
    VIDEO_UPLOAD_STABLE_POLLS = 3
    NAV_BACK_WAIT_SECONDS = 15
    TAB_WAIT_SECONDS = 6
    SEARCH_WAIT_SECONDS = 4
    PAGELOAD_TIMEOUT_SECONDS = 30
    PAGE_READY_WAIT_SECONDS = 20
    STEP_PAUSE_SECONDS = 1.2
    UNITS_LIST_WAIT_SECONDS = 15
    DEBUG_BROWSER_POOL_LIMIT = 5
    DEBUG_BROWSER_POOL: list[webdriver.Firefox] = []
    COURSE_UNITS_URL_CACHE: dict[str, str] = {}

    SETTINGS_KEYS = {
        'upload_firefox_headless',
        'upload_target_url',
        'upload_cookies_json',
        'upload_search_input_selector',
        'upload_course_result_xpath_template',
        'upload_sections_button_xpath',
        'upload_units_button_xpath',
        'upload_login_check_selector',
        'upload_episode_page_indicator_selector',
        'upload_firefox_geckodriver_path',
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.config = self._load_config()

    def validate_cookies(self) -> dict[str, Any]:
        driver = self._create_driver()
        try:
            self._open_target_with_cookies(driver)
            self._assert_logged_in(driver)
            return {'valid': True, 'message': 'Cookies are valid and logged-in session is available.'}
        finally:
            driver.quit()

    def open_course_episode_page(
        self,
        course: Course,
        episode: Episode,
        keep_browser_open: bool = False,
        preferred_units_url: str | None = None,
    ) -> dict[str, Any]:
        query = (course.title_fa or course.title_en or course.slug or '').strip()
        if not query:
            raise UploadConfigurationError('Course title is empty and cannot be used for search.')

        driver = self._create_driver()
        try:
            course_key = str(course.id)
            direct_units_url = (preferred_units_url or '').strip() or self.COURSE_UNITS_URL_CACHE.get(course_key)
            self._open_target_with_cookies(driver, landing_url=direct_units_url or None)
            self._assert_logged_in(driver)
            self._wait_for_page_ready(driver)
            self._pause_between_steps()

            if direct_units_url and '/units/' in driver.current_url:
                units_list_url = self._derive_units_list_url(driver.current_url)
                if units_list_url:
                    self.COURSE_UNITS_URL_CACHE[course_key] = units_list_url
                unit_route = self._open_or_create_episode_unit(driver, episode)
                unit_action = unit_route.get('unit_action')
                debug_halt = bool(keep_browser_open and unit_action == 'skip_existing')
                return {
                    'ok': True,
                    'query': query,
                    'current_url': driver.current_url,
                    'headless': self.config.headless,
                    'browser_kept_open': keep_browser_open,
                    'unit_action': unit_action,
                    'matched_unit_title': unit_route.get('matched_title'),
                    'editor_url': unit_route.get('editor_url', driver.current_url),
                    'units_list_url': units_list_url,
                    'used_cached_units_url': True,
                    'skip_existing': unit_action == 'skip_existing',
                    'debug_halt': debug_halt,
                    'should_continue': not debug_halt,
                    'form_filled': bool(unit_route.get('form_filled')),
                    'form_title': unit_route.get('form_title'),
                    'subtitle_attached': bool(unit_route.get('subtitle_attached')),
                    'subtitle_path': unit_route.get('subtitle_path'),
                    'subtitle_missing_reason': unit_route.get('subtitle_missing_reason'),
                }
            if direct_units_url and '/units/' not in driver.current_url:
                driver.get(self.config.target_url)
                self._assert_logged_in(driver)
                self._wait_for_page_ready(driver)
                self._pause_between_steps()

            wait = WebDriverWait(driver, self.PAGE_WAIT_SECONDS)
            search_input = None
            try:
                search_input = WebDriverWait(driver, self.SEARCH_WAIT_SECONDS).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, self.config.search_input_selector))
                )
            except TimeoutException:
                search_input = None

            if search_input is not None:
                search_input.click()
                search_input.send_keys(Keys.CONTROL, 'a')
                search_input.send_keys(Keys.DELETE)
                search_input.send_keys(query)
                search_input.send_keys(Keys.ENTER)

            result_xpath = self._build_result_xpath(query)
            try:
                course_entry = wait.until(EC.element_to_be_clickable((By.XPATH, result_xpath)))
            except TimeoutException as exc:
                if not self._try_click_sections_button(driver):
                    raise UploadConfigurationError(
                        f"Course result not found. result_xpath={result_xpath} current_url={driver.current_url}"
                    ) from exc
            else:
                course_entry.click()
                self._click_sections_button(driver)
            self._assert_logged_in(driver)
            self._click_units_button(driver)
            self._wait_for_units_listing_ready(driver)
            self._pause_between_steps()
            units_list_url = self._derive_units_list_url(driver.current_url)
            if units_list_url:
                self.COURSE_UNITS_URL_CACHE[course_key] = units_list_url
            unit_route = self._open_or_create_episode_unit(driver, episode)

            if self.config.episode_page_indicator_selector:
                try:
                    wait.until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, self.config.episode_page_indicator_selector)
                        )
                    )
                except TimeoutException as exc:
                    raise UploadConfigurationError(
                        f"Episode page indicator not found. selector={self.config.episode_page_indicator_selector} current_url={driver.current_url}"
                    ) from exc

            unit_action = unit_route.get('unit_action')
            debug_halt = bool(keep_browser_open and unit_action == 'skip_existing')
            return {
                'ok': True,
                'query': query,
                'current_url': driver.current_url,
                'headless': self.config.headless,
                'browser_kept_open': keep_browser_open,
                'unit_action': unit_action,
                'matched_unit_title': unit_route.get('matched_title'),
                'editor_url': unit_route.get('editor_url', driver.current_url),
                'units_list_url': units_list_url,
                'used_cached_units_url': False,
                'skip_existing': unit_action == 'skip_existing',
                'debug_halt': debug_halt,
                'should_continue': not debug_halt,
                'form_filled': bool(unit_route.get('form_filled')),
                'form_title': unit_route.get('form_title'),
                'subtitle_attached': bool(unit_route.get('subtitle_attached')),
                'subtitle_path': unit_route.get('subtitle_path'),
                'subtitle_missing_reason': unit_route.get('subtitle_missing_reason'),
            }
        finally:
            if keep_browser_open:
                self._retain_debug_browser(driver)
            else:
                driver.quit()

    def upload_course_episodes(
        self,
        course: Course,
        episodes: list[Episode],
        keep_browser_open: bool = False,
        preferred_units_url: str | None = None,
    ) -> dict[str, Any]:
        if not episodes:
            return {
                'ok': True,
                'query': (course.title_fa or course.title_en or course.slug or '').strip(),
                'headless': self.config.headless,
                'results': [],
                'processed_count': 0,
                'units_list_url': None,
                'used_cached_units_url': False,
            }

        query = (course.title_fa or course.title_en or course.slug or '').strip()
        if not query:
            raise UploadConfigurationError('Course title is empty and cannot be used for search.')

        driver = self._create_driver()
        try:
            course_key = str(course.id)
            direct_units_url = (preferred_units_url or '').strip() or self.COURSE_UNITS_URL_CACHE.get(course_key)
            self._open_target_with_cookies(driver, landing_url=direct_units_url or None)
            self._assert_logged_in(driver)
            self._wait_for_page_ready(driver)
            self._pause_between_steps()

            used_cached_units_url = False
            units_list_url = None
            if direct_units_url and '/units/' in driver.current_url:
                used_cached_units_url = True
                units_list_url = self._derive_units_list_url(driver.current_url)
            else:
                if direct_units_url and '/units/' not in driver.current_url:
                    driver.get(self.config.target_url)
                    self._assert_logged_in(driver)
                    self._wait_for_page_ready(driver)
                    self._pause_between_steps()

                wait = WebDriverWait(driver, self.PAGE_WAIT_SECONDS)
                search_input = None
                try:
                    search_input = WebDriverWait(driver, self.SEARCH_WAIT_SECONDS).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, self.config.search_input_selector))
                    )
                except TimeoutException:
                    search_input = None

                if search_input is not None:
                    search_input.click()
                    search_input.send_keys(Keys.CONTROL, 'a')
                    search_input.send_keys(Keys.DELETE)
                    search_input.send_keys(query)
                    search_input.send_keys(Keys.ENTER)

                result_xpath = self._build_result_xpath(query)
                try:
                    course_entry = wait.until(EC.element_to_be_clickable((By.XPATH, result_xpath)))
                except TimeoutException as exc:
                    if not self._try_click_sections_button(driver):
                        raise UploadConfigurationError(
                            f"Course result not found. result_xpath={result_xpath} current_url={driver.current_url}"
                        ) from exc
                else:
                    course_entry.click()
                    self._click_sections_button(driver)
                self._assert_logged_in(driver)
                self._click_units_button(driver)
                self._wait_for_units_listing_ready(driver)
                self._pause_between_steps()
                units_list_url = self._derive_units_list_url(driver.current_url)

            if units_list_url:
                self.COURSE_UNITS_URL_CACHE[course_key] = units_list_url

            results: list[dict[str, Any]] = []
            total = len(episodes)
            for index, episode in enumerate(episodes):
                should_return_to_list = index < total - 1
                try:
                    item = self._upload_episode_from_units_page(
                        driver,
                        episode,
                        should_return_to_list=should_return_to_list,
                        units_list_url=units_list_url,
                    )
                except UploadAuthExpiredError:
                    raise
                except UploadAutomationError as exc:
                    item = {
                        'episode_id': str(episode.id),
                        'episode_number': episode.episode_number,
                        'episode_title': (episode.title_fa or episode.title_en or '').strip(),
                        'result': 'error',
                        'unit_action': None,
                        'error': str(exc),
                        'form_filled': False,
                        'form_title': None,
                        'subtitle_attached': False,
                        'subtitle_path': None,
                        'subtitle_missing_reason': None,
                        'video_file': None,
                        'progress': None,
                        'returned_to_units': False,
                        'units_list_url': units_list_url,
                        'current_url': driver.current_url,
                    }
                    if should_return_to_list and units_list_url:
                        try:
                            driver.get(units_list_url)
                            if '/units/' in driver.current_url:
                                self._wait_for_page_ready(driver)
                                self._wait_for_units_listing_ready(driver)
                                self._pause_between_steps()
                                item['returned_to_units'] = True
                                item['current_url'] = driver.current_url
                        except Exception:
                            pass
                results.append(item)
                if item.get('units_list_url') and not units_list_url:
                    units_list_url = str(item.get('units_list_url'))
                    self.COURSE_UNITS_URL_CACHE[course_key] = units_list_url

            return {
                'ok': True,
                'query': query,
                'headless': self.config.headless,
                'current_url': driver.current_url,
                'browser_kept_open': keep_browser_open,
                'results': results,
                'processed_count': len(results),
                'units_list_url': units_list_url,
                'used_cached_units_url': used_cached_units_url,
            }
        finally:
            if keep_browser_open:
                self._retain_debug_browser(driver)
            else:
                driver.quit()

    def _pause_between_steps(self, seconds: float | None = None) -> None:
        time.sleep(seconds if seconds is not None else self.STEP_PAUSE_SECONDS)

    def _wait_for_page_ready(self, driver: webdriver.Firefox, timeout: float | None = None) -> None:
        wait_seconds = timeout if timeout is not None else self.PAGE_READY_WAIT_SECONDS
        try:
            WebDriverWait(driver, wait_seconds, poll_frequency=0.2).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
        except (TimeoutException, WebDriverException):
            return

    def _wait_for_units_listing_ready(self, driver: webdriver.Firefox) -> None:
        if '/units/' not in (driver.current_url or ''):
            return

        try:
            WebDriverWait(driver, self.UNITS_LIST_WAIT_SECONDS, poll_frequency=0.3).until(
                lambda d: bool(d.find_elements(By.CSS_SELECTOR, 'li.item'))
                or bool(d.find_elements(By.XPATH, "//a[contains(@href, 'unit_type=lecture')]"))
            )
        except TimeoutException:
            return

    def _click_sections_button(self, driver: webdriver.Firefox) -> None:
        if self._try_click_sections_button(driver):
            return

        raise UploadConfigurationError(
            f"Sections button not found. sections_xpath={self.config.sections_button_xpath} current_url={driver.current_url}"
        )

    def _try_click_sections_button(self, driver: webdriver.Firefox) -> bool:
        before_handles = set(driver.window_handles)
        short_wait = WebDriverWait(driver, self.ELEMENT_WAIT_SECONDS)
        locators = [
            (By.XPATH, self.config.sections_button_xpath),
            (
                By.XPATH,
                "//a[contains(@href, '/chapters/') and contains(normalize-space(.), 'ÙØµÙ„') and contains(normalize-space(.), 'Ø¬Ù„Ø³')]",
            ),
            (By.XPATH, "//a[contains(@href, '/chapters/')]"),
        ]

        for by, value in locators:
            try:
                button = short_wait.until(EC.element_to_be_clickable((by, value)))
            except TimeoutException:
                continue

            try:
                button.click()
            except WebDriverException:
                driver.execute_script('arguments[0].click();', button)

            self._switch_to_new_tab(driver, before_handles)
            return True

        return False

    def _switch_to_new_tab(self, driver: webdriver.Firefox, before_handles: set[str]) -> None:
        try:
            WebDriverWait(driver, self.TAB_WAIT_SECONDS).until(lambda d: len(d.window_handles) > len(before_handles))
        except TimeoutException:
            return

        after_handles = set(driver.window_handles)
        new_handles = [handle for handle in after_handles if handle not in before_handles]
        if new_handles:
            driver.switch_to.window(new_handles[-1])
            self._wait_for_page_ready(driver)
            self._pause_between_steps()

    def _click_units_button(self, driver: webdriver.Firefox) -> None:
        before_handles = set(driver.window_handles)
        locators = [
            (By.XPATH, self.config.units_button_xpath),
            (By.XPATH, "//a[contains(@href, '/units/')]"),
        ]
        short_wait = WebDriverWait(driver, self.ELEMENT_WAIT_SECONDS)

        for by, value in locators:
            try:
                button = short_wait.until(EC.element_to_be_clickable((by, value)))
            except TimeoutException:
                continue

            try:
                button.click()
            except WebDriverException:
                driver.execute_script('arguments[0].click();', button)

            self._switch_to_new_tab(driver, before_handles)
            if self._is_login_url(driver.current_url):
                raise UploadAuthExpiredError(
                    self._auth_expired_message(driver.current_url)
                )
            try:
                WebDriverWait(driver, self.ELEMENT_WAIT_SECONDS).until(lambda d: '/units/' in d.current_url)
            except TimeoutException:
                raise UploadConfigurationError(
                    f"Units link clicked but units page did not open. current_url={driver.current_url}"
                )
            self._wait_for_page_ready(driver)
            self._wait_for_units_listing_ready(driver)
            self._pause_between_steps()
            return

        if self._is_login_url(driver.current_url):
            raise UploadAuthExpiredError(
                self._auth_expired_message(driver.current_url)
            )
        raise UploadConfigurationError(
            f"Units edit link not found. units_xpath={self.config.units_button_xpath} current_url={driver.current_url}"
        )

    def _open_or_create_episode_unit(self, driver: webdriver.Firefox, episode: Episode) -> dict[str, Any]:
        self._wait_for_units_listing_ready(driver)
        self._pause_between_steps(0.6)
        candidates = [self._normalize_title_text(item) for item in self._episode_title_candidates(episode)]
        candidates = [item for item in candidates if item]

        rows = driver.find_elements(By.CSS_SELECTOR, 'li.item')
        for row in rows:
            title_elements = row.find_elements(By.CSS_SELECTOR, '.ellipsis')
            if not title_elements:
                continue

            raw_title = (title_elements[0].get_attribute('title') or title_elements[0].text or '').strip()
            row_title = self._normalize_title_text(raw_title)
            if not row_title:
                continue
            if not any(self._titles_match(row_title, candidate) for candidate in candidates):
                continue

            detail_links = row.find_elements(By.XPATH, ".//a[contains(@href, '/units/edit/?unit_id=')]")
            detail_href = detail_links[0].get_attribute('href') if detail_links else None

            return {
                'unit_action': 'skip_existing',
                'matched_title': raw_title,
                'editor_url': urljoin(driver.current_url, detail_href) if detail_href else None,
                'form_filled': False,
                'form_title': None,
                'subtitle_attached': False,
                'subtitle_path': None,
                'subtitle_missing_reason': 'existing_unit',
            }

        create_locators = [
            (By.XPATH, "//a[contains(@href, 'unit_type=lecture') and contains(normalize-space(.), 'جلسه')]"),
            (By.XPATH, "//a[contains(@href, 'unit_type=lecture')]"),
        ]
        wait = WebDriverWait(driver, self.ELEMENT_WAIT_SECONDS)
        for by, value in create_locators:
            try:
                create_button = wait.until(EC.element_to_be_clickable((by, value)))
            except TimeoutException:
                continue

            before_handles = set(driver.window_handles)
            self._safe_click(driver, create_button)
            self._switch_to_new_tab(driver, before_handles)
            if self._is_login_url(driver.current_url):
                raise UploadAuthExpiredError(self._auth_expired_message(driver.current_url))
            try:
                WebDriverWait(driver, self.ELEMENT_WAIT_SECONDS).until(
                    lambda d: '/units/edit/' in d.current_url or 'unit_type=lecture' in d.current_url
                )
            except TimeoutException as exc:
                raise UploadConfigurationError(
                    f'Create lecture page did not open. current_url={driver.current_url}'
                ) from exc
            self._wait_for_page_ready(driver)
            self._pause_between_steps()
            form_result = self._populate_episode_form(driver, episode)

            return {
                'unit_action': 'create_new',
                'matched_title': None,
                'editor_url': driver.current_url,
                'form_filled': form_result.get('form_filled', False),
                'form_title': form_result.get('form_title'),
                'subtitle_attached': form_result.get('subtitle_attached', False),
                'subtitle_path': form_result.get('subtitle_path'),
                'subtitle_missing_reason': form_result.get('subtitle_missing_reason'),
            }

        raise UploadConfigurationError(
            f'No matching unit found and create button is missing. current_url={driver.current_url}'
        )

    def _upload_episode_from_units_page(
        self,
        driver: webdriver.Firefox,
        episode: Episode,
        should_return_to_list: bool,
        units_list_url: str | None,
    ) -> dict[str, Any]:
        outcome: dict[str, Any] = {
            'episode_id': str(episode.id),
            'episode_number': episode.episode_number,
            'episode_title': (episode.title_fa or episode.title_en or '').strip(),
            'result': 'error',
            'unit_action': None,
            'error': None,
            'form_filled': False,
            'form_title': None,
            'subtitle_attached': False,
            'subtitle_path': None,
            'subtitle_missing_reason': None,
            'video_file': None,
            'progress': None,
            'returned_to_units': False,
            'units_list_url': units_list_url,
            'current_url': driver.current_url,
        }

        unit_route = self._open_or_create_episode_unit(driver, episode)
        unit_action = unit_route.get('unit_action')
        outcome['unit_action'] = unit_action
        outcome['current_url'] = driver.current_url
        outcome['form_filled'] = bool(unit_route.get('form_filled'))
        outcome['form_title'] = unit_route.get('form_title')
        outcome['subtitle_attached'] = bool(unit_route.get('subtitle_attached'))
        outcome['subtitle_path'] = unit_route.get('subtitle_path')
        outcome['subtitle_missing_reason'] = unit_route.get('subtitle_missing_reason')
        outcome['units_list_url'] = self._derive_units_list_url(driver.current_url) or units_list_url

        if unit_action == 'skip_existing':
            outcome['result'] = 'skipped_existing'
            return outcome

        self._submit_episode_changes(driver)
        video_file = self._episode_video_file_path(episode)
        outcome['video_file'] = video_file
        if not video_file:
            outcome['result'] = 'skipped_missing_video'
            outcome['error'] = 'Video file was not found for this episode.'
            if should_return_to_list:
                self._return_to_units_list(driver, outcome.get('units_list_url'))
                outcome['returned_to_units'] = '/units/' in driver.current_url
                outcome['current_url'] = driver.current_url
            return outcome

        self._attach_video_file_and_wait(driver, video_file)
        outcome['progress'] = '100%'
        outcome['result'] = 'uploaded'

        if should_return_to_list:
            self._return_to_units_list(driver, outcome.get('units_list_url'))
            outcome['returned_to_units'] = '/units/' in driver.current_url
            outcome['current_url'] = driver.current_url

        return outcome

    def _submit_episode_changes(self, driver: webdriver.Firefox) -> None:
        wait = WebDriverWait(driver, self.SUBMIT_WAIT_SECONDS)
        locators = [
            (By.CSS_SELECTOR, "button.mirza-form__button--sticky[type='submit']"),
            (By.XPATH, "//button[@type='submit' and contains(normalize-space(.), 'ثبت تغییرات')]"),
            (By.XPATH, "//button[@type='submit']"),
        ]
        submit_button = None
        for by, value in locators:
            try:
                submit_button = wait.until(EC.element_to_be_clickable((by, value)))
                break
            except TimeoutException:
                continue

        if submit_button is None:
            raise UploadConfigurationError(
                f'Submit button (ثبت تغییرات) was not found on episode form. current_url={driver.current_url}'
            )

        self._safe_click(driver, submit_button)
        if self._is_login_url(driver.current_url):
            raise UploadAuthExpiredError(self._auth_expired_message(driver.current_url))
        self._wait_for_page_ready(driver)
        self._pause_between_steps()

    def _attach_video_file_and_wait(self, driver: webdriver.Firefox, video_path: str) -> None:
        file_input = self._wait_for_video_upload_input(driver)
        self._pause_between_steps(0.8)
        try:
            file_input.send_keys(video_path)
        except WebDriverException as exc:
            raise UploadConfigurationError(
                f'Failed to attach video file. path={video_path} current_url={driver.current_url}'
            ) from exc

        try:
            WebDriverWait(driver, self.VIDEO_UPLOAD_START_WAIT_SECONDS, poll_frequency=0.5).until(
                lambda d: self._has_video_upload_started(d)
            )
        except TimeoutException as exc:
            raise UploadConfigurationError(
                f'Video upload did not start after attaching file. current_url={driver.current_url}'
            ) from exc

        stable_polls = 0
        deadline = time.time() + self.VIDEO_UPLOAD_WAIT_SECONDS
        while time.time() < deadline:
            if self._is_video_upload_complete(driver):
                stable_polls += 1
                if stable_polls >= self.VIDEO_UPLOAD_STABLE_POLLS:
                    self._pause_between_steps(1)
                    return
            else:
                stable_polls = 0
            time.sleep(1)

        raise UploadConfigurationError(
            f'Video upload did not reach stable 100% before timeout. current_url={driver.current_url}'
        )

    def _wait_for_video_upload_input(self, driver: webdriver.Firefox) -> Any:
        selectors = [
            'input#file_upload',
            "input[type='file']#file_upload",
            "input[type='file'][id='file_upload']",
        ]
        wait = WebDriverWait(driver, self.UPLOAD_PAGE_WAIT_SECONDS)
        try:
            return wait.until(
                lambda d: next(
                    (
                        element
                        for selector in selectors
                        for elements in [d.find_elements(By.CSS_SELECTOR, selector)]
                        for element in elements
                        if element.is_enabled()
                    ),
                    False,
                )
            )
        except TimeoutException as exc:
            raise UploadConfigurationError(
                f'Video upload input (#file_upload) not found after saving episode. current_url={driver.current_url}'
            ) from exc

    def _upload_progress_percent(self, driver: webdriver.Firefox) -> float | None:
        value_elements = driver.find_elements(By.CSS_SELECTOR, '#progress-value')
        for element in value_elements:
            text = self._normalize_digits((element.text or '').strip()).replace('٪', '%')
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
            if text.isdigit():
                try:
                    return float(text)
                except ValueError:
                    continue

        bar_elements = driver.find_elements(By.CSS_SELECTOR, '#progress-bar')
        for element in bar_elements:
            style = self._normalize_digits((element.get_attribute('style') or '').strip())
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', style)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue

        return None

    def _has_video_upload_started(self, driver: webdriver.Firefox) -> bool:
        percent = self._upload_progress_percent(driver)
        if percent is not None and percent > 0:
            return True

        file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input#file_upload')
        for element in file_inputs:
            value = (element.get_attribute('value') or '').strip()
            if value:
                return True
        return False

    def _is_video_upload_complete(self, driver: webdriver.Firefox) -> bool:
        percent = self._upload_progress_percent(driver)
        if percent is not None and percent >= 100:
            return True

        value_elements = driver.find_elements(By.CSS_SELECTOR, '#progress-value')
        for element in value_elements:
            text = self._normalize_digits((element.text or '').strip()).replace('٪', '%')
            if '100%' in text or text == '100':
                return True

        bar_elements = driver.find_elements(By.CSS_SELECTOR, '#progress-bar')
        for element in bar_elements:
            style = self._normalize_digits((element.get_attribute('style') or '').strip())
            if '100%' in style:
                return True
        return False

    def _return_to_units_list(self, driver: webdriver.Firefox, units_list_url: str | None) -> None:
        locators = [
            (By.XPATH, "//a[contains(@href, '/units/') and contains(normalize-space(.), 'بازگشت')]"),
            (By.CSS_SELECTOR, "a.mirza-form__button[href*='/units/']"),
            (By.XPATH, "//a[contains(@href, '/units/')]"),
        ]
        wait = WebDriverWait(driver, self.NAV_BACK_WAIT_SECONDS)
        for by, value in locators:
            try:
                back_link = wait.until(EC.element_to_be_clickable((by, value)))
            except TimeoutException:
                continue

            self._safe_click(driver, back_link)
            if self._is_login_url(driver.current_url):
                raise UploadAuthExpiredError(self._auth_expired_message(driver.current_url))
            try:
                WebDriverWait(driver, self.NAV_BACK_WAIT_SECONDS).until(lambda d: '/units/' in d.current_url)
                self._wait_for_page_ready(driver)
                self._wait_for_units_listing_ready(driver)
                self._pause_between_steps()
                return
            except TimeoutException:
                continue

        if units_list_url:
            driver.get(units_list_url)
            if self._is_login_url(driver.current_url):
                raise UploadAuthExpiredError(self._auth_expired_message(driver.current_url))
            if '/units/' in driver.current_url:
                self._wait_for_page_ready(driver)
                self._wait_for_units_listing_ready(driver)
                self._pause_between_steps()
                return

        raise UploadConfigurationError(
            f'Could not navigate back to units list after video upload. current_url={driver.current_url}'
        )

    def _normalize_digits(self, value: str) -> str:
        if not value:
            return value
        return value.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))

    def _populate_episode_form(self, driver: webdriver.Firefox, episode: Episode) -> dict[str, Any]:
        title_value = self._episode_form_title(episode)
        wait = WebDriverWait(driver, self.FORM_WAIT_SECONDS)
        try:
            title_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input#id_title,input[name='title']"))
            )
        except TimeoutException as exc:
            raise UploadConfigurationError(
                f'Title input was not found on episode form. current_url={driver.current_url}'
            ) from exc

        title_input.click()
        title_input.send_keys(Keys.CONTROL, 'a')
        title_input.send_keys(Keys.DELETE)
        title_input.send_keys(title_value)

        subtitle_path = self._episode_subtitle_vtt_path(episode)
        if not subtitle_path:
            return {
                'form_filled': True,
                'form_title': title_value,
                'subtitle_attached': False,
                'subtitle_path': None,
                'subtitle_missing_reason': 'processed_vtt_not_found',
            }

        file_inputs = driver.find_elements(By.CSS_SELECTOR, "input#id_caption_file,input[name='caption_file']")
        if not file_inputs:
            return {
                'form_filled': True,
                'form_title': title_value,
                'subtitle_attached': False,
                'subtitle_path': subtitle_path,
                'subtitle_missing_reason': 'caption_input_not_found',
            }
        try:
            file_inputs[0].send_keys(subtitle_path)
        except WebDriverException as exc:
            raise UploadConfigurationError(
                f'Failed to attach VTT subtitle file. path={subtitle_path} current_url={driver.current_url}'
            ) from exc

        return {
            'form_filled': True,
            'form_title': title_value,
            'subtitle_attached': True,
            'subtitle_path': subtitle_path,
            'subtitle_missing_reason': None,
        }

    def _episode_form_title(self, episode: Episode) -> str:
        title_fa = (episode.title_fa or '').strip()
        if title_fa:
            return title_fa

        title_en = (episode.title_en or '').strip()
        if title_en:
            return title_en

        if episode.episode_number is not None:
            return f'Episode {episode.episode_number}'
        return 'Episode'

    def _episode_subtitle_vtt_path(self, episode: Episode) -> str | None:
        candidates: list[str] = []
        processed = (episode.subtitle_processed_path or '').strip()
        local_subtitle = (episode.subtitle_local_path or '').strip()

        if processed:
            candidates.append(processed)
        if local_subtitle:
            candidates.append(local_subtitle)

        for raw in candidates:
            candidate = Path(raw)
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() != '.vtt':
                continue
            return str(candidate.resolve())
        return None

    def _episode_video_file_path(self, episode: Episode) -> str | None:
        local_video = (episode.video_local_path or '').strip()
        if not local_video:
            return None
        candidate = Path(local_video)
        if not candidate.is_file():
            return None
        return str(candidate.resolve())

    def _episode_title_candidates(self, episode: Episode) -> list[str]:
        candidates: list[str] = []
        title_fa = (episode.title_fa or '').strip()
        title_en = (episode.title_en or '').strip()

        if title_fa:
            candidates.append(title_fa)
        if title_en:
            candidates.append(title_en)
        if title_fa and title_en:
            candidates.append(f'{title_fa} ({title_en})')
            candidates.append(f'{title_fa}({title_en})')

        return candidates

    def _normalize_title_text(self, value: str) -> str:
        normalized = (value or '').strip().lower()
        normalized = normalized.replace('ي', 'ی').replace('ك', 'ک')
        normalized = re.sub(r'[\u200c\u200f\u202a-\u202e]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = re.sub(r'[^\w\s\u0600-\u06FF\-\(\)]', '', normalized)
        return normalized.strip()

    def _titles_match(self, row_title: str, candidate: str) -> bool:
        if row_title == candidate:
            return True
        if len(candidate) >= 6 and candidate in row_title:
            return True
        if len(row_title) >= 6 and row_title in candidate:
            return True
        if min(len(row_title), len(candidate)) >= 6:
            ratio = SequenceMatcher(None, row_title, candidate).ratio()
            if ratio >= 0.87:
                return True
        return False

    def _safe_click(self, driver: webdriver.Firefox, element: Any) -> None:
        try:
            element.click()
        except WebDriverException:
            driver.execute_script('arguments[0].click();', element)
        self._pause_between_steps(0.6)

    def _build_result_xpath(self, query: str) -> str:
        template = self.config.course_result_xpath_template
        if '{query}' not in template:
            return template
        return template.replace('{query}', _xpath_literal(query))

    def _derive_units_list_url(self, current_url: str) -> str | None:
        if '/units/' not in (current_url or ''):
            return None
        parts = urlsplit(current_url)
        path = parts.path or '/'
        marker = '/units/'
        marker_index = path.find(marker)
        if marker_index < 0:
            return None
        units_path = path[: marker_index + len(marker)]
        if not units_path.endswith('/'):
            units_path = f'{units_path}/'
        return f'{parts.scheme}://{parts.netloc}{units_path}'

    def _open_target_with_cookies(self, driver: webdriver.Firefox, landing_url: str | None = None) -> None:
        cookies = self._parse_cookies(self.config.cookies_json)
        if not cookies:
            raise UploadConfigurationError('No cookies configured. Please provide valid cookies in admin settings.')

        target_parts = urlsplit(self.config.target_url)
        target_host = (target_parts.hostname or '').strip()
        if not target_host:
            raise UploadConfigurationError('upload_target_url is invalid. Host is missing.')
        target_scheme = target_parts.scheme if target_parts.scheme in {'http', 'https'} else 'https'

        applied = 0
        current_seed_url = None
        for cookie in cookies:
            payload = self._normalize_cookie(cookie)
            if not payload.get('name') or payload.get('value') is None:
                continue

            cookie_host = str(payload.get('domain') or '').strip().lstrip('.') or target_host
            seed_scheme = 'https' if payload.get('secure') else target_scheme
            seed_url = f'{seed_scheme}://{cookie_host}/'

            try:
                if current_seed_url != seed_url:
                    driver.get(seed_url)
                    self._wait_for_page_ready(driver, timeout=self.PAGE_WAIT_SECONDS)
                    current_seed_url = seed_url

                cookie_payload = dict(payload)
                if not cookie_payload.get('domain'):
                    cookie_payload.pop('domain', None)

                driver.add_cookie(cookie_payload)
                applied += 1
            except (WebDriverException, AssertionError, ValueError, TypeError):
                continue

        if applied == 0:
            raise UploadConfigurationError(
                'No valid cookies could be applied. Re-export cookies and ensure domain matches target URL.'
            )

        driver.get(landing_url or self.config.target_url)
        self._wait_for_page_ready(driver)
        self._pause_between_steps()

    def _assert_logged_in(self, driver: webdriver.Firefox) -> None:
        if self.config.login_check_selector:
            try:
                WebDriverWait(driver, self.LOGIN_WAIT_SECONDS).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, self.config.login_check_selector))
                )
                return
            except TimeoutException as exc:
                raise UploadAuthExpiredError(
                    self._auth_expired_message(driver.current_url)
                ) from exc

        if self._is_login_url(driver.current_url):
            raise UploadAuthExpiredError(
                self._auth_expired_message(driver.current_url)
            )

    def _is_login_url(self, url: str) -> bool:
        lowered = (url or '').lower()
        return any(token in lowered for token in ['login', 'signin', 'auth'])

    def _auth_expired_message(self, current_url: str) -> str:
        base = 'Cookies seem expired or invalid. Please update cookies from admin panel.'
        host = (urlsplit(current_url).hostname or '').strip().lower()
        if not host:
            return base
        if self._has_auth_cookie_for_host(host):
            return base
        return (
            f'{base} No auth cookie was found for domain "{host}". '
            'Export cookies while logged in on that domain and save again.'
        )

    def _has_auth_cookie_for_host(self, host: str) -> bool:
        tracking_prefixes = ('_ga', '_gid', '_gcl', '_cl', '__stripe')
        try:
            cookies = self._parse_cookies(self.config.cookies_json)
        except UploadConfigurationError:
            return False

        for cookie in cookies:
            raw_domain = str(cookie.get('domain') or '').strip().lower().lstrip('.')
            if not raw_domain:
                continue
            if not (host == raw_domain or host.endswith(f'.{raw_domain}')):
                continue

            name = str(cookie.get('name') or '').strip().lower()
            if not name:
                continue
            if any(name.startswith(prefix) for prefix in tracking_prefixes):
                continue
            return True
        return False

    def _parse_cookies(self, raw: str) -> list[dict[str, Any]]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UploadConfigurationError('Cookies JSON is invalid.') from exc
        if not isinstance(payload, list):
            raise UploadConfigurationError('Cookies JSON must be a list.')
        return [item for item in payload if isinstance(item, dict)]

    def _normalize_cookie(self, cookie: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key in ('name', 'value', 'path', 'domain'):
            value = cookie.get(key)
            if value is not None:
                payload[key] = value

        raw_expiry = cookie.get('expiry', cookie.get('expirationDate'))
        if raw_expiry is not None:
            try:
                expiry = int(float(raw_expiry))
                if expiry > 0:
                    payload['expiry'] = expiry
            except (TypeError, ValueError):
                pass

        for bool_key in ('secure', 'httpOnly'):
            raw = cookie.get(bool_key)
            if raw is not None:
                payload[bool_key] = bool(raw)

        same_site_raw = cookie.get('sameSite')
        if isinstance(same_site_raw, str):
            normalized = same_site_raw.strip().lower()
            same_site_map = {
                'strict': 'Strict',
                'lax': 'Lax',
                'none': 'None',
                'no_restriction': 'None',
            }
            same_site_value = same_site_map.get(normalized)
            if same_site_value:
                payload['sameSite'] = same_site_value

        return payload

    def _create_driver(self) -> webdriver.Firefox:
        options = FirefoxOptions()
        options.headless = self.config.headless
        options.set_capability('pageLoadStrategy', 'normal')
        service = (
            FirefoxService(executable_path=self.config.geckodriver_path)
            if self.config.geckodriver_path
            else FirefoxService()
        )
        try:
            driver = webdriver.Firefox(service=service, options=options)
            driver.set_page_load_timeout(self.PAGELOAD_TIMEOUT_SECONDS)
            return driver
        except WebDriverException as exc:
            raise UploadConfigurationError(
                'Failed to start Firefox WebDriver. Install Firefox + geckodriver and verify permissions.'
            ) from exc

    def _retain_debug_browser(self, driver: webdriver.Firefox) -> None:
        self.DEBUG_BROWSER_POOL.append(driver)
        while len(self.DEBUG_BROWSER_POOL) > self.DEBUG_BROWSER_POOL_LIMIT:
            stale = self.DEBUG_BROWSER_POOL.pop(0)
            try:
                stale.quit()
            except Exception:
                pass

    def _load_config(self) -> UploadAutomationConfig:
        rows = self.db.query(Setting).filter(Setting.key.in_(self.SETTINGS_KEYS)).all()
        values = {row.key: row.value for row in rows}

        target_url = (values.get('upload_target_url') or '').strip()
        if not target_url:
            raise UploadConfigurationError('upload_target_url is empty. Configure it in admin settings.')

        return UploadAutomationConfig(
            headless=_parse_bool(values.get('upload_firefox_headless'), default=False),
            target_url=target_url,
            cookies_json=values.get('upload_cookies_json') or '[]',
            search_input_selector=values.get('upload_search_input_selector') or "input[type='search']",
            course_result_xpath_template=values.get('upload_course_result_xpath_template')
            or "//a[contains(normalize-space(.), {query})]",
            sections_button_xpath=values.get('upload_sections_button_xpath')
            or "//a[contains(@href, '/chapters/') and contains(normalize-space(.), 'فصل') and contains(normalize-space(.), 'جلس')]",
            units_button_xpath=values.get('upload_units_button_xpath') or "//a[contains(@href, '/units/')]",
            login_check_selector=values.get('upload_login_check_selector') or '',
            episode_page_indicator_selector=values.get('upload_episode_page_indicator_selector') or '',
            geckodriver_path=(values.get('upload_firefox_geckodriver_path') or '').strip() or None,
        )

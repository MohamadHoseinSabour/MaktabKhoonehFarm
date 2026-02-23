import json

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.ai_config import AIConfig
from app.models.course import Course
from app.models.episode import Episode
from app.services.ai.claude_provider import ClaudeProvider
from app.services.ai.openai_provider import OpenAIProvider
from app.services.ai.prompt_manager import PromptManager
from app.services.ai.security import decrypt_secret

logger = get_logger('ai.translator')


class AITranslator:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.prompt_manager = PromptManager()
        self.cache: dict[str, str] = {}

    def translate_course(self, course: Course) -> dict:
        provider = self._get_provider()
        if not provider:
            return {'translated': False, 'reason': 'No active AI provider configured'}

        updates = {}
        if course.title_en and not course.title_fa:
            prompt = self.prompt_manager.build_course_title_prompt(course.title_en, course.source_platform)
            updates['title_fa'] = self._call_with_cache(provider, f'title:{course.id}', prompt)

        if course.description_en and not course.description_fa:
            prompt = self.prompt_manager.build_description_prompt(course.description_en)
            updates['description_fa'] = self._call_with_cache(provider, f'desc:{course.id}', prompt)

        if updates:
            for key, value in updates.items():
                setattr(course, key, value)
            self.db.commit()

        return {'translated': bool(updates), 'updated_fields': list(updates.keys())}

    def translate_episode_titles(self, course: Course, batch_size: int = 20) -> dict:
        provider = self._get_provider()
        if not provider:
            return {'translated': 0, 'reason': 'No active AI provider configured'}

        episodes = (
            self.db.query(Episode)
            .filter(Episode.course_id == course.id)
            .order_by(Episode.episode_number.asc().nullslast())
            .all()
        )
        pending = [ep for ep in episodes if ep.title_en and not ep.title_fa]
        translated = 0

        for i in range(0, len(pending), batch_size):
            chunk = pending[i : i + batch_size]
            prompt_payload = [{'number': ep.episode_number, 'title': ep.title_en} for ep in chunk]
            prompt = self.prompt_manager.build_episode_batch_prompt(course, prompt_payload)
            response = self._call_with_cache(provider, f'ep:{course.id}:{i}', prompt)

            try:
                parsed = json.loads(response)
            except json.JSONDecodeError:
                logger.warning('Episode translation returned non-JSON payload')
                continue

            by_number = {item.get('number'): item.get('title_fa') for item in parsed if isinstance(item, dict)}
            for ep in chunk:
                if title_fa := by_number.get(ep.episode_number):
                    ep.title_fa = title_fa
                    translated += 1

        self.db.commit()
        return {'translated': translated, 'total_pending': len(pending)}

    def _call_with_cache(self, provider, cache_key: str, prompt: str) -> str:
        if cache_key in self.cache:
            return self.cache[cache_key]
        result = provider.translate(prompt)
        self.cache[cache_key] = result
        return result

    def _get_provider(self):
        configs = (
            self.db.query(AIConfig)
            .filter(AIConfig.is_active.is_(True))
            .order_by(AIConfig.priority.asc())
            .all()
        )

        for cfg in configs:
            try:
                api_key = decrypt_secret(cfg.api_key)
                provider_name = cfg.provider.lower()
                if provider_name == 'openai':
                    return OpenAIProvider(api_key=api_key, model=cfg.model_name, endpoint_url=cfg.endpoint_url)
                if provider_name == 'claude':
                    return ClaudeProvider(api_key=api_key, model=cfg.model_name, endpoint_url=cfg.endpoint_url)
            except Exception as exc:
                logger.warning('Failed to initialize provider %s: %s', cfg.provider, exc)
                continue
        return None
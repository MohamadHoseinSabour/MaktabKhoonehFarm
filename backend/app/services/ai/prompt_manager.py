from app.models.course import Course


DEFAULT_PROMPTS = {
    'course_title_translation': (
        'Translate the following online course title to Persian (Farsi). '
        'Keep technical terms in English parenthetically. '\
        'Make it natural and appealing for Iranian audience. '\
        'Title: {title}\nPlatform: {platform}\nOutput format: Just the translated title, nothing else.'
    ),
    'episode_title_translation': (
        'Translate these episode titles from an online course to Persian. '\
        'Course: {course_title}\nKeep technical terms in English parenthetically. '\
        'Maintain numbering.\nEpisodes:\n{episode_list}\nOutput as JSON: [{number, title_fa}]'
    ),
    'description_translation': (
        'Translate the following course description to Persian. '\
        'Make it professional and suitable for an educational platform. '\
        'Keep technical terms in English parenthetically. '\
        'Description: {description}\nOutput: Translated description in Persian.'
    ),
}


class PromptManager:
    def build_course_title_prompt(self, title: str, platform: str | None) -> str:
        template = DEFAULT_PROMPTS['course_title_translation']
        return template.format(title=title, platform=platform or 'Unknown')

    def build_description_prompt(self, description: str) -> str:
        template = DEFAULT_PROMPTS['description_translation']
        return template.format(description=description)

    def build_episode_batch_prompt(self, course: Course, episodes: list[dict]) -> str:
        episode_list = '\n'.join([f"{item['number']}. {item['title']}" for item in episodes])
        template = DEFAULT_PROMPTS['episode_title_translation']
        return template.format(course_title=course.title_en or '', episode_list=episode_list)
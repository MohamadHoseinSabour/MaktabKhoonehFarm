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
        'Maintain numbering.\nEpisodes:\n{episode_list}\nOutput as JSON: [{{"number":1,"title_fa":"..."}}]'
    ),
    'single_episode_title_translation': (
        'Translate the following episode title from an online course to Persian. '
        'Course: {course_title}\nEpisode number: {episode_number}\nTitle: {title}\n'
        'Keep technical terms in English parenthetically.\n'
        'Output format: Just the translated title in Persian, nothing else.'
    ),
    'description_translation': (
        'Translate the following course description to Persian. '\
        'Make it professional and suitable for an educational platform. '\
        'Keep technical terms in English parenthetically. '\
        'Description: {description}\nOutput: Translated description in Persian.'
    ),
    'course_content_generation': (
        'Based on the scraped course data below, generate Persian educational content for a course page.\n'
        'Data:\n{course_data}\n\n'
        'Return only valid JSON with this exact shape:\n'
        '{{'
        '"course_overview":"string",'
        '"prerequisites":["string"],'
        '"prerequisites_description":"string",'
        '"what_you_will_learn":["string"],'
        '"course_goals":["string"]'
        '}}\n'
        'Rules:\n'
        '- Content must be in Persian.\n'
        '- `course_overview` must be comprehensive and long: at least 220 words and at least 1300 characters.\n'
        '- `course_overview` must explain the course scope, target audience, core workflow, and expected outcomes.\n'
        '- `course_overview` should be written in clear, cohesive long-form prose.\n'
        '- `prerequisites` should have 3 to 6 items.\n'
        '- `what_you_will_learn` should have 4 to 8 items.\n'
        '- `course_goals` should have 3 to 6 items.\n'
        '- Be accurate and grounded in given data. If data is limited, keep claims conservative.\n'
        '- Do not add markdown, numbering, or any extra keys.'
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

    def build_single_episode_title_prompt(self, course: Course, episode_number: int | None, title: str) -> str:
        template = DEFAULT_PROMPTS['single_episode_title_translation']
        return template.format(
            course_title=course.title_en or '',
            episode_number=episode_number if episode_number is not None else '-',
            title=title,
        )

    def build_course_content_prompt(self, course_data: str) -> str:
        template = DEFAULT_PROMPTS['course_content_generation']
        return template.format(course_data=course_data)

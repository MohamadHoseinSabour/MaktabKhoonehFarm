from bs4 import BeautifulSoup

from app.services.scraper.gitir_scraper import GitIRScraper


def test_extract_bilingual_descriptions_from_content_blocks():
    scraper = GitIRScraper()
    html = """
    <article class="content">
      <p>This course teaches modern React patterns for production apps.</p>
      <p>در این دوره با الگوهای مدرن ری‌اکت برای پروژه‌های واقعی آشنا می‌شوید.</p>
    </article>
    """
    soup = BeautifulSoup(html, 'lxml')
    node = soup.select_one('article.content')

    description_en, description_fa = scraper._extract_bilingual_descriptions(
        node,
        raw_description=None,
        meta_description=None,
    )

    assert description_en is not None and 'React' in description_en
    assert description_fa is not None and 'دوره' in description_fa


def test_extract_bilingual_descriptions_falls_back_to_meta_for_english():
    scraper = GitIRScraper()
    html = """
    <div class="entry-content">
      <p>این دوره مفاهیم پایه را با مثال‌های عملی آموزش می‌دهد.</p>
    </div>
    """
    soup = BeautifulSoup(html, 'lxml')
    node = soup.select_one('.entry-content')

    description_en, description_fa = scraper._extract_bilingual_descriptions(
        node,
        raw_description='این دوره مفاهیم پایه را با مثال‌های عملی آموزش می‌دهد.',
        meta_description='Learn the fundamentals with practical examples.',
    )

    assert description_en == 'Learn the fundamentals with practical examples.'
    assert description_fa is not None and 'مفاهیم' in description_fa

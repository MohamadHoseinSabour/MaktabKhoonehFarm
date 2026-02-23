from pathlib import Path

from app.services.processor.subtitle_processor import SubtitleProcessor


def test_subtitle_processor_cleans_ads_and_normalizes_persian(tmp_path: Path):
    source = tmp_path / 'input.srt'
    output = tmp_path / 'output.srt'

    source.write_text(
        '1\n00:00:00,000 --> 00:00:01,000\nwelcome to git.ir\n\n'
        '2\n00:00:01,100 --> 00:00:02,000\n???? ? ? ?\n\n',
        encoding='utf-8',
    )

    processor = SubtitleProcessor()
    result = processor.process(source, output)

    payload = output.read_text(encoding='utf-8')
    assert result['input_count'] == 2
    assert result['output_count'] == 1
    assert 'git.ir' not in payload
    assert '?' in payload
    assert '?' in payload
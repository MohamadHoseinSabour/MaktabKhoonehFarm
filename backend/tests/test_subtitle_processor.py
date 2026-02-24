from pathlib import Path

from app.services.processor.subtitle_processor import SubtitleProcessor


def test_subtitle_processor_removes_gitir_ai_line_and_shifts_10s(tmp_path: Path):
    source = tmp_path / 'input.srt'
    output = tmp_path / 'output.vtt'

    source.write_text(
        '1\n00:00:00,000 --> 00:00:10,000\n\u062a\u0631\u062c\u0645\u0647 \u0628\u0627 \u0647\u0648\u0634 \u0645\u0635\u0646\u0648\u0639\u06cc \u062a\u0648\u0633\u0637 GIT.IR\n\n'
        '2\n00:00:10,500 --> 00:00:12,000\n\u0633\u0644\u0627\u0645 \u064a \u0648 \u0643\n\n',
        encoding='utf-8',
    )

    processor = SubtitleProcessor()
    result = processor.process(source, output)

    payload = output.read_text(encoding='utf-8')

    assert result['input_count'] == 2
    assert result['output_count'] == 1
    assert result['shift_seconds'] == 10.0
    assert '\u062a\u0631\u062c\u0645\u0647 \u0628\u0627 \u0647\u0648\u0634 \u0645\u0635\u0646\u0648\u0639\u06cc \u062a\u0648\u0633\u0637' not in payload
    assert payload.startswith('WEBVTT')
    assert '00:00:20.500 --> 00:00:22.000' in payload
    assert '\u06cc' in payload
    assert '\u06a9' in payload

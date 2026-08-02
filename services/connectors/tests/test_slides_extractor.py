from src.sources.google_extractors.slides import SlidesExtractor


def _shape(text, placeholder=None, object_id="s1"):
    shape = {"text": {"textElements": [{"textRun": {"content": text}}]}}
    if placeholder:
        shape["placeholder"] = {"type": placeholder}
    return {"objectId": object_id, "shape": shape}


def _slide(elements, notes=None):
    slide = {"pageElements": elements}
    if notes is not None:
        slide["slideProperties"] = {
            "notesPage": {
                "notesProperties": {"speakerNotesObjectId": "notes1"},
                "pageElements": [_shape(notes, object_id="notes1")],
            }
        }
    return slide


class _FakeSlides:
    def __init__(self, deck):
        self._deck = deck

    def presentations(self):
        return self

    def get(self, *, presentationId):
        return self

    def execute(self):
        return self._deck


def _extract(slides):
    services = {"slides": _FakeSlides({"slides": slides})}
    return SlidesExtractor().extract(
        services, "file123", "application/vnd.google-apps.presentation"
    )


def test_titled_slide_gets_a_numbered_heading():
    out = _extract([_slide([_shape("Sponsorship Tiers\n", placeholder="TITLE")])]).text
    assert "## Slide 1: Sponsorship Tiers" in out


def test_centered_title_also_counts_as_the_title():
    out = _extract([_slide([_shape("Welcome\n", placeholder="CENTERED_TITLE")])]).text
    assert "## Slide 1: Welcome" in out


def test_slide_without_a_title_placeholder_has_no_colon():
    out = _extract([_slide([_shape("just body text\n")])]).text
    assert "## Slide 1" in out
    assert "## Slide 1:" not in out


def test_slides_are_numbered_from_one_in_order():
    out = _extract(
        [
            _slide([_shape("First\n", placeholder="TITLE")]),
            _slide([_shape("Second\n", placeholder="TITLE")]),
        ]
    ).text
    assert "## Slide 1: First" in out
    assert "## Slide 2: Second" in out


def test_bulleted_shape_keeps_one_line_per_bullet():
    # A single Slides shape holds every bullet, with newlines INSIDE textRun
    # content. Stripping them the way the Docs extractor does would collapse
    # this into one run-on line.
    out = _extract([_slide([_shape("alpha\nbeta\ngamma\n")])]).text
    assert "alpha\nbeta\ngamma" in out


def test_speaker_notes_are_extracted_via_the_notes_object_id():
    out = _extract(
        [_slide([_shape("Q3 Roadmap\n", placeholder="TITLE")], notes="Lead with Gold.\n")]
    ).text
    assert "**Speaker notes:** Lead with Gold." in out


def test_slide_without_notes_omits_the_notes_line():
    out = _extract([_slide([_shape("No notes here\n")])]).text
    assert "Speaker notes" not in out


def test_notes_page_without_a_matching_object_id_yields_no_notes():
    slide = {
        "pageElements": [_shape("body\n")],
        "slideProperties": {
            "notesPage": {
                "notesProperties": {"speakerNotesObjectId": "missing"},
                "pageElements": [_shape("orphan\n", object_id="other")],
            }
        },
    }
    out = _extract([slide]).text
    assert "Speaker notes" not in out
    assert "orphan" not in out


def test_non_text_elements_are_skipped():
    slide = _slide(
        [
            {"objectId": "img1", "image": {"contentUrl": "https://x"}},
            _shape("real text\n"),
        ]
    )
    out = _extract([slide]).text
    assert "real text" in out


def test_whitespace_only_shape_is_dropped():
    out = _extract([_slide([_shape("   \n"), _shape("kept\n")])]).text
    assert "kept" in out
    assert "\n\n" not in out


def test_table_renders_as_a_markdown_table():
    table = {
        "objectId": "t1",
        "table": {
            "tableRows": [
                {
                    "tableCells": [
                        {"text": {"textElements": [{"textRun": {"content": "Tier\n"}}]}},
                        {"text": {"textElements": [{"textRun": {"content": "Amount\n"}}]}},
                    ]
                },
                {
                    "tableCells": [
                        {"text": {"textElements": [{"textRun": {"content": "Gold\n"}}]}},
                        {"text": {"textElements": [{"textRun": {"content": "$5,000\n"}}]}},
                    ]
                },
            ]
        },
    }
    out = _extract([_slide([table])]).text
    assert "| Tier | Amount |" in out
    assert "| --- | --- |" in out
    assert "| Gold | $5,000 |" in out


def test_empty_deck_yields_empty_text():
    assert _extract([]).text == ""


def test_extractor_declares_scope_and_service():
    assert SlidesExtractor().scopes == ("https://www.googleapis.com/auth/presentations.readonly",)
    assert SlidesExtractor().services == ("slides",)

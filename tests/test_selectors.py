from src.instagram.selectors import is_video


def test_is_video_uses_verified_aria_label_format():
    assert is_video("Video, 1 of 18, by @someone, shared September 28, 2026")
    assert not is_video("Photo, 13 of 18, by @someone, shared September 27, 2026")
    assert not is_video(None)
    assert not is_video("")

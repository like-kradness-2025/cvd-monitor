"""Discord sender placeholder."""


def send_chart(webhook_url: str | None, image_path: str) -> bool:
    return bool(webhook_url and image_path)

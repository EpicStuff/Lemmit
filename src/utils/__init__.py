from datetime import datetime


def format_duration(timestamp) -> str:
    now = datetime.utcnow()
    duration = now - timestamp

    seconds = duration.total_seconds()
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    formatted_duration = ""
    if hours >= 1:
        formatted_duration += f"{int(hours):2d}:"
    if minutes >= 1 or hours >= 1:
        formatted_duration += f"{int(minutes):02d}:"
    formatted_duration += f"{int(seconds):02d}"

    return formatted_duration

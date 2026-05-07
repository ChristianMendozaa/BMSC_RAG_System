# Deprecated — replaced by app.utils.model_manager
# Kept as a no-op stub so any stale import does not crash.
from app.utils.model_manager import download_and_load_all


async def ensure_models() -> None:
    await download_and_load_all()
